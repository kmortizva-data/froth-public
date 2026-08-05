"""
audit_networks.py - health check for every corpus's similarity network.

Does each topic's network make sense? A healthy network is mostly ONE connected
blob (papers link up), with few loners (colored nodes with no edge = usually
off-topic intruders that slipped in via a term collision). Reports per topic:
nodes, edges, giant-component share, loners, clusters; flags giant < 75% or
loners > 12%.

Run:
    .venv\\Scripts\\python.exe packaging\\audit_networks.py
"""
import numpy as np
import pandas as pd
import networkx as nx

from froth import config, batch, embed, graph


def main() -> None:
    titles = batch.cohort_titles()
    print(f"{'papers':>6} {'edges':>6} {'giant%':>7} {'loners':>7} {'lon%':>5} "
          f"{'cl':>3}  topic")
    print("-" * 90)
    rows = []
    for title in titles:
        config.set_topic(title)
        tmp = config.DATA_PROCESSED / "topic_map.parquet"
        if not tmp.exists():
            continue
        tm = pd.read_parquet(tmp)
        df = pd.read_parquet(config.DATA_PROCESSED / "papers.parquet")
        vectors = embed.load_embeddings()
        if "relevance" in df.columns and len(vectors) == len(df):
            vectors = vectors[(df["relevance"] >= config.RELEVANCE_THRESHOLD).to_numpy()]
        if len(vectors) != len(tm):
            print(f"  SKIP misaligned {title[:40]}")
            continue
        G = graph.build_similarity_graph(tm, vectors)
        n = G.number_of_nodes()
        comps = sorted(nx.connected_components(G), key=len, reverse=True)
        giant = len(comps[0]) if comps else 0
        loners = sum(1 for i in G.nodes
                     if G.degree(i) == 0 and G.nodes[i]["cluster"] != -1)
        ncl = int(tm[tm["cluster"] != -1]["cluster"].nunique())
        flag = ""
        if n and giant / n < 0.75:
            flag += " <weak-giant>"
        if n and loners / n > 0.12:
            flag += " <many-loners>"
        print(f"{n:>6} {G.number_of_edges():>6} {100*giant/max(n,1):>6.0f}% {loners:>7} "
              f"{100*loners/max(n,1):>4.0f}% {ncl:>3}  {title[:44]}{flag}")
        rows.append(flag)
    print("-" * 90)
    print(f"{len(rows)} corpora audited; {sum(1 for f in rows if f)} flagged.")


if __name__ == "__main__":
    main()
