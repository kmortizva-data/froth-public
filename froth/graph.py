"""
graph.py - PHASE 4: the mind map (relationships between papers and topics).

WHAT IT DOES: builds a NETWORK (graph) where each paper is a node connected to its most
similar papers (kNN by cosine in the ORIGINAL 768D space, not the 2D map). Later phases add
citation edges (who cites whom) and the topic-level mind map.

HOW TO RUN IT (after pull, embed and cluster):
    .venv\\Scripts\\python.exe -m froth.graph

WHAT YOU LEARN HERE (Note 19):
- Graphs: nodes (papers) + weighted edges (similarity).
- Hubs (highly connected papers = must-read classics) via degree.
- Bridges (papers connecting communities = where novelty lives) via betweenness centrality.
"""

import numpy as np
import pandas as pd
import networkx as nx
from sklearn.metrics.pairwise import cosine_similarity

from . import config


def build_similarity_graph(topic_map: pd.DataFrame, vectors: np.ndarray,
                           k: int | None = None,
                           threshold: float | None = None) -> nx.Graph:
    """Connect each paper to its k most similar papers (cosine >= threshold).

    Row i of `vectors` must correspond to row i of `topic_map`. Node attributes carry
    title/year/cluster/label so any view can draw the graph without re-joining tables.
    """
    k = k or config.GRAPH_KNN
    threshold = threshold or config.GRAPH_SIM_THRESHOLD

    S = cosine_similarity(vectors)
    np.fill_diagonal(S, 0)               # a paper is not its own neighbor

    def _int(value, default: int = 0) -> int:
        """Metadata arrives incomplete: a paper can reach us with no year (29 such cells
        across 12 of the corpora on this machine, and any fresh harvest can bring more).
        int(NaN) raises, which used to take the whole Network view down for that topic.
        The paper is kept as harvested - we do not invent a year - it reads as unknown."""
        return default if pd.isna(value) else int(value)

    G = nx.Graph()
    for i, row in topic_map.iterrows():
        G.add_node(i, title=row["title"], year=_int(row["year"]),
                   citations=_int(row["citations"]), cluster=_int(row["cluster"]),
                   label=row["label"])
    for i in range(len(topic_map)):
        for j in np.argsort(S[i])[::-1][:k]:
            j = int(j)
            if S[i, j] >= threshold:
                G.add_edge(i, j, weight=round(float(S[i, j]), 3))
    return G


def find_hubs(G: nx.Graph, top: int = 5) -> list[tuple[int, int]]:
    """Most connected papers (degree): the must-read classics of the corpus."""
    return sorted(G.degree(), key=lambda x: -x[1])[:top]


def find_bridges(G: nx.Graph, top: int = 5) -> list[tuple[int, float]]:
    """Papers that connect communities (betweenness centrality): where novelty lives.

    Betweenness = how often a node sits on the shortest path between two other nodes.
    A paper linking two subtopics scores high even with few connections.
    """
    bc = nx.betweenness_centrality(G, weight=None)
    return sorted(bc.items(), key=lambda x: -x[1])[:top]


def build_topic_graph(topic_map: pd.DataFrame, vectors: np.ndarray) -> nx.Graph:
    """The mind map one level up: one node per SUBTOPIC, edges between subtopics.

    Node attrs: label, n_papers, total citations, centroid (x, y) for drawing.
    Edge attrs: similarity = mean cosine between the two clusters' papers (in 768D),
                citations  = how many times papers of one cluster cite papers of the other.
    Noise (-1) is excluded: it is not a subtopic.
    """
    clusters = sorted(c for c in topic_map["cluster"].unique() if c != -1)

    G = nx.Graph()
    for c in clusters:
        part = topic_map[topic_map["cluster"] == c]
        G.add_node(int(c), label=part["label"].iloc[0], n_papers=len(part),
                   citations=int(part["citations"].sum()),
                   x=float(part["x"].mean()), y=float(part["y"].mean()))

    # Map each corpus paper id to its cluster, to count cross-cluster citations.
    id_to_cluster = dict(zip(topic_map["id"], topic_map["cluster"]))

    for a in clusters:
        for b in clusters:
            if b <= a:
                continue
            ma = (topic_map["cluster"] == a).to_numpy()
            mb = (topic_map["cluster"] == b).to_numpy()
            sim = float(cosine_similarity(vectors[ma], vectors[mb]).mean())

            cites = 0
            for _, row in topic_map[ma | mb].iterrows():
                src, tgt = row["cluster"], (b if row["cluster"] == a else a)
                cites += sum(1 for r in row["references"] if id_to_cluster.get(r) == tgt)

            G.add_edge(int(a), int(b), similarity=round(sim, 3), citations=cites)
    return G


def save_graph(G: nx.Graph) -> None:
    """Persist the network in GraphML (a standard XML format networkx reads back)."""
    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    out = config.DATA_PROCESSED / "similarity_graph.graphml"
    nx.write_graphml(G, out)
    print(f"\nSaved network ({G.number_of_nodes()} nodes, {G.number_of_edges()} edges) to:\n  {out}")


def load_graph() -> nx.Graph:
    """Reload the saved network (node ids come back as strings in GraphML; relabel to int)."""
    G = nx.read_graphml(config.DATA_PROCESSED / "similarity_graph.graphml")
    return nx.relabel_nodes(G, int)


if __name__ == "__main__":
    from . import cluster, embed

    papers = pd.read_parquet(config.DATA_PROCESSED / "papers.parquet")
    mask = (papers["relevance"] >= config.RELEVANCE_THRESHOLD).to_numpy()
    vectors = embed.load_embeddings()[mask]
    topic_map = cluster.load_topic_map()

    G = build_similarity_graph(topic_map, vectors)
    save_graph(G)

    print("\n=== HUBS (most connected: the must-read classics) ===")
    for i, deg in find_hubs(G):
        print(f"  {deg:>2} connections | {G.nodes[i]['title'][:62]}")

    print("\n=== BRIDGES (connect subtopics: where novelty lives) ===")
    for i, bc in find_bridges(G):
        n = G.nodes[i]
        print(f"  score {bc:.3f} | [{n['label'][:22]}] {n['title'][:55]}")

    print("\n=== TOPIC MIND MAP (one node per subtopic) ===")
    T = build_topic_graph(topic_map, vectors)
    for c in T.nodes:
        n = T.nodes[c]
        print(f"  [{c}] {n['n_papers']:>3} papers, {n['citations']:>5} citations - {n['label']}")
    print("  relations:")
    for a, b, d in T.edges(data=True):
        la, lb = T.nodes[a]["label"][:20], T.nodes[b]["label"][:20]
        print(f"    {la} <-> {lb}: similarity {d['similarity']:.3f}, {d['citations']} citations across")
