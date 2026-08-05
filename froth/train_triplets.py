"""
train_triplets.py - PHASE 4B (2026-07-13): fine-tune SPECTER the way SPECTER itself
was trained - with CITATION TRIPLETS, not (title, abstract) pairs.

WHY: our v1/v2 used MultipleNegativesRankingLoss on (title <-> abstract), which only
drags the model toward the corpus' center of mass - so more data (v2) did NOT beat v1.
SPECTER (Cohan et al., 2020) trains on the citation graph: a CITED paper is pulled
closer to the query paper than an uncited one, with hard negatives from citations of
citations. This replays that recipe on OUR mineral-processing citations (the
`references` column, OpenAlex referenced_works), which the uncapped re-harvest makes
plentiful.

Triplet (anchor, positive, hard_negative):
  anchor       = paper P            ("title. abstract")
  positive     = a paper P CITES that is also in the corpus
  hard_negative= a citation-of-a-citation (2 hops) NOT cited by P directly (when found)
In-batch negatives (from MultipleNegativesRankingLoss) supply the easy negatives.

Run (needs CUDA torch; minutes on the RTX 5060):
    .venv\\Scripts\\python.exe -m froth.train_triplets

Output: models/specter-mineral-v3/
"""
import random
import time

import pandas as pd
import torch
from sentence_transformers import InputExample, SentenceTransformer, losses
from torch.utils.data import DataLoader

from . import config

MASTER = config.ROOT / "2_Datos" / "master_corpus.parquet"
OUT = config.ROOT / "models" / "specter-mineral-v3"
BATCH_SIZE = 16
# 1 epoch, tuned live (Batman's call): the uncapped corpus yields 150,885 triplets -
# at seq 512 x 2 epochs the laptop GPU measured ~3.2 s/step = ~17 h of training. One
# pass over 150k triplets is plenty of signal, and every example is still seen once.
EPOCHS = 1
# Abstracts here average ~200 tokens, so 256 keeps them nearly whole while roughly
# halving attention cost vs SPECTER's default 512 (measured: the step-time driver).
MAX_SEQ_LENGTH = 256


def _text(row) -> str:
    return f"{row['title']}. {row['abstract']}"


def build_citation_examples(corpus: pd.DataFrame) -> list[InputExample]:
    """Turn the citation graph inside the corpus into (anchor, positive, hard_negative)
    training triplets. Only citations whose target is ALSO in the corpus count."""
    corpus = corpus[(corpus["title"].str.len() > 10)
                    & (corpus["abstract"].str.len() > 100)].reset_index(drop=True)
    id_to_pos = {pid: i for i, pid in enumerate(corpus["id"]) if pid}
    refs = corpus["references"] if "references" in corpus.columns else [[]] * len(corpus)

    examples, with_hard = [], 0
    rng = random.Random(42)
    n = len(corpus)
    for i, cites in enumerate(refs):
        cites = list(cites) if cites is not None else []
        pos_ids = [c for c in cites if c in id_to_pos and id_to_pos[c] != i]
        if not pos_ids:
            continue
        anchor = _text(corpus.iloc[i])
        for pid in pos_ids[:5]:                        # cap per anchor: keep it balanced
            p_pos = id_to_pos[pid]
            positive = _text(corpus.iloc[p_pos])
            # hard negative: a paper the POSITIVE cites, that the anchor does NOT cite
            hop2 = corpus.iloc[p_pos]["references"] if "references" in corpus.columns else []
            hop2 = [c for c in (list(hop2) if hop2 is not None else [])
                    if c in id_to_pos and c not in pos_ids and id_to_pos[c] != i]
            if hop2:
                hn = _text(corpus.iloc[id_to_pos[rng.choice(hop2)]])
                examples.append(InputExample(texts=[anchor, positive, hn]))
                with_hard += 1
            else:
                examples.append(InputExample(texts=[anchor, positive]))
    print(f"citation triplets: {len(examples)} "
          f"({with_hard} with an explicit hard negative)")
    return examples


def main() -> None:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device: {device}"
          + (f" ({torch.cuda.get_device_name(0)})" if device == "cuda" else " - WARNING: slow"))

    corpus = pd.read_parquet(MASTER)
    examples = build_citation_examples(corpus)
    if len(examples) < 200:
        print(f"\nOnly {len(examples)} citation triplets - too few to train a meaningful "
              "model (this corpus has sparse internal citations). Honest stop: the "
              "uncapped re-harvest should raise this; re-run after Phase A finishes.")
        return

    loader = DataLoader(examples, shuffle=True, batch_size=BATCH_SIZE)
    model = SentenceTransformer(config.EMBEDDING_MODEL, device=device)
    model.max_seq_length = MAX_SEQ_LENGTH
    loss = losses.MultipleNegativesRankingLoss(model)   # uses the hard neg + in-batch negs

    t0 = time.time()
    model.fit(train_objectives=[(loader, loss)],
              epochs=EPOCHS,
              warmup_steps=max(10, len(loader) // 10),
              output_path=str(OUT),
              use_amp=(device == "cuda"),
              # Watchdog lesson applied to training: checkpoint every 1000 steps so a
              # sleep/interruption costs minutes, not the whole run.
              checkpoint_path=str(OUT) + "-ckpt",
              checkpoint_save_steps=1000,
              checkpoint_save_total_limit=2,
              show_progress_bar=True)
    print(f"\nTrained in {time.time() - t0:.0f}s. specter-mineral-v3 lives at:\n  {OUT}")


if __name__ == "__main__":
    main()
