"""
visualize.py - the pretty face: the interactive bubble map.

WHAT IT DOES: turns the topic map table (from cluster.py) into an interactive Plotly chart:
one point per paper, one color per subtopic, cluster labels on the map, and hover with
title/year/authors/citations. Zoom, pan and clickable legend come free with Plotly.
Saves a self-contained .html in 3_Resultados/ that opens in any browser.

HOW TO RUN IT (after pull, embed and cluster):
    .venv\\Scripts\\python.exe -m froth.visualize

Design principles:
- One COLOR per cluster; noise in light gray, smaller.
- Point SIZE = citations (sqrt-scaled so giants don't crush the rest) - optional.
- On hover: title, year, authors, citations, cluster label.
- Clean background, no axis numbers (UMAP axes carry no meaning).
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from . import config

# App <-> engine handshake: app.py refuses to run against an older in-memory module
# (with the file watcher off, a server started mid-update keeps stale imports and
# crashes with confusing TypeErrors - lived through it on 2026-07-18). Bump this when
# a view function's signature changes.
UI_CONTRACT = 3

# Fixed palette: color follows the cluster id, consistent across views.
PALETTE = ["#378ADD", "#EF9F27", "#1D9E75", "#D4537E", "#7F77DD",
           "#D85A30", "#639922", "#E24B4A", "#5F5E5A", "#0F6E56"]
NOISE_COLOR = "#C9C9C9"


def short(text: str, n: int = 70) -> str:
    """One truncation rule for EVERY view (Batman's spec): hard cap + ellipsis.
    Full titles belong only in the detail panel's citations (those must be complete)."""
    text = str(text or "")
    return text if len(text) <= n else text[:n].rstrip() + "…"


def _hover_text(row: pd.Series) -> str:
    """Build the tooltip shown when the mouse rests on a paper."""
    return (f"<b>{short(row['title'])}</b><br>{short(row['authors'], 60)}<br>"
            f"{row['year']} · {row['citations']} citations<br>"
            f"<i>{short(row['label'], 45)}</i>")


def bubble_figure(topic_map: pd.DataFrame,
                  size_by_citations: bool = True,
                  hide_noise: bool = False) -> go.Figure:
    """Build the interactive bubble map figure from a topic map table.

    Expects columns: title, year, citations, authors, x, y, cluster, label.
    Reused by both the saved HTML (plot_bubbles) and the web app tab.
    """
    fig = go.Figure()

    for c in sorted(topic_map["cluster"].unique()):
        part = topic_map[topic_map["cluster"] == c]
        is_noise = c == -1
        if is_noise and hide_noise:
            continue

        if size_by_citations:
            # sqrt scale: a 500-citation classic stands out without crushing everyone else.
            sizes = 6 + 2.2 * np.sqrt(part["citations"].clip(lower=0))
        else:
            sizes = np.full(len(part), 10.0)

        fig.add_trace(go.Scatter(
            x=part["x"], y=part["y"],
            mode="markers",
            name=("noise" if is_noise else part["label"].iloc[0]),
            text=[_hover_text(r) for _, r in part.iterrows()],
            hoverinfo="text",
            customdata=part.index,     # row id travels with the point -> click events know the paper
            marker=dict(
                size=sizes,
                color=(NOISE_COLOR if is_noise else PALETTE[int(c) % len(PALETTE)]),
                opacity=0.5 if is_noise else 0.85,
                line=dict(width=0.5, color="white"),
            ),
        ))

        # Cluster name floating at the cluster's center of mass.
        if not is_noise:
            fig.add_annotation(
                x=part["x"].mean(), y=part["y"].mean(),
                text=f"<b>{part['label'].iloc[0]}</b>",
                showarrow=False, font=dict(size=13, color="#fafafa"), opacity=0.95,
                bgcolor="rgba(39,39,42,0.85)", borderpad=4,
            )

    # UMAP axes carry no meaning -> no ticks, no grid, no titles.
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#18181b", plot_bgcolor="#18181b",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=10, r=10, t=10, b=10),
        height=650,
        # Unified WHITE brick tooltip across every view (matches the network's).
        hoverlabel=dict(bgcolor="#ffffff", bordercolor="#d4d4d8",
                        font=dict(color="#18181b", size=13), align="left"),
    )
    return fig


def plot_bubbles(topic_map: pd.DataFrame, out_html=None) -> str:
    """Render the bubble map and save it as a self-contained HTML file."""
    fig = bubble_figure(topic_map)
    config.DELIVERABLES.mkdir(parents=True, exist_ok=True)
    out_html = out_html or (config.DELIVERABLES / "topic_map.html")
    fig.write_html(out_html, include_plotlyjs=True)
    print(f"Saved interactive bubble map to:\n  {out_html}")
    return str(out_html)


# Runtime polish injected into the pyvis page (vis.js API). Two upgrades:
# 1) setOptions: dark-friendly smooth curved edges, hover highlighting, tuned physics.
# 2) Focus mode (the ResearchRabbit feel): selecting a node keeps it and its neighbors
#    bright while the rest of the network fades; deselecting restores everything.
_NETWORK_POLISH_JS = """
<style>
/* Kill pyvis' white page + light-gray canvas border (Batman: "weird white frame"):
   the network div is 760px tall inside a taller frame, so the white body showed.
   overflow:hidden kills the vertical scrollbar Batman disliked (content edged past
   the frame height). */
html, body { background: #18181b !important; margin: 0 !important;
             overflow: hidden !important; height: 100% !important; }
#mynetwork { border: none !important; }
/* Game-style navigation buttons (Batman's spec: simple videogame feel, kill the default
   green vis.js sprites). Chunky press effect via hard shadow + translate. */
div.vis-network div.vis-navigation div.vis-button {
  background-image: none !important;
  width: 36px; height: 36px; border-radius: 10px;
  background-color: #27272a; border: 1px solid #4f46e5;
  box-shadow: 0 3px 0 #101012;
  color: #a5b4fc; font-size: 18px; font-weight: 700;
  text-align: center; line-height: 34px; cursor: pointer;
}
div.vis-network div.vis-navigation div.vis-button:hover {
  background-color: #312e81; color: #e0e7ff;
}
div.vis-network div.vis-navigation div.vis-button:active {
  transform: translateY(3px); box-shadow: 0 0 0 #101012;
}
div.vis-button.vis-up::after      { content: '\\2191'; }
div.vis-button.vis-down::after    { content: '\\2193'; }
div.vis-button.vis-left::after    { content: '\\2190'; }
div.vis-button.vis-right::after   { content: '\\2192'; }
div.vis-button.vis-zoomIn::after  { content: '+'; }
div.vis-button.vis-zoomOut::after { content: '\\2212'; }
div.vis-button.vis-zoomExtends::after { content: '\\2302'; }
/* Brick tooltip, unified WHITE across every view (Batman's spec): capped width so the
   text wraps into a block; pre-wrap honors the title/meta line breaks. */
div.vis-tooltip {
  white-space: pre-wrap !important;
  max-width: 300px;
  background-color: #ffffff !important;
  color: #18181b !important;
  border: 1px solid #d4d4d8 !important;
  border-radius: 10px !important;
  padding: 10px 12px !important;
  font-family: Inter, 'Segoe UI', sans-serif !important;
  font-size: 13px !important;
  line-height: 1.45 !important;
}
</style>
<script type="text/javascript">
network.setOptions({
  nodes: {borderWidth: 1, font: {size: 0}},
  edges: {color: {inherit: "both", opacity: 0.35},
          smooth: {enabled: true, type: "continuous"},
          width: 1, hoverWidth: 2.5, selectionWidth: 2.5},
  interaction: {hover: true, hoverConnectedEdges: true, selectConnectedEdges: true,
                tooltipDelay: 100, zoomSpeed: 0.7,
                navigationButtons: true, keyboard: false},
  // NOTE: physics is NOT set here. It is configured in Python before the network is
  // built (see network_html), because by the time this script runs vis.js has already
  // started simulating - setting it here was always a correction, never the setting.
  // Setting it here also silently dropped avoidOverlap, which is what keeps the bubbles
  // from sitting on top of each other.
});
var ORIG_COLORS = {};
nodes.get().forEach(function(n) { ORIG_COLORS[n.id] = n.color; });
var FADED = {background: "rgba(120,120,120,0.10)", border: "rgba(120,120,120,0.05)"};
function resetAll() {
  network.unselectAll();
  nodes.update(nodes.get().map(function(n) { return {id: n.id, color: ORIG_COLORS[n.id]}; }));
}
var selectTimer = null;
network.on("selectNode", function(params) {
  var keep = new Set(network.getConnectedNodes(params.nodes[0]));
  keep.add(params.nodes[0]);
  nodes.update(nodes.get().map(function(n) {
    return {id: n.id, color: keep.has(n.id) ? ORIG_COLORS[n.id] : FADED};
  }));
  // Phase 7.9: tell the host page WHICH paper was picked (the bridge turns it
  // into the Know-more panel). DEFERRED 350ms: the first click of a
  // double-click also fires selectNode, and posting immediately reruns
  // Streamlit mid-gesture - the zoom animation would stutter or die.
  if (selectTimer) clearTimeout(selectTimer);
  selectTimer = setTimeout(function() {
    try { window.parent.postMessage({frothSelect: params.nodes[0]}, "*"); } catch (e) {}
  }, 650);                                        // let the spotlight fade finish first
});
network.on("deselectNode", resetAll);
// Auto-fit that cannot be missed: the stabilization event may have fired BEFORE this
// script attached (race condition), so we also fit on a timer - but never after the
// user has started interacting (their zoom/pan wins).
var userInteracted = false;
var animating = false;                             // a camera tween is in flight
network.on("animationFinished", function() { animating = false; });
network.on("dragStart", function() { userInteracted = true; });
network.on("zoom", function() { userInteracted = true; });
// A click IS interaction (Fix-pack 3): the click -> rerun -> layout-shift chain used to
// trigger an auto-fit that collapsed the spotlight animation.
network.on("click", function() { userInteracted = true; });
function goHome() {
  if (userInteracted) return;
  resetAll();
  animating = true;
  network.fit({animation: {duration: 700, easingFunction: "easeInOutQuad"}});
}
network.once("stabilizationIterationsDone", goHome);
setTimeout(goHome, 600);
setTimeout(goHome, 2500);
// SIZE WATCHDOG (Batman: nav buttons + double-click "failing"): Streamlit renders
// every tab up front, so the network can initialize inside a HIDDEN panel and
// freeze at a bogus canvas width (seen: 266px instead of ~1100). Broken geometry
// breaks hit-testing - clicks and buttons miss. Re-measure whenever our page box
// actually changes, and re-frame unless the user already took the wheel.
var lastW = document.documentElement.clientWidth;
function ensureSize() {
  var w = document.documentElement.clientWidth;
  // 24px threshold: Streamlit's scrollbar jitter is ~17px and used to re-trigger this
  // constantly; and NEVER resize mid-tween - setSize was the animation collapser
  // (click -> rerun -> Know-more panel appears -> width shifts -> boom).
  if (Math.abs(w - lastW) < 24) return;
  if (animating) return;
  lastW = w;
  var pos = network.getViewPosition(), sc = network.getScale();
  network.setSize("100%", "760px");
  network.redraw();
  if (userInteracted) {
    network.moveTo({position: pos, scale: sc});    // restore the camera, no surprises
  } else {
    network.fit();
  }
}
window.addEventListener("resize", ensureSize);
if (window.ResizeObserver) {
  new ResizeObserver(ensureSize).observe(document.documentElement);
}
setInterval(ensureSize, 1200);                    // belt and braces: hidden->shown

network.on("doubleClick", function(params) {
  if (selectTimer) clearTimeout(selectTimer);      // double-click wins: no rerun
  userInteracted = true;                           // auto-fit must never fight the tween
  animating = true;
  if (params.nodes.length === 0) {
    network.fit({animation: {duration: 600, easingFunction: "easeInOutQuad"}});
  } else {
    // RELATIVE zoom (Batman: the absolute 1.6 jumped weirdly from far out): step in
    // from wherever the camera is, capped so repeated double-clicks converge sanely.
    var target = Math.min(Math.max(network.getScale() * 2.2, 1.2), 8);
    network.focus(params.nodes[0], {scale: target,
                                    animation: {duration: 600, easingFunction: "easeInOutQuad"}});
  }
});
// ISLAND LEGENDS (Batman 2026-07-17): each cluster's KeyBERT name floats at its center
// of mass. The canvas draws in WORLD units, so everything is divided by the current
// zoom scale - the chip reads the SAME size on screen at any zoom (his fix request).
var CLUSTER_LABELS = __CLUSTER_LABELS__;
network.on("afterDrawing", function(ctx) {
  var s = network.getScale() || 1;
  var fpx = 13 / s, pad = 9 / s, h = 24 / s, r = 9 / s;
  ctx.save();
  ctx.font = "600 " + fpx + "px Inter, 'Segoe UI', sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  Object.keys(CLUSTER_LABELS).forEach(function(lab) {
    var ids = CLUSTER_LABELS[lab];
    var pos = network.getPositions(ids);
    var sx = 0, sy = 0, n = 0;
    ids.forEach(function(id) { if (pos[id]) { sx += pos[id].x; sy += pos[id].y; n++; } });
    if (n < 3) return;                             // tiny scraps: no legend
    var x = sx / n, y = sy / n;
    var w = ctx.measureText(lab).width + 2 * pad;
    ctx.fillStyle = "rgba(24,24,27,0.82)";
    ctx.beginPath();
    ctx.moveTo(x - w / 2 + r, y - h / 2);
    ctx.arcTo(x + w / 2, y - h / 2, x + w / 2, y + h / 2, r);
    ctx.arcTo(x + w / 2, y + h / 2, x - w / 2, y + h / 2, r);
    ctx.arcTo(x - w / 2, y + h / 2, x - w / 2, y - h / 2, r);
    ctx.arcTo(x - w / 2, y - h / 2, x + w / 2, y - h / 2, r);
    ctx.fill();
    ctx.fillStyle = "#fafafa";
    ctx.fillText(lab, x, y);
  });
  ctx.restore();

  // SEED MARKER (Batman 2026-07-20): a small pin floating just above the seed bubble.
  // Drawn AFTER vis.js has already painted every node with its normal colour and size -
  // this call never touches those, and never moves the seed or its neighbors. Fixed
  // on-screen size (divided by scale, same trick as the legend text above) so it reads
  // the same at any zoom; white fill + dark outline so it stands out on any cluster hue.
  var SEED_ID = __SEED_ID__;
  if (SEED_ID !== null) {
    var sp = network.getPositions([SEED_ID])[SEED_ID];
    var sn = network.body.data.nodes.get(SEED_ID);
    if (sp && sn) {
      var rad = sn.size || 10, mw = 11 / s, mh = 15 / s, gap = 4 / s;
      var tipY = sp.y - rad - gap;               // the pin's TIP touches just above the bubble
      ctx.save();
      ctx.fillStyle = "#fafafa";
      ctx.strokeStyle = "#18181b";
      ctx.lineWidth = 2 / s;
      ctx.beginPath();
      ctx.moveTo(sp.x, tipY);
      ctx.lineTo(sp.x - mw, tipY - mh);
      ctx.lineTo(sp.x + mw, tipY - mh);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
      ctx.restore();
    }
  }
});
// Physics is never switched off any more (ported from v1, 2026-08-13). It used to be, to
// stop the canvas twitching - but that also removed the spring: you dragged a paper and it
// just stayed where you dropped it, dead. minVelocity (set in Python, see network_html)
// makes the solver fall asleep by itself when the map is quiet and wake up on a drag, so
// the map settles, costs nothing at rest, and still pulls a dragged paper back to where its
// neighbours want it.
// The rule that DID matter is kept: nothing calls setOptions on physics after load, because
// a setOptions fired mid-tween was what killed the camera animations.
// FIXED LEGEND ZONE (Batman: "que estamos mostrando y que ocultando"): DOM overlay,
// constant position and size, listing drawn hubs with their colors + hidden counts.
var SUMMARY = __NET_SUMMARY__;
(function() {
  var box = document.createElement("div");
  box.style.cssText = "position:absolute;left:10px;top:10px;max-width:240px;" +
    "background:rgba(24,24,27,.88);border:1px solid #2e2e34;border-radius:12px;" +
    "padding:9px 12px;font:11.5px Inter,'Segoe UI',sans-serif;color:#d4d4d8;z-index:9;";
  var rows = "<div style='color:#a1a1aa;text-transform:uppercase;font-size:10px;" +
    "letter-spacing:.05em;margin-bottom:5px;'>Showing</div>";
  SUMMARY.chips.forEach(function(c) {
    rows += "<div style='display:flex;align-items:center;gap:6px;margin:2px 0;'>" +
      "<span style='width:9px;height:9px;border-radius:50%;background:" + c[1] +
      ";flex:none;'></span><span style='flex:1;'>" + c[0] + "</span></div>";
  });
  SUMMARY.lines.forEach(function(t) {
    rows += "<div style='color:#71717a;margin-top:5px;'>" + t + "</div>";
  });
  box.innerHTML = rows;
  document.body.appendChild(box);
})();
</script>
"""


def network_html(G, colors: dict[int, str] | None = None,
                 positions: dict[int, tuple[float, float]] | None = None,
                 summary_lines: list[str] | None = None,
                 seed_id: int | None = None) -> str:
    """Interactive force-directed network of papers (pyvis): drag nodes, physics, hover.

    Dark theme + focus mode: click a node to spotlight it and its neighbors (the rest
    fades), click empty space to restore. Returns a self-contained HTML string usable
    both as a saved file and inside the Streamlit app via components.html().

    `colors` maps cluster id -> hex. Without it, the legacy 10-color PALETTE recycles
    with `% len` - fine at ~10 clusters, but at 40-115 (uncapped era) seven subtopics
    share one purple and the map reads as confetti (Batman's screenshot, 2026-07-16).
    Callers with many clusters should pass palette.territory_hues-based mappings.

    `positions` maps node id -> UMAP (x, y): SEMANTIC SEEDING (Batman 2026-07-17: "el
    circulo encerrado no hace que hubs colindantes se relacionen"). Physics alone only
    knows edges, so hubs with few cross-links land at RANDOM spots around a ball and
    adjacency means nothing. Seeded with UMAP coordinates (and central gravity off, see
    the polish JS), every hub starts at its semantic place and the springs only refine
    locally - neighboring hubs really are related, and the outline is the free shape of
    the cloud instead of an enclosing circle.
    """
    from pyvis.network import Network

    from collections import Counter

    net = Network(height="760px", width="100%", cdn_resources="in_line",
                  bgcolor="#18181b", font_color="#fafafa")

    # BOUNDARY papers (Batman flagged them twice: "a yellow living among the blues"):
    # nodes whose neighbors mostly belong to ANOTHER cluster. Clusters are cut in 2D,
    # springs act in 768D - the few disagreements are papers straddling two conversations.
    # Mark them honestly: dashed ring in the neighborhood's color + a tooltip note.
    #
    # A bridge paper is one with a real share of its kinship on the OTHER side, not one that
    # is merely misfiled. The rule used to demand that ONE other subtopic hold 60% of the
    # neighbours, which misses the purest case of all: a paper split evenly between two
    # islands. Ported from v1 and RE-MEASURED here rather than inherited (rule 9): on the
    # 5752-paper thesis corpus the share of neighbours outside one's own subtopic is 0 for
    # 175 of 232 drawn papers and still 0 at the 75th percentile, then climbs to 0.40 at the
    # 90th. 0.35 sits in that empty space between the bulk and the tail and picks out 10.8%
    # of the papers as landmarks - v1 measured ~9% on its own corpus, so the cut travels.
    BRIDGE_OUTSIDE_SHARE = 0.35
    boundary = {}
    for i in G.nodes:
        c = G.nodes[i]["cluster"]
        neigh = [G.nodes[m]["cluster"] for m in G.neighbors(i)
                 if G.nodes[m]["cluster"] != -1]
        if c == -1 or not neigh:
            continue
        outside = [x for x in neigh if x != c]
        if len(outside) / len(neigh) >= BRIDGE_OUTSIDE_SHARE:
            boundary[i] = int(Counter(outside).most_common(1)[0][0])

    # LONERS (Batman's "green nodes flying free"): a colored node with NO edge means
    # no paper in the corpus reaches the similarity threshold with it. In a healthy
    # corpus that is rare; when it happens it is usually an off-topic intruder that
    # slipped past relevance via a term collision (e.g. "attrition" = grinding here,
    # but also staff turnover / medical wear). We do NOT lower the edge threshold to
    # connect them (that fabricates false kinship) - we FLAG them: dashed gray ring
    # + a tooltip, so the reader can judge. Noise (-1) is already gray, skip it.
    loners = {i for i in G.nodes
              if G.degree(i) == 0 and G.nodes[i]["cluster"] != -1}

    # Fewer nodes -> bigger dots (Batman: 700 points read as dust on a full canvas).
    size_bonus = 5.0 if len(G.nodes) < 500 else (3.0 if len(G.nodes) < 900 else 0.0)
    # BRIDGE PAPERS LAST. vis.js paints nodes in insertion order, so a boundary paper added
    # early ends up UNDER its neighbours - and those are the most interesting papers on the
    # map (they are the ones sitting between two subtopics). Adding them last puts them on
    # top, where they can be seen and clicked.
    ordered = [i for i in G.nodes if i not in boundary] + \
              [i for i in G.nodes if i in boundary]
    for i in ordered:
        n = G.nodes[i]
        c = int(n["cluster"])
        if c == -1:
            color = NOISE_COLOR
        elif colors is not None:
            color = colors.get(c, NOISE_COLOR)
        else:
            color = PALETTE[c % len(PALETTE)]
        size = 8 + size_bonus + 2.0 * (max(int(n["citations"]), 0) ** 0.5)
        # Multi-line composition + CSS wrap = the "brick" tooltip (Batman's spec).
        tooltip = (f"{short(n['title'])}\n"
                   f"{n['year']} · {n['citations']} citations\n"
                   f"{short(n['label'], 40)}")
        kwargs = {}
        if i in boundary:
            if colors is not None:
                ring = colors.get(boundary[i], NOISE_COLOR)
            else:
                ring = PALETTE[boundary[i] % len(PALETTE)]
            # A bridge paper wears the colour of the subtopic it reaches into, on a thick
            # dashed ring, and is drawn a little bigger: it should read as a landmark, not
            # as one more dot. These are the papers a reader most wants to find.
            size += 3.0
            kwargs = {"color": {"background": color, "border": ring},
                      "borderWidth": 5,
                      "shapeProperties": {"borderDashes": [7, 4]}}
            tooltip += "\nboundary paper - bridges into the neighboring subtopic"
        elif i in loners:
            # A loner has no edge, so no spring holds it: repulsion alone pushes it out of
            # frame and the fit zooms everything else into dust (measured in v1: one was
            # yanked 707 units away and kept drifting to 1533). Take it out of the simulation
            # so it stays where the map put it. It is also the honest behaviour: nothing in
            # the corpus is close enough to pull it anywhere.
            kwargs = {"color": {"background": color, "border": "#a1a1aa"},
                      "borderWidth": 2, "physics": False,
                      "shapeProperties": {"borderDashes": [3, 3]}}
            tooltip += ("\nloner - no paper reaches the similarity threshold; "
                        "check whether it is off-topic")
        else:
            kwargs = {"color": color}
        if positions is not None and i in positions:
            # Scale UMAP units (~10-20 span) up to canvas pixels; physics refines from here.
            kwargs["x"] = float(positions[i][0]) * 90.0
            kwargs["y"] = -float(positions[i][1]) * 90.0    # vis.js y grows downward
        net.add_node(int(i), label=" ", title=tooltip,
                     size=float(min(size, 40)), **kwargs)
    # Island legends: cluster KeyBERT name -> its node ids (drawn at the live center of
    # mass by the polish JS). Noise (-1) gets no legend.
    import json as _json
    label_ids: dict[str, list[int]] = {}
    for i in G.nodes:
        n = G.nodes[i]
        if int(n["cluster"]) == -1:
            continue
        label_ids.setdefault(short(str(n["label"]), 42), []).append(int(i))

    for a, b, d in G.edges(data=True):
        w = float(d["weight"])
        # CALIBRATED SPRINGS (Batman's question made this obvious): each edge gets its own
        # rest length - strong kinship pulls tighter. sim 0.95 -> ~81px, sim 0.75 -> ~165px.
        # Proximity in the layout now approximates semantic distance, not just topology.
        net.add_edge(int(a), int(b), value=w, length=float(60 + 420 * (1 - w)))
    net.toggle_physics(True)
    if positions is not None:
        # SEEDED maps used to end up as dust. With centralGravity 0 (what the JS options
        # above still ask for in the seeded branch) nothing holds the graph in, so
        # repulsion inflated a ~950px seeded layout to ~9000 units - measured on v1 - and
        # the fit had to zoom out to 0.076, turning the papers into 1.4px specks on a
        # two-thirds empty canvas. An earlier attempt enlarged the NODES instead and could
        # not work: at that inflation the nearest neighbour sat 6.7px away, so nothing
        # could grow past ~3px without overlapping. The dust was the layout's fault.
        # These Python-side options are applied after the JS ones and win.
        #
        # damping/spring set for a SMOOTH return rather than a springy one: with
        # spring_strength 0.08 against damping 0.75 the system was underdamped and a
        # dragged hub shot past its spot and wobbled (43 direction reversals, still
        # swinging +-114 units after 400 ticks). Softer spring inside heavier damping
        # glides home instead of bouncing.
        net.force_atlas_2based(gravity=-18, central_gravity=0.012, spring_length=90,
                               spring_strength=0.05, damping=0.88, overlap=0.9)
        # 60 iterations, swept against the seeded map: every extra iteration rewrites
        # more of the semantic geometry for almost no gain in spacing. Measured as
        # hub-to-hub distance correlation vs the seeds / overlapping pairs:
        #   40 -> 0.81 / 61     80 -> 0.70 / 46     120 -> 0.67 / 38     180 -> 0.60 / 39
        net.options.physics.stabilization.iterations = 60
        net.options.physics.stabilization.fit = False
        # minVelocity is the speed below which the solver declares itself done. It looks
        # like a smoothness knob and is not: lowering it to 0.7 left 24 nodes twitching
        # instead of 2, and raising it past ~1.6 makes the solver call itself stabilized
        # so fast that a dragged paper never springs back (measured: 0% return). 1.2 keeps
        # the spring alive while the map goes quiet.
        net.options.physics.__dict__["minVelocity"] = 1.2
    html = net.generate_html()
    # Fixed legend zone: chips = the drawn hubs (name + its color), lines = what is
    # hidden and why (the caller knows the counts).
    chip_color = {}
    for i in G.nodes:
        n = G.nodes[i]
        c = int(n["cluster"])
        if c == -1:
            continue
        lab = short(str(n["label"]), 42)
        if lab not in chip_color:
            if colors is not None:
                chip_color[lab] = colors.get(c, NOISE_COLOR)
            else:
                chip_color[lab] = PALETTE[c % len(PALETTE)]
    net_summary = {"chips": [[lab, chip_color[lab]] for lab in label_ids
                             if lab in chip_color and len(label_ids[lab]) >= 3],
                   "lines": summary_lines or []}
    polish = (_NETWORK_POLISH_JS
              .replace("__CLUSTER_LABELS__", _json.dumps(label_ids))
              .replace("__NET_SUMMARY__", _json.dumps(net_summary))
              .replace("__SEEDED__", "true" if positions is not None else "false")
              .replace("__SEED_ID__", _json.dumps(seed_id)))
    return html.replace("</body>", polish + "</body>")


def save_network_html(G, out_html=None) -> str:
    """Save the interactive paper network as a self-contained HTML file."""
    config.DELIVERABLES.mkdir(parents=True, exist_ok=True)
    out_html = out_html or (config.DELIVERABLES / "paper_network.html")
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(network_html(G))
    print(f"Saved interactive paper network to:\n  {out_html}")
    return str(out_html)


def packed_figure(topic_map: pd.DataFrame) -> go.Figure:
    """Circle-packing view: non-overlapping bubbles, one big circle per subtopic.

    Presentation-style view (like classic packaging/market bubble charts). Unlike the
    scatter, positions carry NO meaning here - only membership and size (citations).
    """
    import circlify

    tm = topic_map[topic_map["cluster"] != -1]
    clusters = sorted(tm["cluster"].unique())

    # Hierarchical input: one parent per cluster, papers as children (size = citations).
    data = []
    for c in clusters:
        part = tm[tm["cluster"] == c]
        children = [{"id": int(i), "datum": float(r["citations"]) + 2.0}
                    for i, r in part.iterrows()]
        data.append({"id": f"cluster{c}", "datum": sum(ch["datum"] for ch in children),
                     "children": children})

    circles = circlify.circlify(data, show_enclosure=False)

    fig = go.Figure()
    shapes = []
    for circ in circles:
        if circ.level == 1:                      # subtopic enclosure
            c = int(circ.ex["id"].replace("cluster", ""))
            color = PALETTE[c % len(PALETTE)]
            shapes.append(dict(type="circle", x0=circ.x - circ.r, y0=circ.y - circ.r,
                               x1=circ.x + circ.r, y1=circ.y + circ.r,
                               line=dict(color=color, width=2), fillcolor=color, opacity=0.10))
            part = tm[tm["cluster"] == c]
            fig.add_annotation(x=circ.x, y=circ.y + circ.r * 0.92,
                               text=f"<b>{part['label'].iloc[0]}</b>", showarrow=False,
                               font=dict(size=13, color="#fafafa"),
                               bgcolor="rgba(39,39,42,0.85)", borderpad=4)
        else:                                    # one paper
            i = int(circ.ex["id"])
            row = tm.loc[i]
            c = int(row["cluster"])
            color = PALETTE[c % len(PALETTE)]
            shapes.append(dict(type="circle", x0=circ.x - circ.r, y0=circ.y - circ.r,
                               x1=circ.x + circ.r, y1=circ.y + circ.r,
                               line=dict(color="white", width=1), fillcolor=color, opacity=0.85))
            # Invisible marker at the center provides the hover tooltip AND the click id.
            fig.add_trace(go.Scatter(x=[circ.x], y=[circ.y], mode="markers",
                                     marker=dict(size=max(circ.r * 300, 6), opacity=0),
                                     text=[_hover_text(row)], hoverinfo="text",
                                     customdata=[i], showlegend=False))

    fig.update_layout(shapes=shapes, template="plotly_dark",
                      paper_bgcolor="#18181b", plot_bgcolor="#18181b", height=650,
                      margin=dict(l=10, r=10, t=10, b=10),
                      hoverlabel=dict(bgcolor="#ffffff", bordercolor="#d4d4d8",
                                      font=dict(color="#18181b", size=13), align="left"))
    fig.update_xaxes(visible=False, range=[-1.05, 1.05])
    fig.update_yaxes(visible=False, range=[-1.05, 1.05], scaleanchor="x", scaleratio=1)
    return fig


def gap_overlay_figure(topic_map: pd.DataFrame, gaps: pd.DataFrame,
                       **bubble_kwargs) -> go.Figure:
    """The bubble map with the top SILO gaps drawn on it: a dashed red line between the
    centroids of cluster pairs that are semantically close but barely cite each other.
    Visual thesis: the line marks the frontier where contributions fit."""
    fig = bubble_figure(topic_map, **bubble_kwargs)

    tm = topic_map[topic_map["cluster"] != -1]
    centroid = {tm[tm["cluster"] == c]["label"].iloc[0]:
                (tm[tm["cluster"] == c]["x"].mean(), tm[tm["cluster"] == c]["y"].mean())
                for c in tm["cluster"].unique()}

    silos = gaps[gaps["type"] == "silo"].head(3)
    for shown, (_, r) in enumerate(silos.iterrows()):
        a, b = [s.strip() for s in r["where"].split("<->")]
        if a not in centroid or b not in centroid:
            continue
        (xa, ya), (xb, yb) = centroid[a], centroid[b]
        fig.add_trace(go.Scatter(
            x=[xa, xb], y=[ya, yb], mode="lines",
            line=dict(dash="dash", color="#ef4444", width=2), opacity=0.75,
            name="silo gap", showlegend=(shown == 0), hoverinfo="skip",
        ))
        fig.add_annotation(
            x=(xa + xb) / 2, y=(ya + yb) / 2,
            text=f"silo · score {r['score']:.2f}", showarrow=False,
            font=dict(size=11, color="#fca5a5"), bgcolor="rgba(39,39,42,0.9)", borderpad=3,
        )
    return fig


def _must_count(citations: list[int]) -> int:
    """Objective must-read cutoff, computed PER CLUSTER (Batman: no fixed top-3).

    Primary: the cluster's h-index (h papers with >= h citations each) - the standard
    bibliometric core, parameter-free and self-scaling. Degenerate case: when h > n/2
    (an 'everything is famous' cluster, e.g. USGS summaries) fall back to head/tail
    breaks (papers above the cluster's mean citations - Jiang 2013, built for heavy
    tails). Measured on this corpus: geology n=110 -> 35 must-reads; young XCT n=9 -> 3.
    """
    s = sorted(citations, reverse=True)
    h = max((i + 1 for i, c in enumerate(s) if c >= i + 1), default=0)
    if h > len(s) / 2:
        mean = sum(s) / len(s) if s else 0
        return max(1, sum(1 for c in s if c > mean))
    return max(1, h)


def _legacy_reading_guide(topic_map: pd.DataFrame, height: int = 980) -> str:
    """The READING GUIDE (Batman's spec, replaces circle packing in the app):

    - one vertical COLUMN per subtopic, biggest bubbles at the TOP (small papers never
      get lost in packing gaps again - it's a single ordered stack),
    - the top-3 most-cited of each subtopic = MUST-READ zone: full color + white ring,
      separated by a dashed line ("what to start reading"), the rest dimmed,
    - gentle floating animation - bubbles wander and RETURN to their anchor (sine),
    - unified white brick tooltip on hover.

    D3 via CDN (the app already needs internet for model/APIs). v1 is hover-only;
    click-to-inspect lives in Search/Gaps (needs components.v2 events - N4).
    """
    import json

    tm = topic_map[topic_map["cluster"] != -1]
    clusters = []
    for c in sorted(tm["cluster"].unique()):
        part = tm[tm["cluster"] == c].sort_values("citations", ascending=False)
        papers = [{"t": short(r["title"], 60), "y": int(r["year"]),
                   "c": int(r["citations"]),
                   "r": float(min(7 + 2.2 * (max(int(r["citations"]), 0) ** 0.5), 30))}
                  for _, r in part.iterrows()]
        clusters.append({"label": short(part["label"].iloc[0], 38),
                         "color": PALETTE[int(c) % len(PALETTE)], "papers": papers})
    data = json.dumps(clusters)

    return """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
body { margin:0; background:#18181b; font-family:Inter,'Segoe UI',sans-serif; }
.tip { position:absolute; background:#fff; color:#18181b; border:1px solid #d4d4d8;
  border-radius:10px; padding:10px 12px; font-size:13px; line-height:1.45;
  max-width:300px; pointer-events:none; display:none; }
</style></head><body>
<div class="tip" id="tip"></div>
<svg id="stage" width="100%" height="__H__"></svg>
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script>
const clusters = __DATA__;
const svg = d3.select('#stage');
const W = document.getElementById('stage').clientWidth || 1100;
const H = __H__;
const colW = W / clusters.length, topPad = 56, MUST = 3;
let maxStack = 0;
clusters.forEach(cl => { let s = 0; cl.papers.forEach(p => s += 2*p.r + 6); maxStack = Math.max(maxStack, s); });
const k = Math.min(1, (H - topPad - 30) / maxStack);
const nodes = [];
clusters.forEach((cl, i) => {
  const cx = colW*i + colW/2;
  svg.append('text').attr('x', cx).attr('y', 24).attr('text-anchor','middle')
     .attr('fill','#fafafa').attr('font-weight',600).attr('font-size',13).text(cl.label);
  let y = topPad;
  cl.papers.forEach((p, j) => {
    const r = Math.max(p.r*k, 3.5);
    y += r;
    nodes.push({...p, r, x0:cx, y0:y, color:cl.color, must:(j<MUST),
                ph:Math.random()*6.28, amp:2.2+Math.random()*2.8, sp:0.35+Math.random()*0.5});
    y += r + 6*k;
    if (j === MUST-1 && cl.papers.length > MUST) {
      svg.append('line').attr('x1',cx-colW*0.32).attr('x2',cx+colW*0.32)
         .attr('y1',y).attr('y2',y).attr('stroke','#a1a1aa')
         .attr('stroke-dasharray','5,5').attr('stroke-width',1);
      svg.append('text').attr('x',cx).attr('y',y-4).attr('text-anchor','end')
         .attr('dx', colW*0.3).attr('fill','#a1a1aa').attr('font-size',10)
         .text('must-read');
      y += 10;
    }
  });
});
const tip = document.getElementById('tip');
const circles = svg.selectAll('circle').data(nodes).join('circle')
  .attr('r', d=>d.r).attr('fill', d=>d.color)
  .attr('opacity', d=>d.must?0.95:0.5)
  .attr('stroke', d=>d.must?'#ffffff':'none').attr('stroke-width', d=>d.must?2:0)
  .on('mousemove', (e,d) => { tip.style.display='block';
      tip.style.left=(e.pageX+14)+'px'; tip.style.top=(e.pageY+10)+'px';
      tip.innerHTML='<b>'+d.t+'</b><br>'+d.y+' &middot; '+d.c+' citations'; })
  .on('mouseleave', () => tip.style.display='none');
// Float and RETURN: every bubble breathes around its anchor, never drifting away.
d3.timer(t => {
  circles.attr('cx', d => d.x0 + Math.sin(t/1000*d.sp + d.ph)*d.amp)
         .attr('cy', d => d.y0 + Math.cos(t/1000*d.sp*0.8 + d.ph)*d.amp);
});
</script></body></html>""".replace("__DATA__", data).replace("__H__", str(height))


def reading_guide_html(topic_map: pd.DataFrame) -> tuple[str, int]:
    """READING GUIDE v2 (Batman's fixes): sizes PRESERVED and height BOUNDED.

    Layout computed in Python: one column per subtopic; inside it, bubbles sorted by
    citations wrap into ROWS (biggest first, read left->right top->down) - small papers
    keep their true size and never vanish, and a 110-paper cluster stays compact instead
    of a kilometer-long stack. Must-read set = per-cluster h-index (see _must_count),
    separated by a dashed line. Adapts to ANY granularity (columns share the width).
    Returns (html, pixel_height) so the app can size the frame exactly.
    """
    import json

    W, PAD, TOP, GAP = 1100, 14, 46, 5
    tm = topic_map[topic_map["cluster"] != -1]
    cluster_ids = sorted(tm["cluster"].unique())
    col_w = W / max(len(cluster_ids), 1)

    nodes, seps, labels_out = [], [], []
    total_h = TOP
    for i, c in enumerate(cluster_ids):
        part = tm[tm["cluster"] == c].sort_values("citations", ascending=False)
        color = PALETTE[int(c) % len(PALETTE)]
        must_n = _must_count(part["citations"].tolist())
        # Header must FIT ITS COLUMN: at high granularity (13+ columns) a fixed 34-char
        # cut overflowed and titles collided. Truncate by pixel budget instead.
        label_font = 13 if col_w >= 130 else 11
        label_chars = max(6, int((col_w - 10) / (label_font * 0.58)))
        sub = (f"{must_n} must-reads (h-index)" if col_w >= 150
               else f"{must_n} must-reads")
        # Header = the short keyphrase title; hover = the full centroid sentence
        # (Batman: keep the title short, the rest appears on hover).
        hover = str(part["summary"].iloc[0]) if "summary" in part.columns else ""
        labels_out.append({"x": col_w * i + col_w / 2, "f": label_font,
                           "t": short(part["label"].iloc[0], label_chars),
                           "full": hover or str(part["label"].iloc[0]), "n": sub})
        x0, x1 = col_w * i + PAD, col_w * (i + 1) - PAD
        x, y, row_h = x0, TOP, 0.0
        first = len(nodes)
        for j, (idx, r) in enumerate(part.iterrows()):
            rad = max(min(7 + 2.2 * (max(int(r["citations"]), 0) ** 0.5), 30), 5)
            d = 2 * rad
            if x + d > x1 and x > x0:              # wrap to the next row
                x, y, row_h = x0, y + row_h + GAP, 0.0
            nodes.append({"x": round(x + rad, 1), "y": round(y + rad, 1), "r": round(rad, 1),
                          "color": color, "must": j < must_n, "i": int(idx),
                          "t": short(r["title"], 60), "yr": int(r["year"]),
                          "c": int(r["citations"])})
            x += d + GAP
            row_h = max(row_h, d)
        if must_n < len(part):
            musts = nodes[first:first + must_n]
            sep_y = max(m["y"] + m["r"] for m in musts) + 5
            seps.append({"x1": round(x0, 1), "x2": round(x1, 1), "y": round(sep_y, 1)})
        total_h = max(total_h, y + row_h)

    H = int(total_h + 26)
    data = json.dumps({"nodes": nodes, "seps": seps, "labels": labels_out, "W": W, "H": H})

    html = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
body { margin:0; background:#18181b; font-family:Inter,'Segoe UI',sans-serif; }
.tip { position:absolute; background:#fff; color:#18181b; border:1px solid #d4d4d8;
  border-radius:10px; padding:10px 12px; font-size:13px; line-height:1.45;
  max-width:300px; pointer-events:none; display:none; }
</style></head><body>
<div class="tip" id="tip"></div>
<svg id="stage"></svg>
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script>
const D = __DATA__;
const svg = d3.select('#stage').attr('viewBox', '0 0 ' + D.W + ' ' + D.H)
              .attr('width', '100%').attr('height', D.H);
D.labels.forEach(l => {
  svg.append('text').attr('x', l.x).attr('y', 20).attr('text-anchor', 'middle')
     .attr('fill', '#fafafa').attr('font-weight', 600).attr('font-size', l.f)
     .text(l.t)
     .append('title').text(l.full);
  svg.append('text').attr('x', l.x).attr('y', 36).attr('text-anchor', 'middle')
     .attr('fill', '#a1a1aa').attr('font-size', 10)
     .text(l.n);
});
D.seps.forEach(s => {
  svg.append('line').attr('x1', s.x1).attr('x2', s.x2).attr('y1', s.y).attr('y2', s.y)
     .attr('stroke', '#a1a1aa').attr('stroke-dasharray', '5,5').attr('stroke-width', 1);
});
const tip = document.getElementById('tip');
const circles = svg.selectAll('circle').data(D.nodes).join('circle')
  .attr('r', d => d.r).attr('fill', d => d.color)
  .attr('opacity', d => d.must ? 0.95 : 0.45)
  .attr('stroke', d => d.must ? '#ffffff' : 'none')
  .attr('stroke-width', d => d.must ? 2 : 0)
  .style('cursor', 'pointer')
  .on('mousemove', (e, d) => { tip.style.display = 'block';
      tip.style.left = (e.pageX + 14) + 'px'; tip.style.top = (e.pageY + 10) + 'px';
      tip.innerHTML = '<b>' + d.t + '</b><br>' + d.yr + ' &middot; ' + d.c + ' citations'; })
  .on('mouseleave', () => tip.style.display = 'none')
  .on('click', (e, d) => {
      try { window.parent.postMessage({frothSelect: d.i}, '*'); } catch (err) {} });
circles.each(function(d) { d.ph = Math.random() * 6.28;
                           d.amp = 1.6 + Math.random() * 2.2;
                           d.sp = 0.35 + Math.random() * 0.5; });
d3.timer(t => {
  circles.attr('cx', d => d.x + Math.sin(t / 1000 * d.sp + d.ph) * d.amp)
         .attr('cy', d => d.y + Math.cos(t / 1000 * d.sp * 0.8 + d.ph) * d.amp);
});
</script></body></html>""".replace("__DATA__", data)
    return html, H


def plot_packed(topic_map: pd.DataFrame, out_html=None) -> str:
    """Render the circle-packing view and save it as a self-contained HTML file."""
    fig = packed_figure(topic_map)
    config.DELIVERABLES.mkdir(parents=True, exist_ok=True)
    out_html = out_html or (config.DELIVERABLES / "packed_bubbles.html")
    fig.write_html(out_html, include_plotlyjs=True)
    print(f"Saved circle-packing view to:\n  {out_html}")
    return str(out_html)


if __name__ == "__main__":
    from . import cluster, graph

    topic_map = cluster.load_topic_map()
    plot_bubbles(topic_map)
    plot_packed(topic_map)
    save_network_html(graph.load_graph())
