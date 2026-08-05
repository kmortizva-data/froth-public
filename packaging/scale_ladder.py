"""Where does each view actually break as the corpus grows?

Calls the REAL generators (visualize.network_html, visualize.reading_guide_html,
atlas.atlas_html) at increasing paper budgets and measures generation time, payload size,
and how many elements the browser is asked to create. Headless on purpose: browsers freeze
requestAnimationFrame in an unfocused window, so an in-app stopwatch would measure the
window manager, not the view. It also keeps the numbers clean of the app computing all six
tabs per click.

Replicates app.py's chain (filtered_state -> subtitled_state -> _cap_for_heavy_views ->
build_similarity_graph) without Streamlit, so what is measured is the shipping code path.

Usage: scale_ladder.py [mcs]
"""
import io
import re
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, r"C:\Users\Bruce Wayne\Documents\Master Thesis AI")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from froth import atlas, cluster, config, embed, graph, review, visualize

MCS = int(sys.argv[1]) if len(sys.argv) > 1 else 7
STEPS = [400, 900, 1400, 1900, 2400, 2900, 3400, None]   # None = the whole corpus
# Above this a single view stops being "slow" and becomes "do not ship": a Streamlit
# rerun that spends longer than this on one view makes the whole tab feel hung.
SLOW_S = 8.0


def build_state():
    """filtered_state + subtitled_state, without the Streamlit cache decorators."""
    paths = config.DATA_PROCESSED
    df = pd.read_parquet(paths / "papers.parquet")
    vectors = embed.load_embeddings()
    topic_map = cluster.load_topic_map()

    rel = (df["relevance"] >= config.RELEVANCE_THRESHOLD).to_numpy()
    v_rel = vectors[rel]

    xy = topic_map[["x", "y"]].to_numpy()
    labels = cluster.cluster_points(xy, min_cluster_size=MCS)
    names = cluster.label_clusters(topic_map, labels)
    tm = topic_map.copy()
    tm["cluster"] = labels
    tm["label"] = [names[c] for c in labels]

    subs = review.cluster_subtitles(tm, v_rel)
    tm["keywords"] = tm["label"]
    tm["label"] = [subs.get(int(c), (l, ""))[0] for c, l in zip(tm["cluster"], tm["label"])]
    tm["summary"] = [subs.get(int(c), ("", ""))[1] for c in tm["cluster"]]
    return tm, v_rel


def cap(tm, v, budget):
    """app._cap_for_heavy_views with the budget passed in instead of read from config."""
    if budget is None or len(tm) <= budget:
        return tm.reset_index(drop=True), v, False
    weight = tm.groupby("cluster")["citations"].sum().sort_values(ascending=False)
    parts, left = [], budget
    for c in weight.index:
        if c == -1 or left <= 0:
            continue
        part = tm[tm["cluster"] == c]
        if len(part) > left:
            part = part.nlargest(left, "citations")
        parts.append(part)
        left -= len(part)
    keep = pd.concat(parts).index.to_numpy() if parts else tm.index[:budget].to_numpy()
    return tm.loc[keep].reset_index(drop=True), v[keep], True


def timed(fn):
    t0 = time.perf_counter()
    out = fn()
    return out, time.perf_counter() - t0


tm_full, v_full = build_state()
print(f"CORPUS: {len(tm_full)} papers mapeados · "
      f"{tm_full['cluster'].nunique() - 1} subtemas · "
      f"{int((tm_full['cluster'] == -1).sum())} ruido · mcs={MCS}\n")

hdr = (f"{'papers':>7} | {'NETWORK gen':>12} {'nodos':>6} {'HTML':>8} | "
       f"{'PACKED gen':>11} {'circ':>6} {'HTML':>8} | {'ATLAS gen':>10} {'pts':>6} {'HTML':>8}")
print(hdr)
print("-" * len(hdr))

rows = []
for budget in STEPS:
    tm, v, _ = cap(tm_full, v_full, budget)
    n = len(tm)

    # NETWORK: graph build + pyvis html (physics runs in the browser, O(n^2) per frame)
    (G, t_graph) = timed(lambda: graph.build_similarity_graph(tm, v))
    G.remove_nodes_from([i for i in list(G.nodes) if G.degree(i) == 0])
    net_nodes = len(G.nodes)
    net_edges = len(G.edges)
    try:
        net_html, t_net = timed(lambda: visualize.network_html(G))
        net_bytes = len(net_html)
    except Exception as e:
        t_net, net_bytes = float("nan"), 0
        print(f"  !! network fallo a {n}: {type(e).__name__}: {str(e)[:60]}")
    t_net_total = t_graph + t_net

    # PACKED (reading guide): one SVG circle per paper, animated
    try:
        (guide, _h), t_pack = timed(lambda: visualize.reading_guide_html(tm))
        pack_bytes = len(guide)
        pack_circles = guide.count("circle")
    except Exception as e:
        t_pack, pack_bytes, pack_circles = float("nan"), 0, 0
        print(f"  !! packed fallo a {n}: {type(e).__name__}: {str(e)[:60]}")

    # ATLAS: WebGL points, no DOM node per paper
    try:
        atl, t_atl = timed(lambda: atlas.atlas_html(tm))
        atl_bytes = len(atl)
    except Exception as e:
        t_atl, atl_bytes = float("nan"), 0
        print(f"  !! atlas fallo a {n}: {type(e).__name__}: {str(e)[:60]}")

    print(f"{n:7d} | {t_net_total:11.2f}s {net_nodes:6d} {net_bytes/1024:7.0f}k | "
          f"{t_pack:10.2f}s {pack_circles:6d} {pack_bytes/1024:7.0f}k | "
          f"{t_atl:9.2f}s {n:6d} {atl_bytes/1024:7.0f}k")
    rows.append(dict(papers=n, net_s=t_net_total, net_nodes=net_nodes, net_edges=net_edges,
                     net_kb=net_bytes / 1024, pack_s=t_pack, pack_circles=pack_circles,
                     pack_kb=pack_bytes / 1024, atlas_s=t_atl, atlas_kb=atl_bytes / 1024))

d = pd.DataFrame(rows)
out = r"C:\Users\Bruce Wayne\Documents\Master Thesis AI\2_Datos\scale_ladder.csv"
d.to_csv(out, index=False)

print(f"\n{'=' * 78}\nVEREDICTO (umbral 'no shippeable' = {SLOW_S}s de generacion)\n")
for view, tcol, label in [("NETWORK", "net_s", "nodos"), ("PACKED", "pack_s", "circulos"),
                          ("ATLAS", "atlas_s", "puntos")]:
    bad = d[d[tcol] > SLOW_S]
    if len(bad):
        first = bad.iloc[0]
        prev = d[d.papers < first.papers]
        safe = int(prev.papers.max()) if len(prev) else 0
        print(f"  {view:8} se pasa de {SLOW_S}s a los {int(first.papers)} papers "
              f"({first[tcol]:.1f}s) -> tope seguro medido: {safe}")
    else:
        print(f"  {view:8} aguanta TODO el corpus ({int(d.papers.max())} papers, "
              f"max {d[tcol].max():.1f}s)")
print(f"\nCSV: {out}")
