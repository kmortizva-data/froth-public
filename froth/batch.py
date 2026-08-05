"""
batch.py - PHASE 6.2: run the whole pipeline over every cohort thesis title.

WHAT IT DOES: reads the 22 thesis titles from the cohort CSV, runs pull -> embed ->
relevance -> cluster for each one (own data folder per topic, auto granularity by DBCV),
and writes a robustness report row per topic (papers, relevant, clusters, noise, seconds,
status). The report is saved after EVERY topic, so a crash or rate limit loses nothing:
re-running skips topics that already finished (resume-friendly). Use --force to redo all.

HOW TO RUN IT:
    .venv\\Scripts\\python.exe -m froth.batch [--force]

This is the 1 -> 22 generalization ladder from the original plan: every title that breaks
something makes the CODE stronger (the model is not trained here - that is Phase 6.5).
"""

import sys
import time
from collections import Counter

import numpy as np
import pandas as pd

from . import config
from . import cluster as cl
from . import embed, pull

# Titles-only file: the original allocation sheet holds classmates' NAMES and
# stays local/gitignored (privacy); the public repo only ever sees thesis titles.
CSV = config.ROOT / "2_Datos" / "cohort_thesis_titles.csv"
REPORT = config.ROOT / "2_Datos" / "batch_report.csv"


def cohort_titles() -> list[str]:
    """The thesis titles from the allocation CSV (header has a trailing space - trimmed)."""
    df = pd.read_csv(CSV)
    df.columns = [c.strip() for c in df.columns]
    return [str(t).strip() for t in df["thesis title"].dropna() if str(t).strip()]


def run_topic(title: str, per_term: int = 15, force: bool = False) -> dict:
    """Pipeline for ONE title. Never raises: failures land in the report as FAILED."""
    t0 = time.time()
    config.set_topic(title)
    row = {"slug": config.slugify(title), "status": "ok", "error": "",
           "papers": 0, "relevant": 0, "clusters": 0, "noise": 0, "mcs": 0, "secs": 0}
    try:
        tm_path = config.DATA_PROCESSED / "topic_map.parquet"
        if tm_path.exists() and not force:
            row["status"] = "cached"
            df = pd.read_parquet(config.DATA_PROCESSED / "papers.parquet")
            tm = pd.read_parquet(tm_path)
        else:
            df = pull.pull_papers(per_term=per_term)
            if df.empty:
                # Phase A-fix: derived terms can whiff on a niche title (a rare-metal granite -> 0),
                # or the pull hit a transient blip. Retry ONCE with a broadened query before
                # giving up - self-heals any thin topic instead of dying as FAILED.
                from .terms import broaden_terms
                broad = broaden_terms(title)
                if broad:
                    print(f"  0 papers with derived terms; retrying broadened: {broad}")
                    df = pull.pull_papers(terms=broad, per_term=per_term)
                if df.empty:
                    raise RuntimeError("no papers harvested (even after broadening)")
            vectors = embed.embed_papers(df)
            embed.save_embeddings(vectors)
            df["relevance"] = embed.relevance_to_topic(vectors)
            df.to_parquet(config.DATA_PROCESSED / "papers.parquet", index=False)
            # THE GATE (note 43), not the fixed 0.55 threshold. This used to end with
            # cl.build_topic_map(), which filters papers individually against a constant.
            # Measured on the scheelite ores topic, 2026-08-03: the fixed threshold kept
            # 81 of 5,114 harvested papers and produced 2 subtopics; the contrastive
            # hub-level gate kept 438 and produced 5. Every one of the 22 cohort corpora
            # was built with remap_topic, so a freshly harvested topic was getting a map
            # far worse than any corpus already on disk, and nothing said so.
            # remap_topic maps the FULL harvest itself, so there is no earlier map to build.
            gate = remap_topic(title)
            if gate["status"] == "FAILED":
                raise RuntimeError(f"relevance gate failed: {gate['error']}")
            tm = pd.read_parquet(tm_path)
            row.update({k: gate[k] for k in
                        ("papers", "relevant", "clusters", "noise", "mcs")})
            row["secs"] = round(time.time() - t0)
            return row

        row.update(
            papers=len(df),
            relevant=int((df["relevance"] >= config.RELEVANCE_THRESHOLD).sum()),
            clusters=int(tm["cluster"].max() + 1),
            noise=int((tm["cluster"] == -1).sum()),
            mcs=int(tm["mcs_used"].iloc[0]) if "mcs_used" in tm.columns else 0,
        )
    except Exception as e:
        row["status"] = "FAILED"
        row["error"] = str(e)[:140]
    row["secs"] = round(time.time() - t0)
    return row


def reembed_topic(title: str) -> dict:
    """Re-embed ONE topic's saved harvest with the CURRENT config.EMBEDDING_MODEL (used
    when production switches models - e.g. base -> v1 after Batman's blind verdicts),
    refresh the title-similarity, drop stale gate columns, then re-run the cluster gate.
    No pull: papers.parquet is reused as-is."""
    config.set_topic(title)
    try:
        df = pd.read_parquet(config.DATA_PROCESSED / "papers.parquet")
        vectors = embed.embed_papers(df)
        embed.save_embeddings(vectors)
        stale = [c for c in ("relevance_v1", "relevance_v2", "relevance_valley",
                             "relevance_gate", "cluster_v2_mean",
                             "cluster_title_mean") if c in df.columns]
        df = df.drop(columns=stale)
        df["relevance"] = embed.relevance_to_topic(vectors)
        df.to_parquet(config.DATA_PROCESSED / "papers.parquet", index=False)
    except Exception as e:
        return {"slug": config.slugify(title), "status": "FAILED", "error": str(e)[:140],
                "papers": 0, "relevant": 0, "clusters": 0, "noise": 0, "mcs": 0, "secs": 0}
    return remap_topic(title)


def remap_topic(title: str) -> dict:
    """Phase 8.5b: CLUSTER-LEVEL contrastive gate, from the SAVED harvest (no pull/embed).

    v2.0 gated per PAPER and flattened the maps: keeping only a similarity band around
    the core left a homogeneous ball with no internal density valleys (tailings went
    115 clusters -> 2 at EVERY granularity). The junk actually arrives as coherent HUBS
    (Batman's original observation: "an HR hub, in colors"), so the gate now judges
    CLUSTERS:
      1) map EVERYTHING harvested (healthy multi-modal structure),
      2) score each cluster TWICE: mean title similarity and mean facet-contrastive score,
      3) drop a cluster only when BOTH say no (the HR hub dies entire; the mortars hub
         keeps every paper; the "lepidolite flotation" hub is rescued by the title gate
         even though the contrastive one rates it below its valley),
      4) noise papers (-1) are judged individually, against both paper-level valleys.
    The verdict is encoded back into `relevance` so every consumer keeps its
    `>= RELEVANCE_THRESHOLD` contract: papers in kept clusters land above it, papers in
    dropped clusters below. Audit columns: relevance_v1 (title), relevance_v2 (facets),
    relevance_gate (cluster-kept-both / -title / -facet, cluster-dropped, noise-kept /
    -dropped), cluster_v2_mean, cluster_title_mean. A hub marked kept-facet earned its
    place on method alone, which is where borrowed technique and silos live.
    """
    t0 = time.time()
    config.set_topic(title)
    row = {"slug": config.slugify(title), "status": "remapped", "error": "",
           "papers": 0, "relevant": 0, "clusters": 0, "noise": 0, "mcs": 0, "secs": 0}
    try:
        df = pd.read_parquet(config.DATA_PROCESSED / "papers.parquet")
        vectors = embed.load_embeddings()
        if len(df) != len(vectors):
            raise RuntimeError(f"papers ({len(df)}) != vectors ({len(vectors)})")
        title_sim = (df["relevance_v1"] if "relevance_v1" in df.columns
                     else df["relevance"]).to_numpy()
        # TWO GATES, and a hub survives if EITHER admits it (2026-08-03).
        #
        # One gate cannot do this job, because a title usually names a material AND a method
        # and those pull in opposite directions:
        #   - the single contrastive core (v2) re-picked itself twice and collapsed onto
        #     whichever idea dominated the harvest. On a corpus whose thesis is titled
        #     "FLOTATION of differently sized Li bearing mica minerals" it kept 6% of the
        #     flotation papers, and let in hubs on gender studies, osteoporosis, tritium
        #     breeder blankets and welding journals.
        #   - one core per facet (v3) fixed the coverage, 73% flotation, zero junk, but
        #     KILLED the hub literally named "lepidolite flotation" (36 papers, mean +0.378
        #     against a valley of +0.479). A very specific hub sits far from every broad
        #     core, so contrastive scoring rewards what is typical of each half and punishes
        #     what lives at the intersection, which is exactly what a thesis is about.
        #
        # So: v1 (plain title similarity) AT HUB LEVEL answers "is this subtopic my title?"
        # and rescues the intersection. Paper by paper v1 let koalas in (note 43), but the
        # MEAN of a koala hub falls below its valley, so the hub level is where it is safe.
        # v3 answers "is this subtopic one of my ideas, and not generic?" and supplies the
        # method coverage. Measured on the thesis corpus, same clustering, only the rule:
        #
        #        hubs  papers  "lepidolite flotation" hub  junk hubs  flotation  lepidolite
        #   v2    104   3,055            kept                  5          5%         70%
        #   v3    129   3,847          DROPPED                 0         56%         45%
        #   v1uv3 140   4,059            kept                  0         60%         70%
        #
        # The union wins on every column at once and recovers 26 of 26 lepidolite-flotation
        # papers. Adding the title's parenthetical elements (Ta, Nb, Be) as extra facets was
        # tried and is worse: it readmits the gender-studies hub and loses the
        # columbite-tantalite one. Facets stay exactly the phrases that drove the harvest.
        facet_score = embed.relevance_to_topic_v3(vectors)

        # 1) Map the FULL harvest - structure first, judgement after.
        df2 = df.copy()
        df2["relevance_v1"] = title_sim
        df2["relevance_v2"] = facet_score
        tm = cl.build_topic_map(df2, vectors, min_cluster_size="auto",
                                relevance_filter=False)

        # 2-3) Judge whole clusters, once per gate.
        labels = tm["cluster"].to_numpy()
        cluster_ids = sorted(c for c in set(labels) if c != -1)

        def _hub_verdict(score):
            """(hub mean by id, hub valley, per-paper valley) for one scoring rule."""
            m = {c: float(score[labels == c].mean()) for c in cluster_ids}
            hub_v = embed.auto_relevance_threshold(
                np.array([m[c] for c in cluster_ids])) if cluster_ids else 0.0
            return m, hub_v, embed.auto_relevance_threshold(score)

        m_title, valley_title, paper_valley_title = _hub_verdict(title_sim)
        m_facet, valley_facet, paper_valley_facet = _hub_verdict(facet_score)

        keep_cluster = {c: (m_title[c] >= valley_title) or (m_facet[c] >= valley_facet)
                        for c in cluster_ids}
        gate, relevance = [], []
        thr = config.RELEVANCE_THRESHOLD
        for c, s_t, s_f in zip(labels, title_sim, facet_score):
            if c != -1:
                c = int(c)
                by_title = m_title[c] >= valley_title
                by_facet = m_facet[c] >= valley_facet
                if by_title and by_facet:
                    gate.append("cluster-kept-both")
                elif by_title:
                    gate.append("cluster-kept-title")
                elif by_facet:
                    # Admitted for the method, not the subject: this is where borrowed
                    # technique from other fields lives, and where the silos are.
                    gate.append("cluster-kept-facet")
                else:
                    gate.append("cluster-dropped")
                # Encode the CLUSTER verdict so downstream `>= thr` reproduces it. Use the
                # better of the two margins, since either one alone justifies keeping.
                relevance.append(thr + max(m_title[c] - valley_title,
                                           m_facet[c] - valley_facet))
            else:
                # A stray paper belongs to no hub, and the union does NOT apply to it. The
                # title gate is only trustworthy as a hub AVERAGE: paper by paper it is the
                # rule that let koala chlamydiosis in (note 43), and measured here it admits
                # 2,229 of 2,336 strays, 95%, which is no gate at all. So a paper with no
                # group to vouch for it faces the contrastive gate alone: 1,267 kept, 54%.
                # (Requiring both gates gives 1,261, the same answer with a worse reason.)
                m_f = s_f - paper_valley_facet
                gate.append("noise-kept" if m_f >= 0 else "noise-dropped")
                relevance.append(thr + m_f)
        df2["relevance"] = relevance
        df2["relevance_gate"] = gate
        df2["cluster_v2_mean"] = [m_facet.get(int(c), np.nan) for c in labels]
        df2["cluster_title_mean"] = [m_title.get(int(c), np.nan) for c in labels]
        df2.to_parquet(config.DATA_PROCESSED / "papers.parquet", index=False)

        dropped = [c for c in cluster_ids if not keep_cluster[c]]
        names = dict(zip(tm["cluster"], tm["label"]))
        by = Counter(g for g in gate if g.startswith("cluster-kept"))
        print(f"  cluster gate: valleys title {valley_title:+.3f} / facet "
              f"{valley_facet:+.3f} -> dropped {len(dropped)}/{len(cluster_ids)} hubs, "
              f"e.g.: " + " | ".join(str(names.get(c, c))[:34] for c in dropped[:3]))
        print(f"    kept by: both {by['cluster-kept-both']} · title only "
              f"{by['cluster-kept-title']} · facet only {by['cluster-kept-facet']} papers")

        # Saved topic map = kept papers only, positions and labels from the full map.
        kept_mask = np.array([g.startswith("cluster-kept") or g == "noise-kept"
                              for g in gate])
        tm_kept = tm[kept_mask].copy()
        for col in ("relevance", "relevance_gate", "cluster_v2_mean",
                    "cluster_title_mean"):
            tm_kept[col] = df2.loc[kept_mask, col].to_numpy()
        tm_kept = tm_kept.reset_index(drop=True)
        tm_kept.to_parquet(config.DATA_PROCESSED / "topic_map.parquet", index=False)

        kept_clusters = sum(1 for c in cluster_ids if keep_cluster[c])
        row.update(papers=len(df2), relevant=int(kept_mask.sum()),
                   clusters=kept_clusters,
                   noise=int((tm_kept["cluster"] == -1).sum()),
                   mcs=int(tm["mcs_used"].iloc[0]) if "mcs_used" in tm.columns else 0)
    except Exception as e:
        row["status"] = "FAILED"
        row["error"] = str(e)[:140]
    row["secs"] = round(time.time() - t0)
    return row


def build_master_corpus() -> pd.DataFrame:
    """PHASE 6.4: fuse every topic's corpus into ONE deduplicated training set.

    Keeps only papers relevant to their own topic (each corpus was already self-cleaned),
    tags each row with its topic_slug, dedups across topics by DOI then title, and saves
    2_Datos/master_corpus.parquet - the dataset that will fine-tune SPECTER (6.5).
    """
    from .sources import _norm_doi, _norm_title

    frames = []
    legacy = config.ROOT / "2_Datos" / "processed" / "papers.parquet"
    if legacy.exists():
        d = pd.read_parquet(legacy)
        d["topic_slug"] = "default-" + config.slugify(config.DEFAULT_TOPIC)[-6:]
        frames.append(d)
    for p in sorted((config.ROOT / "2_Datos" / "topics").glob("*/processed/papers.parquet")):
        d = pd.read_parquet(p)
        d["topic_slug"] = p.parent.parent.name
        frames.append(d)

    corpus = pd.concat(frames, ignore_index=True)
    total = len(corpus)
    corpus = corpus[corpus["relevance"] >= config.RELEVANCE_THRESHOLD]
    relevant = len(corpus)

    # Cross-topic dedup: the same classic paper shows up in several thesis corpora.
    corpus["_nd"] = corpus["doi"].map(_norm_doi)
    corpus["_nt"] = corpus["title"].map(_norm_title)
    with_doi = corpus[corpus["_nd"] != ""].drop_duplicates("_nd")
    no_doi = corpus[corpus["_nd"] == ""]
    corpus = (pd.concat([with_doi, no_doi], ignore_index=True)
              .drop_duplicates("_nt").drop(columns=["_nd", "_nt"])
              .reset_index(drop=True))

    out = config.ROOT / "2_Datos" / "master_corpus.parquet"
    corpus.to_parquet(out, index=False)
    print(f"\nMaster corpus: {total} rows -> {relevant} relevant -> "
          f"{len(corpus)} unique papers. Saved to:\n  {out}")
    return corpus


if __name__ == "__main__":
    if "--master" in sys.argv:
        build_master_corpus()
        sys.exit(0)
    # Phase A-fix: run ONE topic and emit its report row as JSON on the last line. The batch
    # runner spawns this per topic in a child process with a wall-clock timeout, so a wedged
    # topic is killed instead of freezing the whole run.
    if "--one" in sys.argv:
        import json
        one_title = sys.argv[sys.argv.index("--one") + 1]
        # --reembed: re-embed with the current production model, then re-gate.
        # --remap: Phase R child - re-gate from the saved harvest instead of re-pulling.
        if "--reembed" in sys.argv:
            one_row = reembed_topic(one_title)
        elif "--remap" in sys.argv:
            one_row = remap_topic(one_title)
        else:
            one_row = run_topic(one_title, force="--force" in sys.argv)
        print("ROW_JSON:" + json.dumps(one_row))
        sys.exit(0)
    force = "--force" in sys.argv
    titles = cohort_titles()
    print(f"Cohort batch: {len(titles)} titles (force={force})\n")

    rows = []
    for i, title in enumerate(titles, start=1):
        print(f"[{i:>2}/{len(titles)}] {title[:72]}")
        row = run_topic(title, force=force)
        rows.append(row)
        print(f"     -> {row['status']} | papers={row['papers']} relevant={row['relevant']} "
              f"clusters={row['clusters']} noise={row['noise']} mcs={row['mcs']} "
              f"({row['secs']}s) {row['error']}")
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(REPORT, index=False)     # crash-safe: saved every topic
        time.sleep(2)                                      # courtesy between topics

    done = sum(1 for r in rows if r["status"] in ("ok", "cached"))
    print(f"\nBatch finished: {done}/{len(titles)} topics OK. Report:\n  {REPORT}")
