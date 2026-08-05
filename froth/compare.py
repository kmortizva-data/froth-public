"""
compare.py - PHASE 6.6: generic SPECTER vs YOUR fine-tuned model, measured.

WHAT IT DOES: for every cohort topic, embeds the corpus with BOTH models, clusters each
(same UMAP seed, DBCV-chosen granularity) and records the best DBCV validity. The output
table answers the thesis-grade question: does domain fine-tuning make better maps?
A blind test file is also exported: two cluster listings labeled A/B (mapping hidden) so
the expert can judge without knowing which model made which.

HOW TO RUN IT (after froth.train):
    .venv\\Scripts\\python.exe -m froth.compare
"""

import random

import pandas as pd
from sentence_transformers import SentenceTransformer

from . import config
from . import cluster as cl

GENERIC = config.EMBEDDING_MODEL
MINERAL = str(config.ROOT / "models" / "specter-mineral")
REPORT = config.ROOT / "2_Datos" / "model_comparison.csv"
BLIND = config.ROOT / "3_Resultados" / "blind_test.md"
BLIND_KEY = config.ROOT / "2_Datos" / "blind_key.txt"


def corpus_paths() -> list[tuple[str, object]]:
    """(slug, papers.parquet path) for the default topic + every batch topic."""
    out = [("default-beauvoir", config.ROOT / "2_Datos" / "processed" / "papers.parquet")]
    for p in sorted((config.ROOT / "2_Datos" / "topics").glob("*/processed/papers.parquet")):
        out.append((p.parent.parent.name, p))
    return out


def best_validity(model: SentenceTransformer, df: pd.DataFrame) -> dict:
    """Embed -> UMAP (fixed seed) -> DBCV sweep. Returns the corpus' best clustering stats."""
    texts = (df["title"] + ". " + df["abstract"]).tolist()
    vectors = model.encode(texts, show_progress_bar=False)
    xy = cl.reduce_to_2d(vectors)
    mcs, table = cl.recommend_min_cluster_size(xy)
    row = table[table["min_cluster_size"] == mcs].iloc[0]
    return {"validity": float(row["validity"]), "clusters": int(row["clusters"]),
            "noise": int(row["noise"]), "mcs": mcs, "xy": xy, "vectors": vectors}


def main() -> None:
    print("loading both models...")
    models = {"generic": SentenceTransformer(GENERIC),
              "mineral": SentenceTransformer(MINERAL)}

    rows = []
    blind_topic = None
    for slug, path in corpus_paths():
        df = pd.read_parquet(path)
        df = df[df["relevance"] >= config.RELEVANCE_THRESHOLD].reset_index(drop=True)
        if len(df) < 25:
            continue
        row = {"topic": slug[:45], "papers": len(df)}
        results = {}
        for name, model in models.items():
            r = best_validity(model, df)
            row[f"dbcv_{name}"] = round(r["validity"], 3)
            row[f"clusters_{name}"] = r["clusters"]
            results[name] = r
        row["delta"] = round(row["dbcv_mineral"] - row["dbcv_generic"], 3)
        rows.append(row)
        print(f"  {row['topic']:<45} generic={row['dbcv_generic']:.3f} "
              f"mineral={row['dbcv_mineral']:.3f} delta={row['delta']:+.3f}")
        if blind_topic is None and slug == "default-beauvoir":
            blind_topic = (slug, df, results)

    report = pd.DataFrame(rows)
    report.to_csv(REPORT, index=False)
    wins = int((report["delta"] > 0).sum())
    print(f"\nmineral wins on DBCV: {wins}/{len(report)} topics "
          f"(mean delta {report['delta'].mean():+.3f})")
    print(f"Report: {REPORT}")

    # --- Blind test: same corpus, two anonymous cluster listings -----------------------
    if blind_topic:
        slug, df, results = blind_topic
        letters = ["A", "B"]
        random.shuffle(letters)
        mapping = dict(zip(letters, ["generic", "mineral"]))
        lines = [f"# Blind test - which clustering reads better? (topic: {slug})", ""]
        for letter in sorted(mapping):
            name = mapping[letter]
            r = results[name]
            labels = cl.cluster_points(r["xy"], min_cluster_size=r["mcs"])
            names = cl.label_clusters(df, labels)
            lines.append(f"## Model {letter}")
            for c in sorted(set(labels)):
                if c == -1:
                    continue
                n = int((labels == c).sum())
                lines.append(f"- ({n} papers) {names[c]}")
            lines.append("")
        lines.append("*Judge which grouping tells the field's story better, then ask for "
                     "the key.*")
        BLIND.write_text("\n".join(lines), encoding="utf-8")
        BLIND_KEY.write_text(str(mapping), encoding="utf-8")
        print(f"Blind test: {BLIND}\n(key hidden at {BLIND_KEY} - no peeking)")


if __name__ == "__main__":
    main()
