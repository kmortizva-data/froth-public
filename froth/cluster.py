"""
cluster.py - PHASE 3: the bubbles and clusters (the visual core).

WHAT IT DOES: takes the vectors, "flattens" them from 768 dimensions to 2 (with UMAP) so they
can be drawn, groups the dense points into subtopics (with HDBSCAN), and gives each cluster an
automatic keyword label (c-TF-IDF idea). Saves the result table to
2_Datos/processed/topic_map.parquet.

HOW TO RUN IT (after pull and embed):
    .venv\\Scripts\\python.exe -m froth.cluster

WHAT YOU LEARN HERE (Notes 12-15):
- Dimensionality reduction: why 768D cannot be drawn and how UMAP brings it to 2D.
- Density clustering: HDBSCAN finds the number of groups by itself and flags noise (-1).
- Labeling: the words that are frequent in one cluster and rare in the others (c-TF-IDF).

Output: a table with [paper columns..., x, y, cluster, label] ready for visualize.py.
"""

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer, ENGLISH_STOP_WORDS

from . import config

# UMAP and HDBSCAN are imported INSIDE the functions that use them, not here. Measured on
# Batman's machine, importing them at module load costs 24.8s of the 52.2s the web app spent
# before painting its first screen - and the home screen uses neither. UMAP is the expensive
# half (~30s warm, it drags in numba's JIT) and is only needed when a corpus is first mapped;
# HDBSCAN is cheap once warm and is needed for the live granularity slider.
# The cost does not vanish, it MOVES: it is now paid on the first re-cluster or harvest,
# where a progress bar is already on screen and waiting is expected.

# The corpus mixes languages (Beauvoir papers have French abstracts) but sklearn's stopword
# list is English-only, so French filler words leaked into the labels ("du", "les"...).
# Minimal fix: extend the stopword list with common French function words.
FRENCH_STOP_WORDS = {
    "de", "la", "le", "les", "des", "du", "un", "une", "et", "en", "dans", "pour",
    "sur", "par", "au", "aux", "avec", "ce", "ces", "cette", "est", "sont", "plus",
    "que", "qui", "ont", "leur", "leurs", "nous", "être", "été", "comme", "entre",
}
STOP_WORDS = list(ENGLISH_STOP_WORDS | FRENCH_STOP_WORDS)

# Shared label-quality guards (Batman: labels went weird - '1966', 'ma', 'old',
# author surnames). No digits, min 2 letters. Reused by review.py's KeyBERT-style
# cluster titles so both labelers speak the same vocabulary.
TOKEN_PATTERN = r"(?u)\b[a-zA-Zµ][a-zA-Z\-]+\b"
# 2-letter tokens are usually noise ('ma') EXCEPT chemical elements (Sn, Nb, Ta...):
# gold in this domain. Plus a short blacklist of label-useless fillers.
ELEMENTS = {"li", "be", "na", "mg", "al", "si", "ti", "cr", "mn", "fe", "co", "ni",
            "cu", "zn", "zr", "nb", "mo", "sn", "ta", "hf", "pb", "th", "ce", "la",
            "nd", "cs", "rb"}
BLACKLIST = {"old", "white", "names", "cent", "historical", "room", "use", "new",
             "based", "high", "low", "large", "small"}


def is_good_term(term: str) -> bool:
    """A candidate label term is usable if every word is >=3 letters (or a chemical
    element) and none is a blacklisted filler."""
    return all((len(w) >= 3 or w in ELEMENTS) and w not in BLACKLIST
               for w in term.split())


def reduce_to_2d(vectors: np.ndarray) -> np.ndarray:
    """Flatten (N, 768) to (N, 2) with UMAP, preserving neighborhoods.

    metric="cosine": judge neighbors with the same ruler as Phase 2.
    random_state=42: fixed seed so the map is reproducible run after run.
    """
    import umap                                    # deferred: see the note at the imports
    reducer = umap.UMAP(n_components=2, metric="cosine", random_state=42)
    return reducer.fit_transform(vectors)


def cluster_points(xy: np.ndarray, min_cluster_size: int | None = None) -> np.ndarray:
    """Group dense zones of the 2D map with HDBSCAN. Returns one label per paper.

    Labels are 0..K-1; -1 means "noise" (belongs to no dense zone). The granularity
    dial is min_cluster_size: how many papers it takes to count as a subtopic
    (defaults to config.MIN_CLUSTER_SIZE; the web app exposes it as a live slider -
    cheap to recompute because HDBSCAN on 2D points takes milliseconds).
    """
    import hdbscan                                 # deferred: see the note at the imports
    mcs = min_cluster_size or config.MIN_CLUSTER_SIZE
    return hdbscan.HDBSCAN(min_cluster_size=mcs).fit_predict(xy)


def recommend_min_cluster_size(xy: np.ndarray, lo: int = 3, hi: int = 20) -> tuple[int, pd.DataFrame]:
    """Data-driven granularity: sweep min_cluster_size and keep the value that maximizes
    DBCV (density-based cluster validity - hdbscan's relative_validity_).

    DBCV rewards clusterings whose groups are dense inside and well separated; it is THE
    native quality metric for density clustering (silhouette assumes round clusters).
    Not a fixed default: recomputed for every corpus, because the right granularity
    depends on the data. Returns (best_mcs, diagnostics_table).
    """
    import hdbscan                                 # deferred: see the note at the imports
    hi = min(hi, max(lo, len(xy) // 2))            # tiny corpora: don't ask for impossible sizes
    # DBCV (relative_validity_) is ~O(n^2): on tens of thousands of points the 18x sweep can
    # hang or thrash RAM (Phase A-fix). Evaluate the sweep on a random subsample above the cap
    # - the granularity choice is stable; the final clustering (build_topic_map) uses ALL points.
    xy_eval = xy
    if len(xy) > config.DBCV_SUBSAMPLE_CAP:
        idx = np.random.default_rng(42).choice(len(xy), config.DBCV_SUBSAMPLE_CAP, replace=False)
        xy_eval = xy[idx]
        print(f"  DBCV sweep on a {config.DBCV_SUBSAMPLE_CAP}-point subsample "
              f"(corpus has {len(xy)}, keeping the sweep cheap)")
    rows = []
    best_mcs, best_v = lo, -np.inf
    for m in range(lo, hi + 1):
        cl = hdbscan.HDBSCAN(min_cluster_size=m, gen_min_span_tree=True).fit(xy_eval)
        n_clusters = int(cl.labels_.max() + 1)
        validity = float(cl.relative_validity_)
        rows.append({"min_cluster_size": m, "clusters": n_clusters,
                     "noise": int((cl.labels_ == -1).sum()), "validity": round(validity, 3)})
        if n_clusters >= 2 and validity > best_v:      # a single blob is not a clustering
            best_mcs, best_v = m, validity
    return best_mcs, pd.DataFrame(rows)


def label_clusters(df: pd.DataFrame, labels: np.ndarray, top_n: int = 4) -> dict[int, str]:
    """Give each cluster a keyword label (c-TF-IDF idea).

    Merge each cluster's title+abstract into ONE mega-document, then score words that are
    frequent in this mega-doc but rare in the others (TF-IDF across mega-docs). The top
    words become the label. Noise (-1) is labeled "noise".
    """
    cluster_ids = sorted(set(labels))
    mega_docs = []
    for c in cluster_ids:
        part = df[labels == c]
        mega_docs.append(" ".join(part["title"] + ". " + part["abstract"]))

    # Label quality guards (Batman: labels get weird at low granularity - '1966', 'ma',
    # 'old', 'white', author surnames...): no digits in tokens, and a post-filter below.
    vec = TfidfVectorizer(stop_words=STOP_WORDS, ngram_range=(1, 2), sublinear_tf=True,
                          token_pattern=TOKEN_PATTERN)
    tfidf = vec.fit_transform(mega_docs)
    words = np.array(vec.get_feature_names_out())

    names = {}
    for row, c in enumerate(cluster_ids):
        if c == -1:
            names[c] = "noise"
            continue
        scores = tfidf[row].toarray()[0]
        ranked = words[np.argsort(scores)[::-1][:20]]
        picked = [t for t in ranked if is_good_term(t)][:top_n]
        names[c] = ", ".join(picked) if picked else ", ".join(ranked[:top_n])
    return names


def build_topic_map(df: pd.DataFrame, vectors: np.ndarray,
                    min_cluster_size: int | str | None = None,
                    relevance_filter: bool = True) -> pd.DataFrame:
    """Full Phase 3 pipeline: reduce -> cluster -> label. Returns and saves the map table.

    Row i of `vectors` must correspond to row i of `df` (same order as embed.py saved them).
    min_cluster_size: an int, None (config default), or "auto" - pick per corpus by DBCV
    (small corpora need smaller subtopics; one fixed number does not fit all topics).
    relevance_filter=False maps EVERYTHING (Phase 8.5b: the cluster-level gate needs the
    full map first - junk arrives as coherent hubs, and whole clusters are judged after).
    """
    # Drop off-topic intruders BEFORE mapping: UMAP never sees them, so the layout improves.
    if relevance_filter and "relevance" in df.columns:
        mask = (df["relevance"] >= config.RELEVANCE_THRESHOLD).to_numpy()
        dropped = int((~mask).sum())
        if dropped:
            print(f"  relevance filter: dropped {dropped} papers below {config.RELEVANCE_THRESHOLD}")
        df = df[mask].reset_index(drop=True)
        vectors = vectors[mask]

    print("  reducing 768D -> 2D with UMAP ...")
    xy = reduce_to_2d(vectors)

    mcs = min_cluster_size or config.MIN_CLUSTER_SIZE
    if mcs == "auto":
        mcs, _ = recommend_min_cluster_size(xy)
        print(f"  auto granularity (DBCV): min_cluster_size={mcs}")

    print("  clustering with HDBSCAN ...")
    labels = cluster_points(xy, min_cluster_size=mcs)
    n_clusters = int(labels.max() + 1)
    n_noise = int((labels == -1).sum())
    print(f"  found {n_clusters} clusters (+{n_noise} noise papers)")

    print("  labeling clusters (c-TF-IDF) ...")
    names = label_clusters(df, labels)

    topic_map = df.copy()
    topic_map["x"] = xy[:, 0]
    topic_map["y"] = xy[:, 1]
    topic_map["cluster"] = labels
    topic_map["label"] = [names[c] for c in labels]
    topic_map["mcs_used"] = mcs                    # so reports know which granularity ran

    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    out_path = config.DATA_PROCESSED / "topic_map.parquet"
    topic_map.to_parquet(out_path, index=False)
    print(f"\nSaved topic map ({len(topic_map)} papers) to:\n  {out_path}")
    return topic_map


def load_topic_map(folder=None) -> pd.DataFrame:
    """Reload the saved topic map (for visualize.py and the web app).

    `folder` pins WHICH topic's map to read; omitted it uses the active topic's folder.
    See embed.load_embeddings for why the app always passes it.
    """
    base = config.DATA_PROCESSED if folder is None else folder
    return pd.read_parquet(base / "topic_map.parquet")


if __name__ == "__main__":
    from . import embed

    df = pd.read_parquet(config.DATA_PROCESSED / "papers.parquet")
    vectors = embed.load_embeddings()
    topic_map = build_topic_map(df, vectors)

    print("\nClusters:")
    summary = topic_map.groupby(["cluster", "label"]).size().reset_index(name="papers")
    for _, r in summary.iterrows():
        print(f"  [{r['cluster']:>2}] {r['papers']:>3} papers - {r['label']}")
