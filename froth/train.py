"""
train.py - PHASE 6.5: fine-tune SPECTER on the master corpus. YOUR model is born here.

WHAT IT DOES: takes the 1,290-paper master corpus (6.4) and teaches SPECTER the dialect
of mineral processing. Self-supervised - no hand labels: each paper's (title, abstract)
pair is a positive example, and MultipleNegativesRankingLoss uses every OTHER abstract in
the batch as negatives ("your title should sit closer to YOUR abstract than to anyone
else's"). One clever loss turns a plain corpus into a training set.

HOW TO RUN IT (needs the CUDA torch build; ~minutes on the RTX 5060):
    .venv\\Scripts\\python.exe -m froth.train

Output: models/specter-mineral/ - load it by setting EMBEDDING_MODEL to that path.
"""

import time

import pandas as pd
import torch
from sentence_transformers import InputExample, SentenceTransformer, losses
from torch.utils.data import DataLoader

from . import config

MASTER = config.ROOT / "2_Datos" / "master_corpus.parquet"
OUT = config.ROOT / "models" / "specter-mineral"

BATCH_SIZE = 16
EPOCHS = 2


def main() -> None:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device: {device}"
          + (f" ({torch.cuda.get_device_name(0)})" if device == "cuda" else " - WARNING: slow"))

    corpus = pd.read_parquet(MASTER)
    corpus = corpus[(corpus["title"].str.len() > 10) & (corpus["abstract"].str.len() > 100)]
    print(f"training pairs: {len(corpus)} (title <-> abstract of the same paper)")

    examples = [InputExample(texts=[row["title"], row["abstract"]])
                for _, row in corpus.iterrows()]
    loader = DataLoader(examples, shuffle=True, batch_size=BATCH_SIZE)

    model = SentenceTransformer(config.EMBEDDING_MODEL, device=device)
    loss = losses.MultipleNegativesRankingLoss(model)

    t0 = time.time()
    model.fit(train_objectives=[(loader, loss)],
              epochs=EPOCHS,
              warmup_steps=max(10, len(loader) // 10),
              output_path=str(OUT),
              use_amp=(device == "cuda"),          # mixed precision: faster on GPU
              show_progress_bar=True)
    print(f"\nTrained in {time.time() - t0:.0f}s. Your model lives at:\n  {OUT}")
    print("Try it: config.EMBEDDING_MODEL = str(OUT) -> re-run embed/cluster and compare.")


if __name__ == "__main__":
    main()
