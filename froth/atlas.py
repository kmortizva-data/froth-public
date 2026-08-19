"""
atlas.py - Phase D: "The Atlas", Froth's full-corpus map for the uncapped era.

WHY: the uncapped harvest grew corpora to 8k-16k papers. The legacy views draw one DOM
node per paper (Plotly SVG, vis.js physics, animated D3) and die at that scale; the Atlas
draws every paper as WebGL points via deck.gl, which handles hundreds of thousands without
breaking a sweat. deck.gl loads from a CDN inside our own iframe (same pattern as the D3
reading guide and the vis.js network) - zero pip dependencies, zero native DLLs (nothing
for Smart App Control to block), full brand control.

Phase D.1 (this file, first cut): ScatterplotLayer of the whole corpus, brand hierarchical
colors (palette.territory_hues - every cluster gets its OWN hue, no recycling), white brick
tooltip, click -> postMessage({frothSelect}) through the existing froth_bridge.
Phase D.2 adds the semantic-zoom label layers; D.4 reuses this generator for hub sub-tabs.
"""
import json

import numpy as np
import pandas as pd

from . import palette
from .visualize import NOISE_COLOR, short

DECK_CDN = "https://cdn.jsdelivr.net/npm/deck.gl@9.0.36/dist.min.js"


def _hex_to_rgb(hex_color: str) -> list[int]:
    h = hex_color.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def atlas_html(topic_map: pd.DataFrame, height: int = 720,
               colors: dict[int, str] | None = None) -> str:
    """Standalone HTML for the Atlas map of ONE frame (full corpus or a single hub).

    Expects columns: title, year, citations, x, y, cluster, label. Colors: one OWN hue
    per cluster via palette.territory_hues (or an explicit {cluster: hex} mapping, used
    by hub sub-tabs to paint subtones of the parent's hue). Noise stays muted gray.
    Every point is pickable: hover = brand white-brick tooltip, click = the paper's row
    id posted to the host page (frothSelect), same contract as every other view.
    """
    tm = topic_map
    clusters = sorted(c for c in tm["cluster"].unique() if c != -1)
    if colors is None:
        hues = palette.territory_hues(len(clusters))
        colors = {c: hues[i] for i, c in enumerate(clusters)}

    rgb = {c: _hex_to_rgb(h) for c, h in colors.items()}
    noise_rgb = _hex_to_rgb(NOISE_COLOR)

    # Compact per-point records: [x, y, radius_px, r, g, b, alpha, row_id, title, year,
    # citations, label]. Arrays (not dicts) keep 16k points ~1.5 MB of HTML.
    # Real uncapped corpora carry NaNs (year/citations from sources that omit them) -
    # sanitize once here instead of trusting every row.
    cites = pd.to_numeric(tm["citations"], errors="coerce").fillna(0).astype(int)
    years = pd.to_numeric(tm["year"], errors="coerce").fillna(0).astype(int)
    radius = (2.2 + 1.1 * np.sqrt(cites.clip(lower=0))).clip(upper=10.0)
    # Relevance mapped to 0..1 for the optional dimming toggle (0.55 = the per-corpus
    # gate valley; above it papers brighten toward 1).
    if "relevance" in tm.columns:
        rel01 = ((pd.to_numeric(tm["relevance"], errors="coerce").fillna(0.55) - 0.5)
                 / 0.3).clip(0.1, 1.0)
    else:
        rel01 = pd.Series(1.0, index=tm.index)
    pts = []
    for (i, row), rad, yr, ct, r01 in zip(tm.iterrows(), radius, years, cites, rel01):
        c = int(row["cluster"])
        col = rgb.get(c, noise_rgb)
        alpha = 90 if c == -1 else 210
        pts.append([round(float(row["x"]), 3), round(float(row["y"]), 3),
                    round(float(rad), 1), col[0], col[1], col[2], alpha, int(i),
                    short(str(row["title"]), 70), int(yr),
                    int(ct), short(str(row["label"]), 45), c, round(float(r01), 2)])

    # Fit the initial camera to the data (OrthographicView: zoom = log2(px per unit)).
    xs, ys = tm["x"].to_numpy(), tm["y"].to_numpy()
    cx, cy = float((xs.min() + xs.max()) / 2), float((ys.min() + ys.max()) / 2)
    span_x = max(float(xs.max() - xs.min()), 1e-6)
    span_y = max(float(ys.max() - ys.min()), 1e-6)

    # Legend panel data (Batman 2026-07-17): one entry per territory - name, count,
    # color and centroid (the centroid drives zoom-adaptive visibility in JS).
    terr = []
    for c in clusters:
        part = tm[tm["cluster"] == c]
        terr.append({"id": int(c), "name": short(str(part["label"].iloc[0]), 40),
                     "count": int(len(part)), "color": colors[c],
                     # Distance to the thesis title, carried so the legend can SHOW it.
                     # Information, not a filter: measured on this corpus, keeping only the
                     # closest subtopics does not sharpen the view (44% of his own field
                     # against 46% for no filter), because his title is half method and half
                     # deposit and both are his. The legend marks; the choosing stays his.
                     "rel": round(float(part["relevance"].mean()), 3)
                     if "relevance" in part.columns else None,
                     "cx": round(float(part["x"].mean()), 3),
                     "cy": round(float(part["y"].mean()), 3)})
    terr.sort(key=lambda t: -t["count"])
    _rels = sorted(t["rel"] for t in terr if t["rel"] is not None)
    _weak = _rels[len(_rels) // 2] if _rels else None      # the lower half of THIS corpus
    for t in terr:
        t["weak"] = bool(_weak is not None and t["rel"] is not None and t["rel"] <= _weak)

    # Semantic-zoom thresholds, taken from THIS corpus's own size distribution rather than
    # invented (rule 9). Shneiderman's "overview first, zoom and filter, details on demand":
    # far out only the big territories are named, and smaller ones appear as you close in.
    # Measured on Beauvoir (96 subtopics, sizes 7..194): p90 -> 10 labels, p75 -> 26,
    # p50 -> 48, p0 -> 96. A corpus with a flatter distribution gets its own numbers.
    counts = [t["count"] for t in terr] or [0]
    tiers = [int(np.percentile(counts, p)) for p in (90, 75, 50, 0)]
    # Each label also carries the bounding box of its territory, so clicking it can fly the
    # camera there with no recomputation (hito 2.2). Cheap: 4 numbers per territory.
    for t in terr:
        part = tm[tm["cluster"] == t["id"]]
        t["x0"] = round(float(part["x"].min()), 3)
        t["x1"] = round(float(part["x"].max()), 3)
        t["y0"] = round(float(part["y"].min()), 3)
        t["y1"] = round(float(part["y"].max()), 3)

    payload = json.dumps({"pts": pts, "cx": cx, "cy": cy, "terr": terr, "tiers": tiers,
                          "spanX": span_x, "spanY": span_y, "n": len(pts)})

    return """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
html, body { margin:0; background:#18181b; height:100%; overflow:hidden;
             font-family: Inter, 'Segoe UI', sans-serif; }
#map { position:absolute; inset:0; }
#hud { position:absolute; left:12px; bottom:10px; color:#71717a; font-size:11px;
       background:rgba(24,24,27,.75); padding:3px 8px; border-radius:8px; }
#legend { position:absolute; right:10px; top:10px; bottom:52px; width:250px;
  background:rgba(24,24,27,.88); border:1px solid #2e2e34; border-radius:12px;
  padding:10px 6px 10px 10px; overflow-y:auto; }
#legend h3 { margin:0 0 8px 2px; font-size:12px; font-weight:600; color:#a1a1aa;
  text-transform:uppercase; letter-spacing:.05em; }
.lrow { display:flex; align-items:center; gap:7px; padding:4px 4px; border-radius:8px;
  cursor:pointer; }
.lrow:hover { background:rgba(255,255,255,.06); }
.lrow input { accent-color:#6366f1; margin:0; flex:none; }
.chip { width:11px; height:11px; border-radius:50%; flex:none; }
.lname { color:#e4e4e7; font-size:12px; line-height:1.25; flex:1; cursor:zoom-in; }
.lname:hover { color:#a5b4fc; text-decoration:underline; }
.lcount { color:#71717a; font-size:11px; flex:none; }
#home { position:absolute; left:12px; top:12px; display:none; padding:7px 13px;
  border:1px solid #3f3f46; border-radius:9px; background:rgba(24,24,27,.9);
  color:#e4e4e7; font-size:12px; font-weight:600; cursor:pointer; font-family:inherit; }
#home:hover { border-color:#6366f1; color:#a5b4fc; }
#tonet { position:absolute; right:10px; bottom:10px; width:250px; padding:9px 0;
  border:none; border-radius:10px; background:#4f46e5; color:#e0e7ff; font-size:13px;
  font-weight:600; cursor:pointer; font-family:inherit; }
#tonet:disabled { background:#27272a; color:#52525b; cursor:default; }
</style></head><body>
<div id="map"></div><div id="hud"></div>
<button id="home">&#8592; Whole map</button>
<div id="legend"><h3>Subtopics in view</h3>
<div style="color:#71717a;font-size:10.5px;margin:0 0 6px 2px;">
  Click a name to zoom to it &middot; tick to send to Network</div>
<div style="display:flex;gap:10px;margin:0 0 8px 2px;color:#a1a1aa;font-size:11px;">
 <label style="display:flex;gap:4px;align-items:center;cursor:pointer;">
   <input type="checkbox" id="tgnoise" checked style="accent-color:#6366f1;margin:0;">noise</label>
 <label style="display:flex;gap:4px;align-items:center;cursor:pointer;">
   <input type="checkbox" id="tgdim" style="accent-color:#6366f1;margin:0;">dim low relevance</label>
</div>
<div id="lrows"></div></div>
<button id="tonet" disabled>Open selection in Network</button>
<script src="__DECK_CDN__"></script>
<script>
// Any failure paints itself on screen instead of dying silently (a blank map with no
// clue cost us a debugging session; never again).
window.onerror = function (msg, src, line) {
  var h = document.getElementById('hud');
  if (h) { h.textContent = 'Atlas error: ' + msg + ' @' + line; h.style.color = '#f87171'; }
};
if (typeof deck === 'undefined') {
  document.getElementById('hud').textContent =
    'deck.gl CDN did not load (no internet or blocked) - the Atlas needs it';
}
const D = __PAYLOAD__;
document.getElementById('hud').textContent =
  D.n.toLocaleString() + ' papers · WebGL';
// Fit: pixels-per-data-unit that shows the whole cloud with a small margin.
const W = window.innerWidth || 1100, H = window.innerHeight || __H__;
const fitZoom = Math.log2(Math.min(W / (D.spanX * 1.12), H / (D.spanY * 1.12)));
// Layer factory: the noise / relevance-dimming toggles rebuild it (a fresh id per
// state combination makes deck.gl treat it as a new layer - no updateTriggers dance).
function makeLayer() {
  const showNoise = document.getElementById('tgnoise').checked;
  const dim = document.getElementById('tgdim').checked;
  return new deck.ScatterplotLayer({
    id: 'papers-' + (showNoise ? 1 : 0) + (dim ? 1 : 0),
    data: showNoise ? D.pts : D.pts.filter(p => p[12] !== -1),
    getPosition: p => [p[0], p[1]],
    getRadius: p => p[2],
    radiusUnits: 'pixels',
    radiusMinPixels: 1.2,
    getFillColor: p => [p[3], p[4], p[5],
                        dim ? Math.round(p[6] * (0.2 + 0.8 * p[13])) : p[6]],
    stroked: false,
    pickable: true,
    antialiasing: true,
  });
}
// SEMANTIC ZOOM (hito 2.1): which territories are NAMED depends on how close you are.
// D.tiers holds this corpus's own size percentiles [p90, p75, p50, p0], so the ladder is
// derived from the data, not from a magic number. Far out only the biggest territories
// carry a label; each step in reveals the next tier. Zoom is log2(pixels per unit), so
// these offsets are "one doubling of scale" apart.
let viewZoom = fitZoom;
function minCountForZoom(z) {
  const d = z - fitZoom;                       // 0 = the initial fit-everything view
  if (d < 1.0) { return D.tiers[0]; }          // satellite: only the majors
  if (d < 2.2) { return D.tiers[1]; }          // regional
  if (d < 3.4) { return D.tiers[2]; }          // local
  return D.tiers[3];                           // street: every territory
}
function makeLabels() {
  const minCount = minCountForZoom(viewZoom);
  const shown = D.terr.filter(t => t.count >= minCount);
  return new deck.TextLayer({
    id: 'labels-' + minCount,
    data: shown,
    getPosition: t => [t.cx, t.cy],
    getText: t => t.name,
    // Pixel sizing keeps labels legible at any zoom (same trick as the seed pin in the
    // network overlay); the dark outline makes them readable over any cluster hue.
    getSize: t => (t.count >= D.tiers[0] ? 15 : 12),
    sizeUnits: 'pixels',
    getColor: [250, 250, 250, 235],
    outlineColor: [24, 24, 27, 255],
    outlineWidth: 3,
    fontSettings: {sdf: true},
    fontFamily: "Inter, 'Segoe UI', sans-serif",
    fontWeight: 600,
    getTextAnchor: 'middle',
    getAlignmentBaseline: 'center',
    // Labels must never eat a click meant for a paper underneath.
    pickable: false,
    // deck.gl drops overlapping labels itself (verified present in this CDN bundle),
    // which is what keeps 96 territories from turning into a wall of text.
    extensions: [new deck.CollisionFilterExtension()],
    collisionEnabled: true,
    collisionGroup: 'labels',
    getCollisionPriority: t => t.count,        // a bigger territory wins the spot
    collisionTestProps: {sizeScale: 1.4},
  });
}
function redrawLayers() {
  deckgl.setProps({layers: [makeLayer(), makeLabels()]});
}

const deckgl = new deck.DeckGL({
  container: 'map',
  views: new deck.OrthographicView({flipY: false}),
  initialViewState: {target: [D.cx, D.cy, 0], zoom: fitZoom,
                     minZoom: fitZoom - 1.5, maxZoom: fitZoom + 7},
  controller: {scrollZoom: {speed: 0.02, smooth: true}, inertia: 300},
  layers: [makeLayer(), makeLabels()],
  // Brand white-brick tooltip, same look as every other Froth view.
  getTooltip: ({object}) => object && {
    html: '<b>' + object[8] + '</b><br>' + object[9] + ' &middot; ' + object[10] +
          ' citations<br><i>' + object[11] + '</i>',
    style: {backgroundColor: '#ffffff', color: '#18181b',
            border: '1px solid #d4d4d8', borderRadius: '10px',
            padding: '10px 12px', fontSize: '13px', maxWidth: '300px',
            fontFamily: "Inter, 'Segoe UI', sans-serif"}
  },
  onClick: (info) => {
    if (info && info.object) {
      console.log('frothSelect', info.object[7]);
      try { window.parent.postMessage({frothSelect: info.object[7]}, '*'); }
      catch (e) {}
    }
  },
  // Zoom-adaptive legend (Batman): show only territories whose center sits in view.
  // The same event drives the label tier - redrawn only when the tier actually changes,
  // so panning around at one zoom level costs nothing.
  onViewStateChange: ({viewState}) => {
    const before = minCountForZoom(viewZoom);
    viewZoom = viewState.zoom;
    if (minCountForZoom(viewZoom) !== before) { redrawLayers(); }
    scheduleLegend(viewState);
  },
});

document.getElementById('tgnoise').addEventListener('change', redrawLayers);
document.getElementById('tgdim').addEventListener('change', redrawLayers);

// ---- Legend panel: zoom-adaptive list + hub selection -> Network ----------------
const selected = new Set();
const rowsEl = document.getElementById('lrows');
const btn = document.getElementById('tonet');
D.terr.forEach(t => {
  const row = document.createElement('label');
  row.className = 'lrow';
  row.dataset.terr = t.id;
  // The relevance number rides along and the lower half is dimmed. Nothing is pre-ticked:
  // measured, picking only the closest subtopics does not sharpen this corpus, so the
  // legend says what it knows and leaves the decision alone.
  if (t.weak) row.style.opacity = 0.55;
  row.title = t.rel === null ? t.name
            : t.name + '  -  closeness to your title: ' + t.rel.toFixed(2);
  row.innerHTML = '<input type="checkbox">' +
    '<span class="chip" style="background:' + t.color + '"></span>' +
    '<span class="lname">' + t.name + '</span>' +
    (t.rel === null ? '' :
      '<span class="lrel" style="opacity:.6;font-size:10px;margin-right:4px">'
      + t.rel.toFixed(2) + '</span>') +
    '<span class="lcount">' + t.count + '</span>';
  row.querySelector('input').addEventListener('change', (e) => {
    if (e.target.checked) selected.add(t.id); else selected.delete(t.id);
    refreshBtn();
  });
  // HITO 2.2: clicking the NAME (not the checkbox) flies the camera to that territory.
  // Uses the bounding box already shipped in the payload - no reprojection, no wait. A
  // local UMAP would have been more informative but costs 29s per hub (measured), which
  // with 96 subtopics makes exploring unusable; zooming the existing coordinates is
  // instant and is what semantic zoom actually asks for.
  row.querySelector('.lname').addEventListener('click', (e) => {
    e.preventDefault(); e.stopPropagation();
    flyTo(t);
  });
  rowsEl.appendChild(row);
});
function flyTo(t) {
  const padX = Math.max((t.x1 - t.x0) * 1.35, 1e-3);
  const padY = Math.max((t.y1 - t.y0) * 1.35, 1e-3);
  const z = Math.min(Math.log2(Math.min(W / padX, H / padY)), fitZoom + 7);
  viewZoom = z;
  deckgl.setProps({
    initialViewState: {target: [(t.x0 + t.x1) / 2, (t.y0 + t.y1) / 2, 0], zoom: z,
                       minZoom: fitZoom - 1.5, maxZoom: fitZoom + 7,
                       transitionDuration: 650},
  });
  redrawLayers();
  document.getElementById('home').style.display = 'block';
}
document.getElementById('home').addEventListener('click', () => {
  viewZoom = fitZoom;
  deckgl.setProps({
    initialViewState: {target: [D.cx, D.cy, 0], zoom: fitZoom,
                       minZoom: fitZoom - 1.5, maxZoom: fitZoom + 7,
                       transitionDuration: 650},
  });
  redrawLayers();
  document.getElementById('home').style.display = 'none';
});
function refreshBtn() {
  const total = D.terr.filter(x => selected.has(x.id))
                      .reduce((s, x) => s + x.count, 0);
  btn.disabled = selected.size === 0;
  btn.textContent = selected.size === 0 ? 'Open selection in Network'
    : 'Open ' + selected.size + ' hub' + (selected.size > 1 ? 's' : '') +
      ' in Network (' + total.toLocaleString() + ' papers)';
}
// The host relays the app-wide pick on every render: mirror it here so the
// checkboxes never go stale (e.g. after 'Clear pick' in the Network tab).
window.addEventListener('message', (e) => {
  const d = e.data || {};
  if (d.frothSyncHubs === undefined) return;
  selected.clear();
  d.frothSyncHubs.forEach(id => selected.add(+id));
  document.querySelectorAll('.lrow').forEach(row => {
    row.querySelector('input').checked = selected.has(+row.dataset.terr);
  });
  refreshBtn();
});
btn.addEventListener('click', () => {
  try { window.parent.postMessage({frothHubs: Array.from(selected)}, '*'); }
  catch (e) {}
});
// Visibility: a territory row shows while its centroid is inside the viewport
// (selected rows always show, so a choice never vanishes mid-zoom).
let legendTimer = null;
function scheduleLegend(vs) {
  if (legendTimer) clearTimeout(legendTimer);
  legendTimer = setTimeout(() => updateLegend(vs), 120);
}
function updateLegend(vs) {
  const scale = Math.pow(2, vs.zoom);
  const halfW = (window.innerWidth || 1100) / 2 / scale;
  const halfH = (window.innerHeight || __H__) / 2 / scale;
  const [tx, ty] = vs.target;
  document.querySelectorAll('.lrow').forEach(row => {
    const t = D.terr.find(x => x.id === +row.dataset.terr);
    const visible = selected.has(t.id) ||
      (Math.abs(t.cx - tx) < halfW * 1.05 && Math.abs(t.cy - ty) < halfH * 1.05);
    row.style.display = visible ? 'flex' : 'none';
  });
}
updateLegend({zoom: fitZoom, target: [D.cx, D.cy]});
</script></body></html>""".replace("__DECK_CDN__", DECK_CDN) \
                          .replace("__PAYLOAD__", payload) \
                          .replace("__H__", str(height))
