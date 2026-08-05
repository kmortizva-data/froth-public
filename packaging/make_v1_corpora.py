"""
make_v1_corpora.py - build the v1 edition's corpora from the ones already on disk.

v1 ships the CORE of each topic (~250 papers), the size where every view stays readable
and the physics-based network is at its best. Nothing is harvested again: the papers and
their SPECTER vectors already exist from the uncapped run, so this only SELECTS, RE-EMBEDS
and RE-MAPS.

Two things here are decided by measurement rather than by a default:

1. WHICH 250 papers. Two candidates are built for every topic and the better one wins:
     - "top": the 250 most relevant papers.
     - "strata": 250 allocated across the big map's own subtopics in proportion to their
       size, most relevant first inside each.
   "top" sounds obviously right and often is not: it concentrates on the core, the
   periphery disappears, and HDBSCAN then calls 30-52% of the papers noise because what
   is left is one homogeneous blob. But "strata" is not a universal win either (on
   process-mineralogical it went 0% -> 34% noise), so the choice is made per corpus.

2. WHICH MODEL. The stored vectors come from the local fine-tune (specter-mineral-v1).
   The v1 edition ships no models/ folder, so its app embeds search queries with stock
   SPECTER from the hub. Shipping fine-tune vectors would leave the corpus and the
   queries in two different spaces, quietly degrading search - so everything is
   re-embedded with the model v1 actually runs.

Run (from the main worktree):
    .venv\\Scripts\\python.exe packaging\\make_v1_corpora.py
"""
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hdbscan
import numpy as np
import pandas as pd

from froth import config

config.EMBEDDING_MODEL = "allenai-specter"         # pin BEFORE the model loads

from froth import cluster as cl                                        # noqa: E402
from froth import embed                                                # noqa: E402

V1_ROOT = Path(r"C:\Users\Bruce Wayne\Documents\froth-v1core")
TARGET_N = 250
DROPPED = {"cluster-dropped", "noise-dropped"}
# Readability is the CONSTRAINT, cluster quality is the objective: a candidate is only
# eligible if it leaves less than this fraction of the papers unassigned (grey dots),
# and among the eligible ones the best DBCV wins. If neither candidate clears the bar,
# the least grey one takes it.
#
# The first version of this rule was the other way round (best DBCV first, noise as the
# tie-break) and it produced a map with 88 of 250 papers grey in exchange for moving
# DBCV from 0.100 to 0.156 - two numbers that are both bad. A map where a third of the
# papers belong to nothing is not a map.
MAX_NOISE_FRACTION = 0.30


def _gate_survivors(df: pd.DataFrame, vectors: np.ndarray):
    """Drop what the contrastive gate already judged junk (whole off-topic hubs)."""
    if "relevance_gate" not in df.columns:
        return df, vectors
    keep = ~df["relevance_gate"].isin(DROPPED)
    return df[keep], vectors[keep.to_numpy()]


def pick_top(df: pd.DataFrame, n: int = TARGET_N) -> pd.Index:
    """Candidate 1: the n most relevant papers."""
    return df.nlargest(min(n, len(df)), "relevance").index


def pick_strata(df: pd.DataFrame, tmap: pd.DataFrame, n: int = TARGET_N) -> pd.Index:
    """Candidate 2: n papers spread over the big map's subtopics in proportion to size."""
    cluster_of = dict(zip(tmap["id"], tmap["cluster"]))
    sub = df[df["id"].isin(cluster_of)].copy()
    sub["_c"] = sub["id"].map(cluster_of)
    sub = sub[sub["_c"] != -1]                     # the big map's noise stays out
    if sub.empty:
        return pick_top(df, n)
    sizes = sub["_c"].value_counts()
    quota = (sizes / sizes.sum() * n).round().astype(int).clip(lower=3)
    picks = [sub[sub["_c"] == c].nlargest(min(q, int(sizes[c])), "relevance")
             for c, q in quota.items()]
    return pd.concat(picks).nlargest(min(n, len(sub)), "relevance").index


def evaluate(vectors: np.ndarray) -> dict:
    """Map a candidate the way the app will and report how readable the result is."""
    xy = cl.reduce_to_2d(vectors)
    best = None
    for m in range(3, 21):
        c = hdbscan.HDBSCAN(min_cluster_size=m, gen_min_span_tree=True).fit(xy)
        k = int(c.labels_.max() + 1)
        if k >= 2 and (best is None or c.relative_validity_ > best["dbcv"]):
            best = {"mcs": m, "clusters": k, "noise": int((c.labels_ == -1).sum()),
                    "dbcv": float(c.relative_validity_)}
    return best or {"mcs": 3, "clusters": 0, "noise": len(vectors), "dbcv": 0.0}


def choose(cands: dict) -> str:
    """Readable enough to be a map first, then the best clustering among those."""
    ok = {k: c for k, c in cands.items()
          if c["noise"] / max(c["n"], 1) < MAX_NOISE_FRACTION}
    if ok:
        return max(ok, key=lambda k: ok[k]["dbcv"])
    return min(cands, key=lambda k: cands[k]["noise"] / max(cands[k]["n"], 1))


def write_topic(small: pd.DataFrame, small_v: np.ndarray, dst_p: Path, dst_e: Path):
    """Save the chosen corpus and build its map with the engine the app uses."""
    dst_p.mkdir(parents=True, exist_ok=True)
    dst_e.mkdir(parents=True, exist_ok=True)
    # v1 does not re-gate: it inherits the selection made here, so relevance is re-based
    # to sit comfortably above the app's threshold.
    small = small.copy()
    small["relevance"] = np.linspace(0.95, 0.60, len(small))
    small = small.drop(columns=[c for c in ("relevance_gate", "relevance_v1",
                                            "relevance_v2", "cluster_v2_mean",
                                            "relevance_valley") if c in small.columns])
    small.to_parquet(dst_p / "papers.parquet", index=False)
    np.save(dst_e / "vectors.npy", small_v)
    saved = (config.DATA_PROCESSED, config.DATA_EMBEDDINGS)
    config.DATA_PROCESSED, config.DATA_EMBEDDINGS = dst_p, dst_e
    try:
        return cl.build_topic_map(small, small_v, min_cluster_size="auto")
    finally:
        config.DATA_PROCESSED, config.DATA_EMBEDDINGS = saved


def rebuild(slug: str, src: Path, emb: Path) -> dict:
    """Build both candidates for one topic, keep the better, write it into v1."""
    t0 = time.time()
    df = pd.read_parquet(src / "papers.parquet")
    vectors = np.load(emb / "vectors.npy")
    if len(df) != len(vectors):
        return {"slug": slug, "status": "SKIP (papers/vectors mismatch)"}
    tmap = pd.read_parquet(src / "topic_map.parquet", columns=["id", "cluster"])
    df, vectors = _gate_survivors(df, vectors)

    idx = {"top": pick_top(df), "strata": pick_strata(df, tmap)}
    # Embed the union once with the public model, then slice per candidate: the two
    # selections overlap heavily and SPECTER is the expensive part.
    union = df.loc[sorted(set(idx["top"]) | set(idx["strata"]))]
    union_v = embed.embed_papers(union)
    row_of = {ix: i for i, ix in enumerate(union.index)}

    cands, frames = {}, {}
    for name, ix in idx.items():
        sel_v = union_v[[row_of[i] for i in ix]]
        frames[name] = (df.loc[ix].reset_index(drop=True), sel_v)
        cands[name] = evaluate(sel_v) | {"n": len(ix)}

    winner = choose(cands)
    small, small_v = frames[winner]
    tm = write_topic(small, small_v,
                     V1_ROOT / "2_Datos" / "topics" / slug / "processed",
                     V1_ROOT / "2_Datos" / "topics" / slug / "embeddings")
    w = cands[winner]
    return {"slug": slug, "status": "ok", "selection": winner, "papers": len(small),
            "clusters": int(tm["cluster"].max() + 1),
            "noise": int((tm["cluster"] == -1).sum()),
            "mcs": w["mcs"], "dbcv": round(w["dbcv"], 3),
            "top_noise": cands["top"]["noise"], "top_dbcv": round(cands["top"]["dbcv"], 3),
            "strata_noise": cands["strata"]["noise"],
            "strata_dbcv": round(cands["strata"]["dbcv"], 3),
            "secs": round(time.time() - t0)}


def rebuild_default() -> dict:
    """The default topic already lives at v1 size in the legacy folders: it only needs
    re-embedding with the public model so it shares the space of the other 21."""
    t0 = time.time()
    dst_p = V1_ROOT / "2_Datos" / "processed"
    dst_e = V1_ROOT / "2_Datos" / "embeddings"
    df = pd.read_parquet(dst_p / "papers.parquet")
    small_v = embed.embed_papers(df)
    tm = write_topic(df, small_v, dst_p, dst_e)
    return {"slug": "(default topic - legacy folders)", "status": "ok",
            "selection": "as harvested", "papers": len(df),
            "clusters": int(tm["cluster"].max() + 1),
            "noise": int((tm["cluster"] == -1).sum()), "secs": round(time.time() - t0)}


def main() -> None:
    rows = []
    for src in sorted((config.ROOT / "2_Datos" / "topics").glob("*/processed")):
        slug = src.parent.name
        emb = src.parent / "embeddings"
        needed = [src / "papers.parquet", src / "topic_map.parquet", emb / "vectors.npy"]
        if not all(p.exists() for p in needed):
            print(f"  skip {slug[:40]}: missing papers, vectors or map")
            continue
        row = rebuild(slug, src, emb)
        rows.append(row)
        print(f"[{len(rows):>2}] {row.get('selection', '-'):>6}  {row.get('papers', 0):>4}p  "
              f"{row.get('clusters', 0):>2} subtopics  {row.get('noise', 0):>3} noise  "
              f"(top {row.get('top_noise', '-')} / strata {row.get('strata_noise', '-')})  "
              f"{row.get('secs', 0):>3}s  {slug[:40]}", flush=True)

    rows.append(rebuild_default())
    print(f"[22] default topic: {rows[-1]['papers']} papers, "
          f"{rows[-1]['clusters']} subtopics, {rows[-1]['noise']} noise")

    shutil.copy(config.ROOT / "2_Datos" / "topics_registry.csv",
                V1_ROOT / "2_Datos" / "topics_registry.csv")
    rep = pd.DataFrame(rows)
    rep.to_csv(V1_ROOT / "2_Datos" / "v1_corpora_report.csv", index=False)
    ok = rep[rep["status"] == "ok"]
    noise_pct = 100 * ok["noise"].sum() / ok["papers"].sum()
    print(f"\nDONE: {len(ok)} topics, {int(ok['papers'].sum())} papers, "
          f"{ok['clusters'].mean():.1f} subtopics on average, {noise_pct:.0f}% noise overall.")
    if "selection" in ok:
        print("Selection chosen: " + ", ".join(f"{k}={v}" for k, v in
                                               ok["selection"].value_counts().items()))


if __name__ == "__main__":
    main()
