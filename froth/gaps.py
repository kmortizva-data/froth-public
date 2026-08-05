"""
gaps.py - PHASE 5: gap detection + literature review draft.

WHAT IT DOES (the project's differentiator):
1) find_gaps(): turns the four measurable gap types (Note 24) into a ranked candidate table
   with evidence. The tool PROPOSES with numbers; the expert decides mine vs desert.
2) draft_review(): structured literature review draft with traceable citations. (TODO: 5.2)

HOW TO RUN IT (after the full pipeline):
    .venv\\Scripts\\python.exe -m froth.gaps

Gap types and their signals:
- SILO: cluster pairs with HIGH semantic similarity but FEW cross-citations.
- SCARCE BRIDGE: related cluster pairs connected by very few bridge papers.
- DORMANT: clusters whose newest papers are old (nobody revisits them).
- SPARSE ZONE (experimental): few papers around the midpoint between two related clusters.
  Flagged experimental on purpose: it measures ABSENCE, which carries no reason with it,
  and 2D positions distort (Note 12) - weakest evidence of the four.
"""

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

from . import config
from .graph import build_similarity_graph, build_topic_graph

CURRENT_YEAR = 2026


def safe_int(value, default: int = 0) -> int:
    """int() that survives the empty year/citation cells the sources really send.

    Phase 1.5 put this guard in graph.py after finding 12 of 21 corpora with empty cells;
    review.py and this file never got it, and `int(NaN)` took down the review draft and the
    Obsidian export on the scheelite ores corpus (3 papers of 3,032 with no year). The
    paper is kept and the value reads as unknown - never invented.
    """
    try:
        return default if pd.isna(value) else int(value)
    except (TypeError, ValueError):
        return default


def _cluster_pairs(G_topics):
    """Yield (a, b, edge_data) for every subtopic pair in the topic graph."""
    for a, b, d in G_topics.edges(data=True):
        yield int(a), int(b), d


def find_gaps(topic_map: pd.DataFrame, vectors: np.ndarray) -> pd.DataFrame:
    """Rank gap candidates of the four types. Returns one table [type, where, score, evidence].

    Scores are 0..1 within each type (comparable inside a type, not across types).
    """
    tm = topic_map[topic_map["cluster"] != -1]
    labels = {int(c): tm[tm["cluster"] == c]["label"].iloc[0] for c in tm["cluster"].unique()}

    G_topics = build_topic_graph(topic_map, vectors)
    G_papers = build_similarity_graph(topic_map, vectors)

    rows = []

    # --- SILO: similar clusters that barely cite each other -------------------------
    for a, b, d in _cluster_pairs(G_topics):
        score = d["similarity"] / (1 + d["citations"])
        rows.append({
            "type": "silo",
            "where": f"{labels[a]}  <->  {labels[b]}",
            "score": round(float(score), 3),
            "evidence": f"semantic similarity {d['similarity']:.2f} but only "
                        f"{d['citations']} cross-citation(s)",
        })

    # --- SCARCE BRIDGE: few papers connect two related clusters ---------------------
    cluster_of = topic_map["cluster"].to_dict()          # node id -> cluster
    for a, b, d in _cluster_pairs(G_topics):
        bridges = []
        for n in G_papers.nodes:
            neigh = set(cluster_of[m] for m in G_papers.neighbors(n))
            if a in neigh and b in neigh:
                bridges.append(G_papers.nodes[n]["title"])
        # Fewer bridges between MORE similar clusters = bigger gap.
        score = d["similarity"] / (1 + len(bridges))
        example = f" (e.g. '{bridges[0][:50]}…')" if bridges else ""
        rows.append({
            "type": "scarce_bridge",
            "where": f"{labels[a]}  <->  {labels[b]}",
            "score": round(float(score), 3),
            "evidence": f"only {len(bridges)} bridge paper(s) despite similarity "
                        f"{d['similarity']:.2f}{example}",
        })

    # --- DORMANT: clusters whose newest work is old ----------------------------------
    for c in sorted(labels):
        part = tm[tm["cluster"] == c]
        newest = int(part["year"].max())
        recent = int((part["year"] >= CURRENT_YEAR - 5).sum())
        score = min((CURRENT_YEAR - newest) / 10, 1.0)
        rows.append({
            "type": "dormant",
            "where": labels[c],
            "score": round(float(score), 3),
            "evidence": f"newest paper {newest}; {recent}/{len(part)} papers in the last 5 years",
        })

    # --- SPARSE ZONE (experimental): emptiness between related clusters --------------
    span = max(topic_map["x"].max() - topic_map["x"].min(),
               topic_map["y"].max() - topic_map["y"].min())
    radius = 0.12 * span
    for a, b, d in _cluster_pairs(G_topics):
        ca = tm[tm["cluster"] == a][["x", "y"]].mean().to_numpy()
        cb = tm[tm["cluster"] == b][["x", "y"]].mean().to_numpy()
        mid = (ca + cb) / 2
        dist = np.sqrt(((topic_map[["x", "y"]].to_numpy() - mid) ** 2).sum(axis=1))
        in_between = int((dist <= radius).sum())
        score = d["similarity"] / (1 + in_between)
        rows.append({
            "type": "sparse_zone (experimental)",
            "where": f"{labels[a]}  <->  {labels[b]}",
            "score": round(float(score), 3),
            "evidence": f"{in_between} paper(s) near the midpoint (radius {radius:.1f} on the "
                        f"2D map - positions distort, treat with care)",
        })

    gaps = pd.DataFrame(rows).sort_values(["type", "score"], ascending=[True, False])
    gaps = gaps.reset_index(drop=True)

    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    out = config.DATA_PROCESSED / "gaps.parquet"
    gaps.to_parquet(out, index=False)
    print(f"Saved {len(gaps)} gap candidates to:\n  {out}\n")
    return gaps


def _first_author(authors: str) -> str:
    """'A. Smith; B. Jones; ...' -> 'A. Smith et al.' (or just the single author)."""
    if not authors:
        return "Unknown"
    first = authors.split(";")[0].strip()
    return f"{first} et al." if ";" in authors else first


def draft_review(topic_map: pd.DataFrame, vectors: np.ndarray,
                 gaps: pd.DataFrame | None = None) -> str:
    """Structured literature-review draft with 100% traceable citations.

    Every claim points at real corpus papers (title/year/DOI) via numbered references -
    a deterministic template, no LLM, so nothing can be hallucinated. Sections are born
    from the MEASURED structure: sections = clusters, essential reading = hubs/citations,
    research gaps = the ranked signals from find_gaps(). Saves 3_Resultados/review_draft.md.
    """
    from .graph import find_bridges

    tm = topic_map[topic_map["cluster"] != -1]
    G = build_similarity_graph(topic_map, vectors)
    degree = dict(G.degree())

    refs: list[int] = []                     # paper row-ids in citation order

    def cite(i: int) -> str:
        if i not in refs:
            refs.append(i)
        return f"[{refs.index(i) + 1}]"

    L: list[str] = []
    L.append(f"# Literature review draft - {config.TOPIC}")
    L.append("")
    L.append(f"*Generated by Froth from {len(tm)} relevant papers "
             f"({int(tm['year'].min())}–{int(tm['year'].max())}). "
             "This is a structured DRAFT with traceable citations - an expert scaffold, "
             "not final prose. Every number below is measured on the corpus.*")
    L.append("")

    # --- One section per subtopic, biggest first --------------------------------------
    for rank, c in enumerate(tm["cluster"].value_counts().index, start=1):
        part = tm[tm["cluster"] == c]
        label = part["label"].iloc[0]
        L.append(f"## {rank}. {label}")
        L.append(f"*{len(part)} papers, {int(part['year'].min())}–{int(part['year'].max())}.*")
        L.append("")

        L.append("**Essential reading (most cited):**")
        for i, r in part.sort_values("citations", ascending=False).head(3).iterrows():
            L.append(f"- {r['title']} ({safe_int(r['year'])}, {safe_int(r['citations'])} citations) {cite(i)}")
        L.append("")

        hubs = part.loc[sorted(part.index, key=lambda i: -degree.get(i, 0))].head(2)
        L.append("**Most connected within the corpus (local hubs):**")
        for i, r in hubs.iterrows():
            L.append(f"- {r['title']} ({degree.get(i, 0)} connections) {cite(i)}")
        L.append("")

        L.append("**Recent developments:**")
        for i, r in part.sort_values(["year", "citations"], ascending=False).head(3).iterrows():
            L.append(f"- {r['title']} ({safe_int(r['year'])}) {cite(i)}")
        L.append("")

    # --- Research gaps, with their measured evidence -----------------------------------
    L.append("## Research gaps (measured, expert judgment required)")
    L.append("*The tool proposes candidates with evidence; only the expert can tell an "
             "unexplored mine from a barren desert (Note 24).*")
    L.append("")
    if gaps is not None and len(gaps):
        for gap_type in ("silo", "scarce_bridge", "dormant", "sparse_zone (experimental)"):
            part = gaps[(gaps["type"] == gap_type) & (gaps["score"] > 0.02)]
            if not len(part):
                continue
            L.append(f"**{gap_type.replace('_', ' ').capitalize()}:**")
            for _, r in part.head(2).iterrows():
                L.append(f"- {r['where']} - {r['evidence']} (score {r['score']:.2f})")
            L.append("")

    # --- Bridge papers: the connectors worth reading across subtopics -------------------
    L.append("## Bridge papers (connect subtopics - where novelty lives)")
    for i, _bc in find_bridges(G, top=4):
        n = G.nodes[i]
        L.append(f"- {n['title']} ({n['year']}) {cite(i)}")
    L.append("")

    # --- Full reference list (every citation above, in order) ---------------------------
    L.append("## References")
    for pos, i in enumerate(refs, start=1):
        r = topic_map.loc[i]
        doi = f" {r['doi']}" if r.get("doi") else ""
        L.append(f"[{pos}] {_first_author(r['authors'])} ({safe_int(r['year'])}). {r['title']}.{doi}")

    text = "\n".join(L)
    config.DELIVERABLES.mkdir(parents=True, exist_ok=True)
    out = config.DELIVERABLES / "review_draft.md"
    out.write_text(text, encoding="utf-8")
    print(f"Saved review draft ({len(refs)} traceable references) to:\n  {out}")
    return text


if __name__ == "__main__":
    from . import cluster, embed

    papers = pd.read_parquet(config.DATA_PROCESSED / "papers.parquet")
    mask = (papers["relevance"] >= config.RELEVANCE_THRESHOLD).to_numpy()
    vectors = embed.load_embeddings()[mask]
    topic_map = cluster.load_topic_map()

    gaps = find_gaps(topic_map, vectors)

    for gap_type in gaps["type"].unique():
        part = gaps[gaps["type"] == gap_type]
        print(f"=== {gap_type.upper()} (top candidates) ===")
        for _, r in part.head(3).iterrows():
            print(f"  [{r['score']:.3f}] {r['where']}")
            print(f"          {r['evidence']}")
        print()

    draft_review(topic_map, vectors, gaps)
