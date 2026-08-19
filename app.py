"""
app.py - Froth mini web app: semantic search + interactive topic views.

Runs on your own PC:
    .venv\\Scripts\\python.exe -m streamlit run app.py

ARCHITECTURE - one set of GLOBAL filters (sidebar) governs EVERY tab:
    granularity (live re-cluster) + year range + hide noise + size-by-citations
    -> one filtered topic map (tm) + aligned vectors (V)
    -> Search ranks within it, Topic map draws it, Network rebuilds from it, Packed packs it.
This keeps all tabs telling the same story (no stale clusters per tab).

NOTE (future): a second input module "Task/Research" (attach instruction PDFs + textbox)
will plug into the same engine later (see CLAUDE.md).
"""
import hashlib
import io
import json
import zipfile

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from froth import cluster, config, embed, graph, palette, pull, sources, visualize
from froth import batch, export_obsidian, export_pack
from froth import gaps as gaps_mod
from froth import my_space
from froth import polish as polish_mod
from froth import review as review_mod

st.set_page_config(page_title="Froth",
                   page_icon=str(config.ROOT / "assets" / "froth_logo.png"),
                   layout="wide", initial_sidebar_state="expanded")
st.logo(str(config.ROOT / "assets" / "froth_logo.svg"))

# Stale-module guard: the file watcher is off, so a server that lived through a code
# update keeps OLD modules in memory while re-reading THIS file - and crashes with
# confusing TypeErrors. Turn that into a human instruction instead.
if getattr(visualize, "UI_CONTRACT", 0) != 3:
    st.error(":material/restart_alt: **Froth's modules are out of date in this "
             "running server.** Close it in the terminal (Ctrl+C) and start it again "
             "with `streamlit run app.py`. Refreshing the browser is not enough.")
    st.stop()

# When the sidebar is collapsed, its reopen chevron is nearly invisible - users never
# discover the filters (Batman's report). Dress it as an indigo pill with a label.
# (Targets a Streamlit testid: may need a touch-up after big Streamlit upgrades.)
st.html("""<style>
/* Custom-component iframes (froth bridge) render at a 300px default width
   (attr width=-1) instead of filling their block - force full width or the
   network/reading-guide canvases initialize squeezed and clicks miss. */
iframe.stCustomComponentV1 { width: 100% !important; }
[data-testid="stSidebarCollapsedControl"] {
  background: #6366f1; border-radius: 0 12px 12px 0;
  padding: 8px 14px 8px 8px; box-shadow: 0 2px 10px rgba(0,0,0,.45);
}
[data-testid="stSidebarCollapsedControl"] * { color: #ffffff !important; }
[data-testid="stSidebarCollapsedControl"]::after {
  content: "Filters & sources"; color: #ffffff;
  font-weight: 600; font-size: 13px; margin-left: 4px;
}
</style>""")

# Brand hero: flotation bubbles slowly rising behind the wordmark. The metaphor IS the
# product: in froth flotation the valuable mineral rides bubbles to the top - in Froth
# the relevant papers do. (Decorative CSS requested explicitly; kept subtle and cheap.)
_HERO = """
<style>
.froth-hero {position: relative; height: 130px; overflow: hidden; margin-bottom: 0.2rem;}
.froth-hero h1 {font-size: 40px; font-weight: 600; margin: 34px 0 4px 0; position: relative;
                z-index: 2; letter-spacing: -0.5px;}
.froth-hero .froth-tag {color: #a1a1aa; font-size: 14px; margin: 0; position: relative; z-index: 2;}
.froth-bubble {position: absolute; bottom: -30px; border-radius: 50%; z-index: 1;
               animation: froth-rise linear infinite;}
@keyframes froth-rise {
  0%   {transform: translateY(0); opacity: 0;}
  15%  {opacity: 0.45;}
  85%  {opacity: 0.25;}
  100% {transform: translateY(-170px); opacity: 0;}
}
</style>
<div class="froth-hero">
  <span class="froth-bubble" style="left: 6%;  width: 18px; height: 18px; background: #6366f1; animation-duration: 11s;"></span>
  <span class="froth-bubble" style="left: 15%; width: 9px;  height: 9px;  background: #14b8a6; animation-duration: 9s;  animation-delay: 2s;"></span>
  <span class="froth-bubble" style="left: 27%; width: 14px; height: 14px; background: #8b5cf6; animation-duration: 13s; animation-delay: 5s;"></span>
  <span class="froth-bubble" style="left: 41%; width: 7px;  height: 7px;  background: #378ADD; animation-duration: 8s;  animation-delay: 1s;"></span>
  <span class="froth-bubble" style="left: 55%; width: 22px; height: 22px; background: #6366f1; animation-duration: 14s; animation-delay: 3s;"></span>
  <span class="froth-bubble" style="left: 68%; width: 10px; height: 10px; background: #14b8a6; animation-duration: 10s; animation-delay: 6s;"></span>
  <span class="froth-bubble" style="left: 79%; width: 15px; height: 15px; background: #8b5cf6; animation-duration: 12s; animation-delay: 0.5s;"></span>
  <span class="froth-bubble" style="left: 90%; width: 8px;  height: 8px;  background: #378ADD; animation-duration: 9s;  animation-delay: 4s;"></span>
  <h1>Froth</h1>
  <p class="froth-tag">Relevant papers float to the top - like value on a flotation bubble.</p>
</div>
"""


def _ieee_citation(row) -> str:
    """Build an IEEE-style reference from a paper row.

    'Fareed Ahmad Azizi; Lev Filippov' -> 'F. A. Azizi, L. Filippov, "Title," Journal, year.'
    """
    names = [a.strip() for a in str(row.get("authors", "")).split(";") if a.strip()]
    formatted = []
    for name in names[:6]:
        parts = name.split()
        if len(parts) >= 2:
            initials = ". ".join(p[0] for p in parts[:-1])
            formatted.append(f"{initials}. {parts[-1]}")
        else:
            formatted.append(name)
    if len(names) > 6:
        formatted.append("et al.")
    authors = ", ".join(formatted) if formatted else "Unknown"
    journal = f" {row['source']}," if row.get("source") else ""
    doi = f" DOI: {str(row['doi']).replace('https://doi.org/', '')}." if row.get("doi") else ""
    return f'{authors}, "{row["title"]},"{journal} {int(row["year"])}.{doi}'


def _must_read_of_island(row: pd.Series, full_map: pd.DataFrame) -> bool:
    """Is this paper above the must-read line of ITS subtopic?

    Computed on the FULL map, never on whatever a view happens to have drawn. The Network
    tab hands the panel a 400-paper slice, so measuring there would make the same paper a
    must-read in one tab and not in another, from the same data. Same helper and same
    ordering the reading guide (visualize.py) and My space use, so the three agree.
    """
    if int(row.get("cluster", -1)) == -1:
        return False
    part = full_map[full_map["cluster"] == row["cluster"]].sort_values(
        "citations", ascending=False)
    if part.empty:
        return False
    return row.name in part.index[:visualize._must_count(part["citations"].tolist())]


@st.fragment
def paper_detail_panel(row: pd.Series, tm: pd.DataFrame, key: str,
                       full_map: pd.DataFrame | None = None) -> None:
    """Batman's 'Know more' flow, reusable across every view (progressive disclosure):
    a click might be curiosity or a slip - first a discreet ask, the full record only
    on confirmation. `key` keeps each view's selection state independent.

    `full_map` is the whole filtered corpus, used only to decide the must-read flag when
    filing; it falls back to `tm` for views that already pass the full map.

    A FRAGMENT, because of what filing is for. In Streamlit any button reruns the whole
    page, and that reloads the map's iframe: you lose the zoom, the pan, and the physics
    re-settles. Tolerable once; unbearable when the point of the feature is to file five
    papers in a row while reading the map. Inside a fragment a button redraws only this
    panel and the canvas never notices. The one action that DOES need the page back is
    "Set as seed", which changes what the map draws: it asks for a full rerun explicitly.
    """
    full_map = tm if full_map is None else full_map
    # A click in Network/Packed opens this panel BELOW a 780px iframe, out of view -
    # so pop a toast (jumps in the corner, visible without scrolling) when the
    # selection changes, so the user knows the details are down there.
    if st.session_state.get(f"toasted_{key}") != row.name:
        st.session_state[f"toasted_{key}"] = row.name
        st.toast(f"Selected: {str(row['title'])[:55]} - open 'Know more' just below",
                 icon=":material/read_more:")
    left, mid, right = st.columns([4, 1.5, 1.5], vertical_alignment="center")
    with left:
        st.caption(f"Selected: **{row['title'][:90]}**")
    with mid:
        if st.button("Know more", icon=":material/read_more:", key=f"more_{key}_{row.name}"):
            st.session_state[f"detail_{key}"] = row.name
    with right:
        # Filing lives OUT here, not inside the record: the whole point (Batman 2026-08-13)
        # is to file while you are reading the map, and making you open a card first is the
        # friction he asked to remove. One click, no questions: stage and island are things
        # the map already knows, so asking would be theatre.
        filed = my_space.find(row)
        if filed:
            st.caption(f":material/bookmark_added: In your logbook · *{filed['stage']}*")
        elif st.button("To logbook", icon=":material/bookmark_add:",
                       key=f"log_{key}_{row.name}",
                       help="File this paper in My space as 'to read', with its topic "
                            "and subtopic filled in"):
            my_space.add(row, SLUG, topic_title=config.TOPIC,
                         island=str(row.get("label", "")),
                         must_read=_must_read_of_island(row, full_map))
            st.toast(f"Filed as 'to read': {str(row['title'])[:50]}",
                     icon=":material/bookmark_added:")
            # Redraw THIS panel so the button becomes "in your logbook" right away.
            # Without it the label only catches up on the next interaction, and a button
            # that looks unpressed after a successful press reads as a failure - you click
            # again. Fragment scope on purpose: the map must not reload (that is the whole
            # reason this panel is a fragment).
            st.rerun(scope="fragment")
    if st.session_state.get(f"detail_{key}") != row.name:
        return
    with st.container(border=True):
        rank = int((tm["citations"] > row["citations"]).sum()) + 1
        st.markdown(f"**{row['title']}**")
        st.caption(f"{row['authors']}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Citation rank", f"#{rank} of {len(tm)}")
        c2.metric("Year", int(row["year"]))
        c3.metric("Citations", int(row["citations"]))
        c4.metric("Relevance", f"{row['relevance']:.2f}" if "relevance" in tm.columns else "-")
        if int(row["citations"]) == 0 and int(row["year"]) >= 2024:
            st.caption(":material/fiber_new: 0 citations = a recent paper that has not "
                       "had time to be cited yet - the frontier, not low quality.")
        st.caption(f"Subtopic: *{row['label']}*"
                   + (f" · Keywords: *{row['keywords']}*" if row.get("keywords") else "")
                   + (f" · Journal: *{row['source']}*" if row.get("source") else ""))
        links = []
        if row.get("doi"):
            links.append(f"[Publisher (DOI)]({row['doi']})")
        if row.get("oa_url"):
            links.append(f"[Free open-access PDF]({row['oa_url']})")
        if links:
            st.markdown(" · ".join(links))
        st.caption("Citations (copy button appears on hover):")
        st.caption("In-text")
        st.code(_in_text_citation(row), language=None)
        st.caption("Bibliographic reference (APA)")
        st.code(_apa_citation(row), language=None)
        st.caption("Bibliographic reference (IEEE)")
        st.code(_ieee_citation(row), language=None)
        # Filing is NOT here: it is the "To logbook" button at the top of this panel, one
        # click, no card to open. That reverses Batman 2026-07-20 ("olvidate de traerlo del
        # know more en los otros modulos"), which is his call to make and he made it again
        # with a better reason (2026-08-13): "si estoy viendo la distribucion o como se
        # relacionan topics, lo pueda agregar facil ahi mismo, sin necesidad de entrar en
        # log y buscarlo". The old rule sent you to My space to hunt for a paper you were
        # already looking at, which is the friction that kills the habit.
        #
        # "Set as seed" is different in kind, not just in name: it does not file anything
        # anywhere, it points Network + the similarity list at this paper. Stored by its
        # OpenAlex id (a column already on every tm), which survives granularity changes -
        # unlike a positional row index, it never goes stale when the map re-clusters.
        if st.button("Set as seed", icon=":material/target:", key=f"seed_{key}_{row.name}"):
            st.session_state["seed_id"] = str(row["id"])
            st.session_state["seed_title"] = str(row["title"])
            st.toast(f"Seed set: {str(row['title'])[:55]} - see it in Network",
                     icon=":material/target:")
            # This one has to escape the fragment: the seed changes what Network draws
            # (the pin, and the similarity list beneath it), and a fragment-only rerun
            # would leave the map showing the old seed while the panel claimed otherwise.
            st.rerun(scope="app")


def _selected_row(event, tm: pd.DataFrame):
    """Map a plotly selection event back to the paper row via customdata (or None)."""
    points = event.selection.points if event and event.selection else []
    if not points:
        return None
    cd = points[0].get("customdata")
    if cd is None:
        return None
    row_id = int(cd[0] if isinstance(cd, (list, tuple)) else cd)
    return tm.loc[row_id] if row_id in tm.index else None


def _split_authors(row) -> list[str]:
    return [a.strip() for a in str(row.get("authors", "")).split(";") if a.strip()]


def _apa_citation(row) -> str:
    """Full bibliographic reference, APA style: Last, F. M., & Last, F. (Year). Title. Journal. DOI-url"""
    formatted = []
    for name in _split_authors(row)[:20]:
        parts = name.split()
        last = parts[-1]
        initials = " ".join(p[0] + "." for p in parts[:-1])
        formatted.append(f"{last}, {initials}" if initials else last)
    if len(formatted) > 1:
        authors = ", ".join(formatted[:-1]) + ", & " + formatted[-1]
    else:
        authors = formatted[0] if formatted else "Unknown"
    journal = f" {row['source']}." if row.get("source") else ""
    doi = f" {row['doi']}" if row.get("doi") else ""
    return f"{authors} ({int(row['year'])}). {row['title']}.{journal}{doi}"


def _in_text_citation(row) -> str:
    """In-text citation, author-year style: (Azizi et al., 2026) / (Smith & Jones, 2020)."""
    names = _split_authors(row)
    if not names:
        return f"(Unknown, {int(row['year'])})"
    lasts = [n.split()[-1] for n in names]
    if len(lasts) == 1:
        who = lasts[0]
    elif len(lasts) == 2:
        who = f"{lasts[0]} & {lasts[1]}"
    else:
        who = f"{lasts[0]} et al."
    return f"({who}, {int(row['year'])})"


def render_topic_picker(key: str = "landing") -> None:
    """The topic card: pick a mapped topic or harvest a NEW one from the UI (Phase 6.7).
    Used on the landing, on a fresh install, AND in the sidebar so the corpus can be
    changed WITHOUT leaving the current view (Batman's request). `key` keeps the two
    placements' widgets independent. Switching only sets the topic; the mode and the
    active tab are untouched, and a reset flag lets the app re-fit the sliders."""
    known = config.known_topics()
    # Full titles in the dropdown (they were cut to 80 chars and looked chopped);
    # the selectbox itself ellipsizes only the closed field, the menu shows all.
    labels = [f"{t}{'' if ready else '  (not harvested yet)'}" for t, ready in known]
    current_idx = next((i for i, (t, _) in enumerate(known)
                        if t == st.session_state.get("topic")), 0)
    picked = st.selectbox("Mapped topics", labels, index=current_idx,
                          label_visibility="collapsed", key=f"topic_sel_{key}")
    picked_title, picked_ready = known[labels.index(picked)]
    pending = picked_title != st.session_state.get("topic") and picked_ready
    if st.button("Switch to this topic", icon=":material/sync_alt:",
                 key=f"switch_topic_{key}", type="primary" if pending else "secondary",
                 disabled=not pending):
        st.session_state["topic"] = picked_title
        st.session_state["corpus_changed"] = True
        st.rerun()

    new_title = st.text_input("...or map a NEW topic (paste a thesis title)",
                              placeholder="e.g. Bioleaching of copper tailings using "
                                          "acidophilic bacteria", key=f"new_topic_{key}")
    # Onboarding (Batman): new users can harvest with OpenAlex alone, or connect free
    # keys for a fuller sweep. Say it plainly, don't force it.
    if config.get_key("ELSEVIER_API_KEY"):
        st.caption(":material/check_circle: Harvesting from **OpenAlex + Crossref + "
                   "Semantic Scholar + Scopus** - your keys are connected.")
    else:
        st.caption(":material/info: Harvest runs on **OpenAlex** (free, no account "
                   "needed). Connecting your free keys (ScienceDirect/Scopus, Semantic "
                   "Scholar) finds MORE papers - it takes ~5 min. Open **Filters & "
                   "sources** in the left sidebar → *Connect institutional account*, or "
                   "see `docs/GET_YOUR_KEYS.md`.")
    ready_to_harvest = bool(new_title.strip())
    if st.button("Harvest & map it", icon=":material/rocket_launch:",
                 key=f"harvest_{key}", type="primary" if ready_to_harvest else "secondary",
                 disabled=not ready_to_harvest):
        title = new_title.strip()
        with st.status("Building the map for your topic...", expanded=True) as status:
                config.set_topic(title)
                st.write(f"search terms: {', '.join(config.SEARCH_TERMS[:5])}...")
                status.update(label="Harvesting papers (OpenAlex + Crossref + Scopus + S2)...")
                new_df = pull.pull_papers(per_term=15)
                if new_df.empty:
                    status.update(label="No papers found - try a longer title", state="error")
                else:
                    st.write(f"{len(new_df)} papers with abstract")
                    status.update(label="Embedding abstracts...")
                    new_v = embed.embed_papers(new_df)
                    embed.save_embeddings(new_v)
                    new_df["relevance"] = embed.relevance_to_topic(new_v)
                    new_df.to_parquet(config.DATA_PROCESSED / "papers.parquet", index=False)
                    status.update(label="Clustering + relevance gate...")
                    # The GATE (note 43), not the fixed 0.55 threshold this used to call
                    # via cluster.build_topic_map(). Measured 2026-08-03 on tungsten
                    # skarns: fixed threshold kept 81 of 5,114 papers and 2 subtopics; the
                    # hub-level contrastive gate kept 438 and 5. Every corpus already on
                    # disk went through the gate, so harvesting a NEW topic from this
                    # button produced a visibly worse map than any older one - the same
                    # pipeline written twice, only one of them corrected.
                    gate = batch.remap_topic(title)
                    if gate["status"] == "FAILED":
                        st.error(f"Relevance gate failed: {gate['error']}")
                    else:
                        st.write(f"{gate['relevant']} papers kept in "
                                 f"{gate['clusters']} subtopics")
                    config.register_topic(title)
                    st.session_state["corpus_changed"] = True
                    status.update(label="Done - welcome to your map", state="complete")
                    st.session_state["topic"] = title
                    st.rerun()


def _data_version() -> float:
    """Sum of data-file modification times. Used as a cache key: if the pipeline rewrites
    the files (new pull, new filter...), the key changes and caches refresh themselves."""
    files = [config.DATA_PROCESSED / "papers.parquet",
             config.DATA_PROCESSED / "topic_map.parquet",
             config.DATA_EMBEDDINGS / "vectors.npy"]
    return sum(f.stat().st_mtime for f in files if f.exists())


@st.cache_resource
def load_data(slug: str, version: float):
    """Load papers, vectors and topic map OF `slug` (cached per topic+version).

    Resolves every path from the slug. It used to take `slug` only as a cache key and
    read config.DATA_PROCESSED, a global that set_topic() rewrites - so the answer
    depended on when the call happened, not on what was asked for. A fragment rerun does
    not re-execute the top of the script, so a cache miss during one could read another
    topic's files and store them under this slug's key, pinning a foreign corpus's
    subtopic names onto these papers until the cache was cleared. With 21 corpora on
    disk here, that exposure is larger than it was in the v1 edition.
    """
    paths = config.paths_for(slug)
    df = pd.read_parquet(paths["processed"] / "papers.parquet")
    vectors = embed.load_embeddings(paths["embeddings"])
    topic_map = cluster.load_topic_map(paths["processed"])
    return df, vectors, topic_map


@st.cache_data
def recluster(min_cluster_size: int, slug: str, version: float) -> pd.DataFrame:
    """Re-cluster the (fixed, cached) 2D map with a new granularity and re-label.

    UMAP positions never change here - only the grouping. HDBSCAN + labeling on ~120
    points is milliseconds, which is why the slider feels instant."""
    _, _, topic_map = load_data(slug, version)
    xy = topic_map[["x", "y"]].to_numpy()
    labels = cluster.cluster_points(xy, min_cluster_size=min_cluster_size)
    names = cluster.label_clusters(topic_map, labels)
    out = topic_map.copy()
    out["cluster"] = labels
    out["label"] = [names[c] for c in labels]
    return out


@st.cache_data
def filtered_state(min_cluster_size: int, years: tuple, slug: str, version: float):
    """The single source of truth every tab consumes: re-clustered topic map filtered by
    year, plus the embedding vectors aligned row-by-row with it."""
    df, vectors, _ = load_data(slug, version)
    rel_mask = (df["relevance"] >= config.RELEVANCE_THRESHOLD).to_numpy()
    v_relevant = vectors[rel_mask]                      # aligned with the topic map rows

    tm = recluster(min_cluster_size, slug, version)
    y_mask = (tm["year"] >= years[0]) & (tm["year"] <= years[1])
    return tm[y_mask].reset_index(drop=True), v_relevant[y_mask.to_numpy()]


@st.cache_data
def gaps_and_draft(min_cluster_size: int, years: tuple, slug: str, version: float):
    """Measured gap candidates + the review scaffold, from the SAME subtitled state as
    every other tab (so the gaps you see match the map you see)."""
    tm, v = subtitled_state(min_cluster_size, years, slug, version)
    gap_table = gaps_mod.find_gaps(tm, v)
    draft_text = gaps_mod.draft_review(tm, v, gap_table)
    return gap_table, draft_text


@st.cache_data
def task_ranking(task_text: str, pdf_contents: tuple, min_cluster_size: int,
                 years: tuple, slug: str, version: float, k: int):
    """The Task module engine: textbox + instruction PDFs -> one mean-pooled query vector
    -> papers ranked for THIS task. Cached by content so re-runs are instant."""
    import io
    from pypdf import PdfReader

    texts = [task_text] if task_text.strip() else []
    for raw in pdf_contents:
        reader = PdfReader(io.BytesIO(raw))
        texts.append("\n".join(page.extract_text() or "" for page in reader.pages))

    q_vec = embed.embed_texts_mean(texts)
    if q_vec is None:
        return None
    tm_f, v_f = subtitled_state(min_cluster_size, years, slug, version)
    return embed.rank_by_vector(q_vec, tm_f, v_f, k=k)


def _cap_for_heavy_views(tm: pd.DataFrame, v: np.ndarray):
    """Phase D.5 scale guard, v2 (Batman's screenshot review, 2026-07-16).

    v1 took the corpus-wide most-cited papers - but famous papers are spread across ALL
    subtopics, so the physics got scraps of ~60 clusters instead of whole islands and the
    map read as confetti. v2 keeps WHOLE CLUSTERS: rank subtopics by total citations,
    admit the biggest ones complete (their most-cited papers if one alone exceeds the
    budget) until config.HEAVY_VIEW_MAX_PAPERS is spent. Few complete islands beat many
    fragments - the '200-paper era' look the product wants. Returns (tm, v, was_capped);
    index reset so vectors stay positionally aligned. The Atlas draws the FULL corpus.

    v3 (2026-08-13, Batman: "aca literal ningun paper es puente de dos temas"). v2 admitted
    WHOLE clusters, which was right for a 250-paper corpus and starves a big one. Measured on
    the 5752-paper thesis corpus: subtopic 39 (246 papers) was admitted whole, subtopic 4 took
    the remaining 154, budget gone - the Network drew 2 of 44 subtopics. With two islands no
    paper can bridge two subtopics, so the boundary rule downstream had nothing to find and
    reported zero no matter how it was tuned. Capping each cluster's share fixes the cause.
    Measured trade-off on that corpus (same 400-paper budget): no cap = 2 islands / 0 bridges;
    60 = 8 / 17; 30 = 14 / 25; 20 = 21 / 23. Batman chose 30: the most bridges without the
    islands shrinking back into the confetti v2 was written to avoid.

    v4 (2026-08-29). Asked three times whether the bridge papers were real bridges, Batman
    answered: "son de temas que no conozco y no puedo juzgar". He was right, and the map was
    at fault. Islands were ranked by TOTAL CITATIONS, and geology cites far more heavily than
    mineral processing, so petrology and geochronology took the places while his own subject
    missed the cut. The bridges ran from Archean cratons to zircons: real bridges, in a
    literature that is not his.

    Ranking by the island's mean RELEVANCE to the thesis title instead. That number already
    exists per paper, from the contrastive gate of phase 5; nothing new is computed.

    Measured on the 5752-paper corpus, sharing the same 400-paper budget across 14 islands:
        rule                  processing papers   mean relevance   first islands
        by citations (v3)             34%             0.694        lavas, e-waste
        by mean relevance             44%             0.716        nano-bubbles, coal fines
        relevance x size              42%             0.708        pegmatites, coal fines
        relevance x citations         33%             0.703        pegmatites, lavas
    The corpus itself is 46% processing, so ranking by relevance very nearly removes the
    geology bias rather than merely reducing it. Note the trap: the correlation between an
    island's relevance and its being processing is +0.04, which looks like proof that
    relevance cannot separate them. It is the wrong statistic. The middle of the ranking is
    full of rare-metal granite geology that IS relevant to a thesis on Beauvoir; what
    relevance does is push the off-topic geology (lavas 0.658, zircons 0.719) below his own
    subject (nano-bubbles 0.811, coal fines 0.773), which is what the ordering needs."""
    cap = config.HEAVY_VIEW_MAX_PAPERS
    if len(tm) <= cap:
        return tm, v, False
    per_cluster = config.NETWORK_MAX_PER_CLUSTER
    weight = tm.groupby("cluster")["relevance"].mean().sort_values(ascending=False) \
        if "relevance" in tm.columns \
        else tm.groupby("cluster")["citations"].sum().sort_values(ascending=False)

    # Ranking by relevance promotes his own subject, and it promotes the junk hub with it:
    # "women, gender, feminist" scores 0.698 because the title's element list contains Be,
    # which is also an ordinary English word. Relevance cannot tell them apart, but citation
    # links can: that island makes ONE cross-island citation in 105 papers where the
    # lepidolite flotation island makes 1.58 per paper. Demoted to the end of the queue, not
    # dropped - a poorly connected island can still be the interesting frontier, so it loses
    # its place only when something better wants it.
    try:
        isolated = graph.isolated_islands(tm)
        if isolated:
            order = [c for c in weight.index if c not in isolated] + \
                    [c for c in weight.index if c in isolated]
            weight = weight.reindex(order)
    except Exception:
        pass                                   # no reference data: rank on relevance alone
    keep_parts, budget = [], cap
    for c in weight.index:
        if c == -1 or budget <= 0:
            continue
        part = tm[tm["cluster"] == c]
        take = min(len(part), per_cluster, budget)  # its most-cited slice, never the whole hog
        keep_parts.append(part.nlargest(take, "citations"))
        budget -= take
    keep = pd.concat(keep_parts).index.to_numpy() if keep_parts else tm.index[:cap].to_numpy()
    return tm.loc[keep].reset_index(drop=True), v[keep], True


@st.cache_data(show_spinner="Drawing the Atlas (WebGL)...")
def atlas_view(min_cluster_size: int, years: tuple, slug: str, version: float) -> str:
    """The Atlas HTML for the CURRENT view: every paper as a WebGL point (deck.gl via
    CDN - no extra deps), one own hue per subtopic, brand tooltip, click -> Know-more
    through the same frothSelect bridge contract as every other view."""
    from froth import atlas
    tm, _v = subtitled_state(min_cluster_size, years, slug, version)
    return atlas.atlas_html(tm)


@st.cache_data(show_spinner=False)
def harvest_size(slug: str, version: float) -> int:
    """Rows harvested BEFORE the relevance gate (papers.parquet), for the gate caption."""
    try:
        return len(pd.read_parquet(config.paths_for(slug)["processed"] / "papers.parquet",
                                   columns=["title"]))
    except Exception:
        return 0


def _hub_subset(tm: pd.DataFrame, v: np.ndarray, hubs: tuple):
    """Batman's architecture (2026-07-17): the Network draws the hubs HE picked in the
    Atlas legend - whole clusters, physics-viable. If the pick is still too big for
    physics, keep its most-cited slice and say so."""
    keep = tm["cluster"].isin(hubs).to_numpy()
    tm2, v2 = tm[keep].reset_index(drop=True), v[keep]
    trimmed = len(tm2) > 1000
    if trimmed:
        idx = tm2["citations"].nlargest(1000).index.to_numpy()
        tm2, v2 = tm2.loc[idx].reset_index(drop=True), v2[idx]
    return tm2, v2, trimmed


def _hub_menu(tm: pd.DataFrame, widget_key: str) -> None:
    """Collapsible subtopic picker with a soft pulsing glow on its header (Batman
    2026-07-17: 'que brille con intermitencia para indicar que se puede plegar').
    Lives in Network AND the reading guide; shares ONE selection with the Atlas
    legend via st.session_state['atlas_hubs'] - pick anywhere, it drives everywhere."""
    st.markdown("""<style>
      div[class*="st-key-hubmenu_"] details summary {
        border-radius: 10px;
        animation: hubglow 2.4s ease-in-out infinite; }
      @keyframes hubglow {
        0%, 100% { box-shadow: 0 0 0 0 rgba(99,102,241,0); }
        50%      { box-shadow: 0 0 12px 2px rgba(99,102,241,.45); } }
    </style>""", unsafe_allow_html=True)
    # Each subtopic carries its distance to the thesis title, and the weak half is marked.
    # Shown as INFORMATION, never as a filter: measured on this corpus, selecting the
    # most relevant islands does not concentrate his own field (44% processing against 46%
    # for no filter at all), because his title is half method and half deposit and both
    # halves are legitimately his. So the number is here to be read, and the picking stays
    # his. A control that felt like focus without delivering it would be worse than none.
    parts = tm[tm["cluster"] != -1].groupby("cluster")
    rows = [(int(c), str(g["label"].iloc[0]), len(g),
             float(g["relevance"].mean()) if "relevance" in g.columns else 0.0)
            for c, g in parts]
    rows.sort(key=lambda t: -t[3])
    rels = sorted(r[3] for r in rows)
    weak = rels[len(rels) // 2] if rels else 0.0        # the lower half, by this corpus
    try:
        far = graph.isolated_islands(tm)
    except Exception:
        far = set()
    def _tag(c, rel):
        if c in far:
            return "○ "                                  # cites nothing else on this map
        return "  " if rel <= weak else "● "
    options = {f"{_tag(c, rel)}{lab[:34]} · {n} · {rel:.2f}": c for c, lab, n, rel in rows}
    by_id = {c: k for k, c in options.items()}
    current = tuple(st.session_state.get("atlas_hubs", ()))
    wkey = f"hubsel_{widget_key}"
    wanted = [by_id[c] for c in current if c in by_id]
    if wkey in st.session_state and set(st.session_state[wkey]) != set(wanted):
        st.session_state[wkey] = wanted            # external pick (Atlas/other menu) wins
    def _apply_pick() -> None:
        # on_change callback: runs BEFORE the rerun, so every tab reads the fresh pick
        # in the same pass - no compare-and-rerun bounce (the add/remove glitches).
        picked = tuple(sorted(options[k] for k in st.session_state.get(wkey, [])))
        if picked:
            st.session_state["atlas_hubs"] = picked
        else:
            st.session_state.pop("atlas_hubs", None)

    with st.container(key=f"hubmenu_{widget_key}"):
        with st.expander(":material/tune: Choose the subtopics to draw", expanded=False):
            st.caption("Sorted by closeness to your thesis title, with that number last. "
                       "**●** = the closer half · **○** = cites nothing else on this map. "
                       "Marks, not filters: on this corpus picking only the closest "
                       "subtopics does not sharpen the view, because your title is half "
                       "method and half deposit and both halves are yours.")
            st.multiselect(
                "Subtopics (empty = the biggest ones)", list(options),
                default=wanted if wkey not in st.session_state else None,
                key=wkey, label_visibility="collapsed", on_change=_apply_pick,
                placeholder="Empty = the most relevant subtopics")


@st.cache_data
def network_view(min_cluster_size: int, years: tuple, hide_noise: bool,
                 slug: str, version: float, hubs: tuple = (),
                 seed_node: int | None = None) -> str:
    """Rebuild the paper network FROM THE SUBTITLED STATE so its clusters/colors/names
    always match the other tabs (no stale pipeline clustering). With `hubs` (picked in
    the Atlas legend) it draws exactly those subtopics; otherwise the biggest ones."""
    tm, v = subtitled_state(min_cluster_size, years, slug, version)
    total_in_view = len(tm)
    n_noise_total = int((tm["cluster"] == -1).sum())
    if hide_noise:
        keep = (tm["cluster"] != -1).to_numpy()
        tm, v = tm[keep].reset_index(drop=True), v[keep]
    if hubs:
        tm, v, _ = _hub_subset(tm, v, hubs)
        capped = True
    else:
        tm, v, capped = _cap_for_heavy_views(tm, v)
    G = graph.build_similarity_graph(tm, v)
    n_weak = 0
    if capped:
        # Batman 2026-07-17: the rim of edge-less papers around big-corpus networks is
        # visual noise (physics flings them outward). Drop degree-0 nodes here; they
        # remain findable in Search. Small corpora keep their flagged loners (rule 7).
        weak = [i for i in list(G.nodes) if G.degree(i) == 0]
        n_weak = len(weak)
        G.remove_nodes_from(weak)
    drawn = len(G.nodes)
    drawn_clusters = tm.loc[list(G.nodes), "cluster"] if drawn else pd.Series(dtype=int)
    k_subtopics = int(drawn_clusters[drawn_clusters != -1].nunique())
    rest = total_in_view - drawn - n_weak
    summary = [f"Drawn: {drawn} papers · {k_subtopics} subtopics"]
    if n_weak:
        summary.append(f"Hidden: {n_weak} weak-linked (in Search)")
    if rest > 0:
        summary.append(f"Not drawn: {rest} papers outside this pick"
                       + (f" (incl. {n_noise_total} noise)" if not hide_noise else ""))
    elif hide_noise and n_noise_total:
        summary.append(f"Hidden: {n_noise_total} noise papers (toggle in sidebar)")
    # One OWN hue per cluster actually present (whole-cluster subset -> few of them),
    # biggest first so the dominant islands take the most distinct hues. Kills the
    # 10-color recycling that painted seven subtopics the same purple.
    present = tm[tm["cluster"] != -1]["cluster"].value_counts().index.tolist()
    hues = palette.territory_hues(len(present))
    # Condensed cartography (Batman 2026-07-18): drawn hubs keep their GLOBAL UMAP
    # spots, so far-apart picks left a mostly-empty canvas and 700 dots looked like
    # dust. Keep each hub's INTERNAL structure intact (offsets to its centroid),
    # compress the emptiness BETWEEN hubs (sqrt pull of centroids toward the common
    # center - real atlases shrink oceans too), then refit the whole thing to the
    # canvas. Neighboring hubs stay neighbors; the screen stays full.
    import math
    xs = tm["x"].to_numpy(dtype=float)
    ys = tm["y"].to_numpy(dtype=float)
    cl_arr = tm["cluster"].to_numpy()
    cx = {c: float(xs[cl_arr == c].mean()) for c in np.unique(cl_arr)}
    cy = {c: float(ys[cl_arr == c].mean()) for c in np.unique(cl_arr)}
    gx = float(np.mean(list(cx.values())))
    gy = float(np.mean(list(cy.values())))
    dmax = max((math.hypot(cx[c] - gx, cy[c] - gy) for c in cx), default=1.0) or 1.0
    cond = {}
    for c in cx:
        dx, dy = cx[c] - gx, cy[c] - gy
        d = math.hypot(dx, dy)
        k = (math.sqrt(d / dmax) * dmax * 0.55 / d) if d > 1e-9 else 0.0
        cond[c] = (gx + dx * k, gy + dy * k)
    nx = np.array([cond[c][0] + (x - cx[c]) for x, c in zip(xs, cl_arr)])
    ny = np.array([cond[c][1] + (y - cy[c]) for y, c in zip(ys, cl_arr)])
    span = max(float(nx.max() - nx.min()), float(ny.max() - ny.min()), 1e-6)
    sc = 10.5 / span                               # network_html scales world x90 -> ~950px
    seed_xy = {int(i): (float((nx[j] - nx.mean()) * sc), float((ny[j] - ny.mean()) * sc))
               for j, i in enumerate(tm.index)}
    # Adaptive call: only pass kwargs the loaded module actually accepts, so even a
    # stale in-memory visualize degrades gracefully instead of raising TypeError.
    import inspect
    accepted = inspect.signature(visualize.network_html).parameters
    kwargs = {k: v for k, v in
              (("colors", {int(c): hues[i] for i, c in enumerate(present)}),
               ("positions", seed_xy), ("summary_lines", summary),
               # Checked against THIS function's own graph: a seed that got dropped as
               # weak-linked, or that sits outside the picked hubs, degrades to "no
               # marker" instead of raising.
               ("seed_id", seed_node if seed_node in G.nodes else None))
              if k in accepted}
    return visualize.network_html(G, **kwargs)


# Phase 7.9: a tiny vanilla component that hosts our interactive HTML and returns
# the paper clicked INSIDE it (components.html renders but never listens).
_bridge = components.declare_component("froth_bridge",
                                       path=str(config.ROOT / "froth" / "bridge"))


def _subtitle_cache_file(slug: str, version: float, mcs: int, years: tuple):
    """Where this exact view's subtopic names live on disk.

    Naming the subtopics is the ONLY startup step that still needs SPECTER, and st.cache_data
    lives in RAM: it dies with the server, so every launch paid for it again. The key covers
    everything the names depend on (data version, granularity, year window), so a change in
    any of them misses the cache and recomputes. Rule 9 is intact: nothing is a fixed default,
    it is still measured per corpus - just not measured twice for the same question."""
    key = f"{version}|{mcs}|{years[0]}-{years[1]}"
    digest = hashlib.sha1(key.encode()).hexdigest()[:12]
    return config.paths_for(slug)["processed"] / f"subtitles_{digest}.json"


@st.cache_data(show_spinner="Naming the subtopics (reading abstracts)...")
def subtitled_state(min_cluster_size: int, years: tuple, slug: str, version: float):
    """Phase 7.1b v2: filtered state with KEYPHRASE cluster titles (Batman: the
    truncated sentences read like Bibles). Every view and export consumes THIS,
    so names never diverge between tabs. `label` = the short keyphrase title;
    `summary` = the full centroid sentence for hovers; `keywords` = the old
    c-TF-IDF terms, kept for the know-more panel."""
    tm_f, v_f = filtered_state(min_cluster_size, years, slug, version)

    cache_file = _subtitle_cache_file(slug, version, min_cluster_size, years)
    subs = None
    if cache_file.exists():
        try:
            raw = json.loads(cache_file.read_text(encoding="utf-8"))
            subs = {int(c): (t, s) for c, (t, s) in raw.items()}
        except Exception:
            subs = None                              # corrupt or older format: just recompute
    if subs is None:
        subs = review_mod.cluster_subtitles(tm_f, v_f)   # {cluster: (title, sentence)}
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps({str(c): list(v) for c, v in subs.items()}, ensure_ascii=False),
                encoding="utf-8")
        except Exception:
            pass                                     # a read-only install still works, just slower
    tm2 = tm_f.copy()
    tm2["keywords"] = tm2["label"]
    tm2["label"] = [subs.get(int(c), (lbl, ""))[0]
                    for c, lbl in zip(tm2["cluster"], tm2["label"])]
    tm2["summary"] = [subs.get(int(c), ("", ""))[1] for c in tm2["cluster"]]
    return tm2, v_f


@st.cache_data(show_spinner=False)
def similarity_anchors(min_cluster_size: int, years: tuple, slug: str, version: float):
    """Phase 7.7, rule 9: the search-score badge thresholds are MEASURED, not invented.
    m_in = mean cosine between papers of the SAME subtopic (what 'clearly related'
    looks like in this corpus); m_out = mean cosine across different subtopics."""
    tm_f, v_f = filtered_state(min_cluster_size, years, slug, version)
    # Scale guard (D.5): the pairwise matrix is O(n^2) - at 16k papers that is ~2 GB.
    # These anchors are MEANS over pair populations, so a 3k random sample estimates
    # them with negligible error at a fraction of the memory.
    if len(v_f) > 3000:
        pick = np.random.default_rng(0).choice(len(v_f), 3000, replace=False)
        tm_f, v_f = tm_f.iloc[pick], v_f[pick]
    norm = v_f / np.linalg.norm(v_f, axis=1, keepdims=True)
    sims = norm @ norm.T
    labels = tm_f["cluster"].to_numpy()
    iu = np.triu_indices(len(labels), k=1)
    pair_sims = sims[iu]
    same = ((labels[:, None] == labels[None, :]) &
            (labels[:, None] != -1))[iu]
    if not same.any() or same.all():
        return 0.85, 0.65                              # degenerate corpus: safe defaults
    return float(pair_sims[same].mean()), float(pair_sims[~same].mean())


@st.cache_data(show_spinner=False)
def seed_similar(seed_id: str, min_cluster_size: int, years: tuple, slug: str,
                 version: float, k: int = 5) -> pd.DataFrame | None:
    """Papers most similar to the seed BY MEANING, ranked over the WHOLE filtered corpus
    (not just whatever Network happens to have drawn - the seed may be outside a hub
    pick, the ranking should not be). Reuses rank_by_vector, the exact engine the Task
    module already runs on a query vector - no new similarity code. None if the seed's
    id is not in this corpus at all (e.g. you switched to a topic that never had it)."""
    tm_f, v_f = subtitled_state(min_cluster_size, years, slug, version)
    hit = tm_f.index[tm_f["id"] == seed_id]
    if hit.empty:
        return None
    q_vec = v_f[[hit[0]]]
    ranked = embed.rank_by_vector(q_vec, tm_f, v_f, k=k + 1)
    return ranked[ranked.index != hit[0]].head(k)


def _match_badge(score: float, m_in: float, m_out: float) -> str:
    if score >= m_in:
        return "very strong"
    if score >= (m_in + m_out) / 2:
        return "strong"
    if score >= m_out:
        return "related"
    return "distant"


@st.cache_data(show_spinner=False)
def review_lambda(min_cluster_size: int, years: tuple, slug: str, version: float):
    """MMR diversity knob chosen by THIS corpus (Phase 7.3): sweep lambda, keep the
    most diverse value that preserves >=99% of the achievable relevance."""
    tm_f, v_f = subtitled_state(min_cluster_size, years, slug, version)
    return review_mod.recommend_lambda(tm_f, v_f)


@st.cache_data(show_spinner=False)
def review_v2(min_cluster_size: int, years: tuple, slug: str, version: float,
              support_n: int, lam: float):
    """The extractive review draft (Phase 7.4), from the same filtered state as
    every other tab. Cached per density+lambda so the slider feels instant."""
    tm_f, v_f = subtitled_state(min_cluster_size, years, slug, version)
    return review_mod.draft_review_v2(tm_f, v_f, lam=lam,
                                      support_n=support_n, save=False)


# ---- Active topic: the session decides what the WHOLE app looks at (Phase 6.7) ----
if "topic" not in st.session_state:
    st.session_state["topic"] = config.DEFAULT_TOPIC
config.set_topic(st.session_state["topic"])
SLUG = (config.DEFAULT_SLUG if st.session_state["topic"] == config.DEFAULT_TOPIC
        else config.slugify(st.session_state["topic"]))

# When the corpus changes, every per-corpus control must re-fit to the NEW data
# (Batman: sliders kept the old topic's granularity, counts were from one corpus).
# Drop the sticky widget state so the granularity slider re-inits to the new
# recommendation and stale rankings/selections do not leak across corpora.
if st.session_state.pop("corpus_changed", False) or \
        st.session_state.get("active_slug") not in (None, SLUG):
    for k in ("mcs", "task_result", "detail_search", "detail_task", "detail_net",
              "detail_packed_guide", "detail_review", "detail_gaps",
              # Cluster ids are positions in ONE corpus's clustering: id 3 in this topic
              # is a different subtopic from id 3 in the last one, so an inherited pick
              # would silently select the wrong subtopics rather than fail visibly. The
              # seed is a paper id, which simply will not exist in the new corpus.
              "atlas_hubs", "hubsel_search", "hubsel_net", "hubsel_packed",
              "seed_id", "seed_title"):
        st.session_state.pop(k, None)
st.session_state["active_slug"] = SLUG

# First run on a fresh machine (portable/public build): there is NO corpus yet - offer
# the harvest flow instead of crashing on a missing parquet.
if not (config.DATA_PROCESSED / "topic_map.parquet").exists():
    st.html(_HERO)
    st.info("Fresh start - no corpus on this machine yet. Map your first topic "
            "(it takes a few minutes and needs internet).", icon=":material/rocket_launch:")
    render_topic_picker()
    st.stop()

DATA_VERSION = _data_version()
df, vectors, topic_map = load_data(SLUG, DATA_VERSION)

@st.cache_data
def recommended_granularity(slug: str, version: float):
    """DBCV sweep over the whole (relevant) map - recomputed per corpus, cached per data."""
    _, _, topic_map_full = load_data(slug, version)
    return cluster.recommend_min_cluster_size(topic_map_full[["x", "y"]].to_numpy())


# ---- Global filters: one set of controls governs every tab ----
with st.sidebar:
    st.header(":material/tune: Filters")
    rec_mcs, rec_table = recommended_granularity(SLUG, DATA_VERSION)
    if "mcs" not in st.session_state:
        st.session_state["mcs"] = rec_mcs
    mcs = st.slider(
        "Granularity (min papers per subtopic)",
        min_value=3, max_value=20, key="mcs",
        help="Lower = more, smaller subtopics. Re-clusters every view live. "
             "Feel free to wander - the recommended button brings you back.",
    )
    st.button(f"Use recommended ({rec_mcs})", icon=":material/auto_awesome:",
              on_click=lambda: st.session_state.update(mcs=rec_mcs))
    best_row = rec_table[rec_table["min_cluster_size"] == rec_mcs].iloc[0]
    st.caption(f"Recommended = {rec_mcs}: maximizes DBCV cluster validity "
               f"({best_row['validity']:.2f}) for THIS corpus - density-based quality, "
               "recomputed whenever the data changes, not a fixed default.")
    year_min, year_max = int(topic_map["year"].min()), int(topic_map["year"].max())
    # Key per corpus: a new topic gets a fresh slider spanning ITS own years,
    # instead of Streamlit carrying the previous corpus's selected range.
    years = st.slider("Year range", year_min, year_max, (year_min, year_max),
                      key=f"years_{SLUG}")
    hide_noise = st.checkbox("Hide noise", value=False,
                             help="Noise = papers HDBSCAN left outside every subtopic. "
                                  "Affects the visual views; Search always includes them.")
    size_by_cites = st.checkbox("Size = citations", value=True)

    tm, v_tm = subtitled_state(mcs, years, SLUG, DATA_VERSION)
    n_clusters = int(tm["cluster"].max() + 1) if len(tm) else 0
    n_noise = int((tm["cluster"] == -1).sum())
    st.caption(f"{n_clusters} subtopics · {n_noise} noise papers · {len(tm)} papers in view")
    # Phase R promise: surface the per-corpus gate (rule 9 - a knob COMPUTED for this
    # corpus, not a fixed constant). The gate verdict lives in the map's audit columns.
    if "relevance_gate" in tm.columns:
        n_harvest = harvest_size(SLUG, DATA_VERSION)
        if n_harvest:
            st.caption(f":material/filter_alt: Relevance gate: kept {len(tm)} of "
                       f"{n_harvest} harvested - junk hubs dropped whole, threshold "
                       "computed for THIS corpus (not a fixed default).")

    # Change the corpus WITHOUT leaving the current view (Batman: switching used to
    # bounce you to the landing; now it stays on the tab you are on). Only shown once
    # a mode is chosen - the landing already has its own picker.
    if st.session_state.get("mode"):
        with st.expander("Topic / corpus", icon=":material/travel_explore:"):
            st.caption("Current: " + config.TOPIC[:70]
                       + ("..." if len(config.TOPIC) > 70 else ""))
            render_topic_picker(key="sidebar")

    # Refresh: clears the cached maps so a re-run recomputes them (Batman ran the app
    # and didn't see recent changes - cached results are keyed by DATA version, not by
    # code). NOTE: for CODE updates you must also RESTART Froth (the .bat) - Streamlit
    # keeps the imported modules in memory (fileWatcherType is off for speed).
    st.divider()
    if st.button("Refresh app (clear cache)", icon=":material/refresh:",
                 help="Recompute the maps. After updating the CODE, also restart Froth."):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()

    # ---- Sources: connect the user's own accounts (Phase 5.6) ----
    with st.expander("Connect institutional account", icon=":material/account_circle:"):
        for name, s in sources.source_status().items():
            icon = ":material/check_circle:" if s["connected"] else ":material/radio_button_unchecked:"
            st.caption(f"{icon} **{name.replace('_', ' ')}** - {s['detail']}")
        st.caption("See papers beyond OpenAlex by connecting your own accounts. Keys are "
                   "stored ONLY on this machine (`.froth_keys`, gitignored); the public "
                   "web build keeps them in your browser session instead. "
                   "**Step-by-step guide with links: `docs/GET_YOUR_KEYS.md`** in the project.")
        src_email = st.text_input("Institutional email", value=config.INSTITUTIONAL_EMAIL,
                                  key="src_email")
        src_s2 = st.text_input("Semantic Scholar API key", type="password", key="src_s2",
                               help="Free key: semanticscholar.org/product/api - steadies "
                                    "the free tier's rate limits.")
        src_els = st.text_input("Elsevier/Scopus API key", type="password", key="src_els",
                                help="Free with a university subscription: dev.elsevier.com "
                                     "→ create API key. Unlocks Scopus results.")
        if st.button("Save connections", icon=":material/link:"):
            keys = config.load_keyfile()
            if src_email.strip():
                keys["INSTITUTIONAL_EMAIL"] = src_email.strip()
            if src_s2.strip():
                keys["SEMANTIC_SCHOLAR_API_KEY"] = src_s2.strip()
            if src_els.strip():
                keys["ELSEVIER_API_KEY"] = src_els.strip()
            (config.ROOT / ".froth_keys").write_text(
                "\n".join(f"{k}={v}" for k, v in keys.items()) + "\n", encoding="utf-8")
            st.success("Connected. New sources join the next corpus pull "
                       "(python -m froth.pull).")

st.html(_HERO)
n_relevant = int((df["relevance"] >= config.RELEVANCE_THRESHOLD).sum()) if "relevance" in df.columns else len(df)
st.caption(f"{len(df)} papers collected · {n_relevant} relevant to the topic · "
           "mapped by meaning, not keywords.")

# ---- Entry gate: choose HOW you come in. Same engine, same views - different door. ----
if "mode" not in st.session_state:
    st.session_state["mode"] = None

if st.session_state["mode"] is None:
    # ---- Start at zero: pick or harvest a topic (Phase 6.7) ----
    render_topic_picker()

    st.subheader("What brings you here?")
    col_a, col_b = st.columns(2)
    with col_a, st.container(border=True):
        st.markdown(":material/school: **Thesis / literature review**")
        st.caption("Explore the full landscape of a research topic: subtopics, "
                   "networks, measured gaps and a review scaffold.")
        if st.button("Start in thesis mode", key="pick_thesis", type="primary"):
            st.session_state["mode"] = "thesis"
            st.rerun()
    with col_b, st.container(border=True):
        st.markdown(":material/assignment: **Task / assignment**")
        st.caption("Attach the instructions (PDFs) or describe the task, and get the "
                   "papers that matter for it - plus every map and insight.")
        if st.button("Start in task mode", key="pick_task", type="primary"):
            st.session_state["mode"] = "task"
            st.rerun()
    st.stop()

mode_label = "Thesis mode" if st.session_state["mode"] == "thesis" else "Task mode"
chip, switch = st.columns([5, 1], vertical_alignment="center")
with chip:
    st.caption(f":material/door_open: **{mode_label}** - same engine and views in both; "
               "only the entrance changes. Global filters live in the left sidebar.")
with switch:
    if st.button("Switch", icon=":material/swap_horiz:", key="switch_mode"):
        st.session_state["mode"] = None
        st.rerun()

# ---- Task-mode input: shown ABOVE the shared views (the door, not a separate house) ----
if st.session_state["mode"] == "task":
    with st.container(border=True):
        task_text = st.text_area(
            "What are you asked to do?",
            placeholder="e.g. Write a 10-page report on how particle size distribution "
                        "affects flotation recovery of lithium micas...",
        )
        pdf_files = st.file_uploader("Instruction PDFs (optional)", type="pdf",
                                     accept_multiple_files=True)
        k_task = st.slider("Number of papers", 3, 25, 10, key="k_task")
        if st.button("Rank papers for this task", icon=":material/rocket_launch:",
                     type="primary"):
            contents = tuple(f.getvalue() for f in (pdf_files or []))
            if not task_text.strip() and not contents:
                st.warning("Describe the task or attach at least one PDF.")
            else:
                with st.spinner("Reading instructions and ranking the corpus..."):
                    ranked = task_ranking(task_text, contents, mcs, years, SLUG,
                                          DATA_VERSION, k_task)
                if ranked is None:
                    st.warning("Could not extract usable text (scanned PDFs have no text layer).")
                else:
                    st.session_state["task_result"] = ranked
        if "task_result" in st.session_state:
            ranked = st.session_state["task_result"]
            task_event = st.dataframe(
                ranked, hide_index=True,
                on_select="rerun", selection_mode="single-row", key="task_select",
                column_config={
                    "label": st.column_config.TextColumn("subtopic"),
                    "doi": st.column_config.LinkColumn("publisher", display_text="DOI"),
                    "oa_url": st.column_config.LinkColumn("free PDF", display_text="open PDF"),
                },
            )
            st.caption("score = how well the paper matches YOUR task. "
                       "Select a row to inspect and copy its citations. "
                       "All the views below still work - they show the whole landscape.")
            sel = task_event.selection.rows if task_event and task_event.selection else []
            if sel:
                row_id = ranked.iloc[sel[0]].name
                if row_id in tm.index:
                    paper_detail_panel(tm.loc[row_id], tm, key="task")

# Batman 2026-07-11: Gaps is no longer its own tab - its cards, semantic map and
# v1 draft now live INSIDE Review (hidden as a tab, nothing deleted).
# 2026-07-17: the ATLAS leads - the only view that draws the FULL uncapped corpus
# (WebGL points, one own hue per subtopic; the legacy views cap at 400).
# LAZY (ported from v1, 98ae778): by default Streamlit computes EVERY tab body on EVERY
# interaction, so one click paid for six views - here over 8k-paper corpora, which is why
# the app took minutes to start. on_change="rerun" plus the `if tab.open:` guards below mean
# only the tab you are looking at runs. The subtopic pick still reaches the other views: it
# lives in st.session_state["atlas_hubs"], a plain key that survives a tab not being drawn.
tab_atlas, tab_search, tab_net, tab_packed, tab_review, tab_space, tab_export = st.tabs([
    ":material/public: Atlas",
    ":material/search: Search",
    ":material/hub: Network",
    ":material/bubble_chart: Packed bubbles",
    ":material/edit_note: Review",
    ":material/bookmarks: My space",
    ":material/ios_share: Export",
], key="main_tabs", on_change="rerun")


@st.cache_data(show_spinner=False)
def logbook_topic_map(slug: str) -> pd.DataFrame:
    """Read ANY topic's map straight off disk, without switching the active corpus.

    config.set_topic() would re-point the whole engine mid-render, so the other tabs
    would suddenly be looking at a different corpus. The logbook only needs titles,
    citations and cluster labels, so it reads the parquet directly instead."""
    path = config.paths_for(slug)["processed"] / "topic_map.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def logbook_topics(active_slug: str, active_title: str) -> list[tuple[str, str]]:
    """(slug, title) for the picker: the ACTIVE topic first, every other harvested one
    after it (Batman: "prioriza el activo... en teoria no deberia necesitar leer de otro
    topic"). The option exists, it just does not get in the way."""
    out = [(active_slug, active_title)]
    if active_slug != "default" and (config.ROOT / "2_Datos" / "processed" /
                                     "topic_map.parquet").exists():
        out.append(("default", config.DEFAULT_TOPIC))    # lives in the legacy folders
    if config.TOPICS_REGISTRY.exists():
        for line in config.TOPICS_REGISTRY.read_text(encoding="utf-8").splitlines():
            if "," not in line:
                continue
            s, t = line.split(",", 1)
            if s != active_slug and (config.ROOT / "2_Datos" / "topics" / s /
                                     "processed" / "topic_map.parquet").exists():
                out.append((s, t))
    return out


def _stage_buttons(scope: str, current: str | None = None) -> str | None:
    """The five stages as coloured buttons. Returns the one pressed, else None."""
    st.markdown("""<style>
      div[class*="st-key-stagebtn_"] button { border-width: 2px !important; }
    </style>""", unsafe_allow_html=True)
    cols = st.columns(len(my_space.STAGES))
    pressed = None
    for col, stage in zip(cols, my_space.STAGES):
        colour = my_space.STAGE_COLORS[stage]
        mark = "● " if stage == current else ""
        with col:
            with st.container(key=f"stagebtn_{scope}_{stage.replace(' ', '_')}"):
                st.markdown(
                    f"<style>div[class*='st-key-stagebtn_{scope}_"
                    f"{stage.replace(' ', '_')}'] button {{ border-color: {colour}; "
                    f"color: {colour}; }}</style>", unsafe_allow_html=True)
                if st.button(f"{mark}{stage}", key=f"sb_{scope}_{stage}",
                             use_container_width=True):
                    pressed = stage
    return pressed


def _stage_filter_bar(entries: list[dict]) -> str | None:
    """'All' + the five stages as a READ-ONLY filter, with a live count on each.

    Deliberately NOT built from _stage_buttons: that one is an ACTION - pressing it
    writes a stage to whatever is selected. Reusing it here would mean a click meant to
    filter the view could instead overwrite the currently-selected paper's stage
    (Batman: "que no se te cruce con la edicion"). This component only ever reads
    st.session_state["ms_filter_stage"] and never calls my_space.update/add - filtering
    the sheet cannot, by construction, change anything on disk. Keys are prefixed
    'filterbtn_', a separate namespace from 'sb_add_' / 'sb_edit_'.
    """
    current = st.session_state.get("ms_filter_stage")
    st.caption("Filter your sheet:")
    labels = [("All", None)] + [(s, s) for s in my_space.STAGES]
    cols = st.columns(len(labels))
    for col, (label, stage) in zip(cols, labels):
        colour = my_space.STAGE_COLORS.get(stage, "#a1a1aa")
        n = len(entries) if stage is None else sum(1 for e in entries if e["stage"] == stage)
        mark = "● " if stage == current else ""
        with col:
            with st.container(key=f"filterbtn_{label.replace(' ', '_')}"):
                st.markdown(
                    f"<style>div[class*='st-key-filterbtn_{label.replace(' ', '_')}'] "
                    f"button {{ border-color: {colour}; color: {colour}; "
                    "border-width: 2px; }</style>", unsafe_allow_html=True)
                if st.button(f"{mark}{label} ({n})", key=f"fb_{label}",
                             use_container_width=True):
                    st.session_state["ms_filter_stage"] = stage
                    st.rerun(scope="fragment")
    return current


def _scope_bar(n_mine: int, n_all: int) -> str:
    """'This topic' / 'All topics' as a READ-ONLY lens over the sheet.

    The logbook is ONE file spanning every topic (each record carries its topic_slug), so
    without this the sheet showed the previous topic's papers after a switch and counted
    them in the progress bar (Batman: "cambie el topic y todavia me aparecen los que
    estaban en el topico anterior"). Filtering, not deleting: nothing leaves the disk.

    Same discipline as _stage_filter_bar - it only ever writes st.session_state["ms_scope"]
    and never calls my_space.add/update/remove. Keys live in their own 'scopebtn_' / 'sc_'
    namespace, separate from 'filterbtn_'/'fb_' and 'stagebtn_'/'sb_': mixing those
    namespaces is what once let a click meant to filter overwrite a paper's stage.
    """
    current = st.session_state.get("ms_scope", "topic")
    st.caption("Show records from:")
    cols = st.columns(2)
    for col, (key, label, n) in zip(cols, [("topic", "This topic", n_mine),
                                           ("all", "All topics", n_all)]):
        mark = "● " if key == current else ""
        with col:
            with st.container(key=f"scopebtn_{key}"):
                st.markdown(
                    f"<style>div[class*='st-key-scopebtn_{key}'] button "
                    "{ border-color: #6366f1; color: #6366f1; border-width: 2px; }"
                    "</style>", unsafe_allow_html=True)
                if st.button(f"{mark}{label} ({n})", key=f"sc_{key}",
                             use_container_width=True):
                    st.session_state["ms_scope"] = key
                    st.rerun(scope="fragment")
    return current


def _clear_topic_controls(active_slug: str, active_title: str, n_mine: int) -> None:
    """'Empty this topic', behind a two-step confirmation.

    Kept BELOW the sheet and behind a divider so it never sits next to the per-row
    'Remove from logbook' - the two delete very different amounts and a misclick between
    them is not recoverable. Only this topic's records are touched; every other topic
    survives (my_space.remove_topic filters, it does not truncate the file).
    """
    if not n_mine:
        return
    st.divider()
    pending = st.session_state.get("ms_confirm_clear")
    # The token carries the slug: switching topic mid-confirmation makes it stop matching,
    # so a confirmation raised for one corpus can never fire against another.
    if pending != active_slug:
        if st.button("Empty this topic", icon=":material/delete_sweep:",
                     key="ms_clear_ask",
                     help="Delete every record filed under the current topic. "
                          "Records from other topics are untouched."):
            st.session_state["ms_confirm_clear"] = active_slug
            st.rerun(scope="fragment")
        return
    st.warning(f":material/warning: Delete **{n_mine}** record"
               f"{'s' if n_mine != 1 else ''} filed under *{active_title[:60]}*? "
               "Records from your other topics stay exactly as they are. "
               "This cannot be undone.")
    c_yes, c_no = st.columns(2)
    if c_yes.button(f"Yes, delete {n_mine}", key="ms_clear_yes",
                    use_container_width=True):
        n = my_space.remove_topic(active_slug)
        st.session_state.pop("ms_confirm_clear", None)
        st.toast(f"Removed {n} record{'s' if n != 1 else ''} from this topic",
                 icon=":material/delete_sweep:")
        st.rerun(scope="fragment")
    if c_no.button("Cancel", key="ms_clear_no", type="primary",
                   use_container_width=True):
        st.session_state.pop("ms_confirm_clear", None)
        st.rerun(scope="fragment")


@st.fragment
def my_space_logbook(active_slug: str, active_title: str,
                     active_map: pd.DataFrame) -> None:
    """The researcher's logbook: a sheet of records you build yourself.

    Rebuilt on Batman's spec (2026-07-20) after the previous design kept breaking: papers
    are no longer pushed in from the map views' Know-more panel, they are filed HERE by
    picking topic -> island -> paper. The old version also painted a selectbox, a text
    field and a button PER RECORD, so a handful of rows meant a swarm of widgets each
    firing its own re-run. This one has no per-row widgets at all: one table, and the
    stage buttons act on whichever row is selected.

    A FRAGMENT so its controls never re-run the rest of the app.
    """
    st.markdown("#### File a paper")
    topics = logbook_topics(active_slug, active_title)
    labels = [f"{t[:70]} (current)" if s == active_slug else t[:70] for s, t in topics]
    pick = st.selectbox("Topic", range(len(topics)), format_func=lambda i: labels[i],
                        key="ms_topic")
    slug, title = topics[pick]
    tmap = active_map if slug == active_slug else logbook_topic_map(slug)
    if tmap.empty:
        st.warning("That topic has no map on disk yet.")
        return

    real = tmap[tmap["cluster"] != -1]
    sizes = real["cluster"].value_counts()
    islands = sizes.index.tolist()
    hues = palette.territory_hues(len(islands))
    colour_of = {c: hues[i] for i, c in enumerate(islands)}
    c_isl, c_paper = st.columns([1, 2])
    with c_isl:
        # Keyed by SLUG (like the paper picker below): island ids are cluster numbers,
        # and topics have anywhere from 2 to 24 islands. An unscoped key remembered
        # "island 6" across a topic switch and crashed the moment the new topic had
        # fewer than 7 - each topic now gets its own widget, always a valid index.
        island = st.selectbox(
            "Island (subtopic)", islands, key=f"ms_island_{slug}",
            format_func=lambda c: f"{str(real[real['cluster'] == c]['label'].iloc[0])[:34]}"
                                  f" ({int(sizes[c])})")
    part = real[real["cluster"] == island].sort_values("citations", ascending=False)
    must_n = visualize._must_count(part["citations"].tolist())
    island_name = str(part["label"].iloc[0])
    with c_paper:
        # Every paper of the island, most cited first, with the h-index core starred -
        # the SAME cut the reading guide draws as its dashed must-read line.
        opts = list(range(len(part)))
        paper_i = st.selectbox(
            "Paper", opts, key=f"ms_paper_{slug}_{island}",
            format_func=lambda i: ("★ " if i < must_n else "")
                                  + f"{int(part.iloc[i]['citations'])} cit - "
                                  + str(part.iloc[i]["title"])[:70])
    row = part.iloc[paper_i]
    st.caption(f"<span style='color:{colour_of[island]}'>&#9679;</span> {island_name[:60]}"
               f" · {int(row['year'])} · {int(row['citations'])} citations"
               + (f" · {row['source']}" if str(row.get("source", "")) not in ("", "nan")
                  else "")
               + ("  ·  **must-read of this island** (top "
                  f"{must_n} by h-index)" if paper_i < must_n else ""),
               unsafe_allow_html=True)
    links = []
    if str(row.get("doi", "")) not in ("", "nan"):
        links.append(f"[DOI]({row['doi']})")
    if str(row.get("oa_url", "")) not in ("", "nan"):
        links.append(f"[open PDF]({row['oa_url']})")
    if links:
        st.caption(" · ".join(links))

    st.caption("Pick the stage to file it under:")
    chosen = _stage_buttons("add")
    if chosen:
        if my_space.add(row, slug, topic_title=title, island=island_name,
                        must_read=paper_i < must_n, stage=chosen):
            st.toast(f"Filed as '{chosen}'", icon=":material/bookmark_added:")
        else:
            st.toast("That paper is already in your logbook", icon=":material/bookmark:")
        st.rerun(scope="fragment")

    st.divider()
    entries = my_space.load()
    if not entries:
        st.info(":material/bookmark_add: Your logbook is empty. File a paper above and it "
                "becomes the first row of your sheet.")
        return

    # Active topic first, everything else after it, newest first inside each group.
    entries.sort(key=lambda e: (e["topic_slug"] != active_slug, e["added_at"]),
                 reverse=False)
    mine = [e for e in entries if e["topic_slug"] == active_slug]
    scope = _scope_bar(len(mine), len(entries))
    scoped = mine if scope == "topic" else entries

    # An empty CURRENT topic while other topics hold records is the moment this view used
    # to look like data loss. Say what is actually going on and offer the way to see it.
    if not scoped:
        st.info(f":material/bookmark_add: Nothing filed under **this topic** yet - but your "
                f"logbook still holds {len(entries)} record"
                f"{'s' if len(entries) != 1 else ''} from other topics. Nothing was deleted.")
        if st.button("Show all topics", icon=":material/inventory_2:", key="ms_show_all"):
            st.session_state["ms_scope"] = "all"
            st.rerun(scope="fragment")
        return

    done = sum(1 for e in scoped if e["stage"] in my_space.DONE_STAGES)
    scope_word = "this topic" if scope == "topic" else "all topics"
    st.markdown(f"#### Your logbook · {done} of {len(scoped)} processed")
    st.caption(f"Counting {scope_word}.")   # the count follows the lens, so the number
    st.progress(done / len(scoped))          # can never describe rows you cannot see

    filter_stage = _stage_filter_bar(scoped)
    view = scoped if filter_stage is None else [e for e in scoped
                                                 if e["stage"] == filter_stage]
    if not view:
        st.caption(f"Nothing filed as *{filter_stage}* yet.")
        return
    sheet = pd.DataFrame([{
        "stage": e["stage"],
        "title": e["title"],
        "year": e["year"],
        "citations": e["citations"],
        "must-read": "★" if e["must_read"] else "",
        "island": e["island"][:40],
        # Only worth a column when the sheet actually mixes topics; dropping it in the
        # single-topic view gives the width back to the title, which was being cut off.
        **({"topic": (e["topic_title"] or e["topic_slug"])[:40]} if scope == "all" else {}),
        "note": e["note"],
        "filed": e["added_at"],
    } for e in view])
    styled = sheet.style.apply(
        lambda col: [f"color: {my_space.STAGE_COLORS.get(v, '')}; font-weight: 600"
                     for v in col], subset=["stage"])
    # Keyed by the active filter: switching filters must start with a CLEAN selection,
    # not carry over a row index from a differently-shaped table (the same class of
    # cross-contamination the filter bar exists to avoid).
    event = st.dataframe(styled, hide_index=True, on_select="rerun",
                         selection_mode="single-row",
                         key=f"ms_sheet_{scope}_{filter_stage or 'all'}")
    rows = event.selection.rows if event and event.selection else []
    if not rows:
        st.caption("Select a row to change its stage, add a note or remove it.")
        _clear_topic_controls(active_slug, active_title, len(mine))
        return
    entry = view[rows[0]]
    st.caption(f"Selected: **{entry['title'][:80]}** - currently *{entry['stage']}*")
    moved = _stage_buttons("edit", current=entry["stage"])
    if moved and moved != entry["stage"]:
        my_space.update(entry["id"], stage=moved)
        st.rerun(scope="fragment")
    note = st.text_input("Note (summary, interpretation, why you discarded it...)",
                         value=entry["note"], key=f"ms_note_{entry['id']}")
    if note != entry["note"]:
        my_space.update(entry["id"], note=note)
        st.rerun(scope="fragment")
    if st.button("Remove from logbook", icon=":material/delete:", key="ms_remove"):
        my_space.remove(entry["id"])
        st.rerun(scope="fragment")
    _clear_topic_controls(active_slug, active_title, len(mine))


if tab_space.open:      # lazy: skip the body entirely when not looking at it
    with tab_space:
        # ANCHOR - do not delete this caption to "clean up" the tab.
        # Streamlit requires a container to receive at least one write during the INITIAL
        # FULL RUN before a fragment can redraw into it on later fragment reruns. My space
        # is the only tab whose body comes from a fragment: the others all write their own
        # caption or banner directly. Without a write of its own this tab has no fixed
        # position to repaint into, and its pickers paint into other tabs' containers
        # instead (Batman reported that three separate times on the v1 edition).
        st.caption(":material/bookmarks: Your reading logbook: file papers as you work "
                   "through them and track which ones you have read, summarized, "
                   "interpreted or discarded. It is saved on this machine and persists "
                   "between sessions.")
        my_space_logbook(SLUG, config.TOPIC, tm)

if tab_atlas.open:      # lazy: skip the body entirely when not looking at it
    with tab_atlas:
        st.caption(f"The Atlas: all {len(tm)} papers in view, drawn as WebGL points - "
                   "zoom with the wheel, drag to pan, hover for the paper, click to open "
                   "it in Know-more below. The legend lists the subtopics in view; tick "
                   "some and send them to the Network for the close-up.")
        atlas_val = _bridge(html=atlas_view(mcs, years, SLUG, DATA_VERSION),
                            height=740, key=f"atlas_bridge_{SLUG}", default=None,
                            sync_hubs=list(st.session_state.get("atlas_hubs", ())))
        if isinstance(atlas_val, dict) and atlas_val.get("hubs"):
            sel = tuple(sorted(int(h) for h in atlas_val["hubs"]))
            if st.session_state.get("atlas_hubs") != sel:
                st.session_state["atlas_hubs"] = sel
                st.toast(f"{len(sel)} subtopic(s) sent to the Network tab",
                         icon=":material/hub:")
        elif atlas_val is not None and not isinstance(atlas_val, dict) \
                and int(atlas_val) in tm.index:
            paper_detail_panel(tm.loc[int(atlas_val)], tm, key="atlas")

if tab_search.open:      # lazy: skip the body entirely when not looking at it
    with tab_search:
        # The Atlas pick governs Search too (Batman 2026-07-17: every view linked; a 65-paper
        # hub must be fully listable, not capped at 20).
        _hub_menu(tm, "search")
        search_hubs = tuple(st.session_state.get("atlas_hubs", ()))
        if search_hubs:
            _sk = tm["cluster"].isin(search_hubs).to_numpy()
            tm_s, v_s = tm[_sk].reset_index(drop=True), v_tm[_sk]
            st.success(f":material/hub: Searching **within your pick**: {len(tm_s)} papers "
                       f"in {len(search_hubs)} subtopic(s).")
        else:
            tm_s, v_s = tm, v_tm
        browse_all = search_hubs and st.toggle(
            "Browse the whole pick (no query - every paper, most-cited first)",
            value=False)
        query = st.text_input(
            "Describe what you're looking for:",
            value="effect of particle size on lithium mica flotation recovery",
            disabled=bool(browse_all),
        )
        k_max = int(min(200, max(2, len(tm_s))))
        k = st.slider("Number of results", min_value=1, max_value=k_max,
                      value=min(5, k_max))
        if browse_all:
            # One SECTION per picked hub (Batman 2026-07-18: "cada hub por separado, no
            # todo junto") - its color chip, its KeyBERT name, its own most-cited table.
            hub_hues = palette.territory_hues(len(search_hubs))
            for hi, hub in enumerate(search_hubs):
                part = tm_s[tm_s["cluster"] == hub].sort_values("citations",
                                                                ascending=False)
                if part.empty:
                    continue
                st.markdown(f"#### <span style='color:{hub_hues[hi]}'>&#9679;</span> "
                            f"{str(part['label'].iloc[0])} · {len(part)} papers",
                            unsafe_allow_html=True)
                bcols = [c for c in ("title", "year", "citations", "doi", "oa_url")
                         if c in part.columns]
                ev = st.dataframe(
                    part[bcols].reset_index(drop=True), hide_index=True,
                    on_select="rerun", selection_mode="single-row",
                    key=f"browse_{hub}",
                    column_config={
                        "doi": st.column_config.LinkColumn("publisher",
                                                           display_text="DOI"),
                        "oa_url": st.column_config.LinkColumn("free PDF",
                                                              display_text="open PDF"),
                    })
                _rows = ev.selection.rows if ev and ev.selection else []
                if _rows:
                    _m = tm[tm["title"] == part.iloc[_rows[0]]["title"]]
                    if len(_m):
                        paper_detail_panel(_m.iloc[0], tm, key=f"browse_{hub}")
        if (not browse_all) and query.strip():
            with st.spinner("Searching..."):
                results = embed.most_similar(query, tm_s, v_s, k=k)
            m_in, m_out = similarity_anchors(mcs, years, SLUG, DATA_VERSION)
            results.insert(1, "match",
                           [_match_badge(s, m_in, m_out) for s in results["score"]])
            results["note"] = ["new - too recent to be cited"
                               if (c == 0 and y >= 2024) else ""
                               for c, y in zip(results["citations"], results["year"])]
            n_pdf = int((results.get("oa_url", pd.Series(dtype=str)) != "").sum())
            table_event = st.dataframe(
                results,
                hide_index=True,
                on_select="rerun", selection_mode="single-row", key="search_select",
                column_config={
                    "label": st.column_config.TextColumn("subtopic"),
                    "doi": st.column_config.LinkColumn("publisher", display_text="DOI"),
                    "oa_url": st.column_config.LinkColumn("free PDF", display_text="open PDF"),
                },
            )
            st.caption(f"Searching the {len(tm_s)} papers in scope "
                       f"({'your pick' if search_hubs else 'the full view'}). "
                       f"{n_pdf}/{len(results)} results have a free open-access PDF. "
                       "Select a row to inspect the paper.")
            with st.expander(":material/help: What do these numbers mean?"):
                st.markdown(
                    "**score** is cosine similarity between meanings, NOT a percentage: "
                    "in this embedding space almost everything lands between 0.4 and 0.95, "
                    "so **0.7+ already means strongly related** - do not expect a 100.\n\n"
                    "**match** grades the score against thresholds MEASURED on this "
                    f"corpus: papers within one subtopic average {m_in:.2f} similarity, "
                    f"papers across subtopics average {m_out:.2f}. A *very strong* match "
                    "is as close to your query as same-subtopic papers are to each "
                    "other.\n\n"
                    "**0 citations** usually marks a 2024+ paper: citations measure "
                    "*accumulated* attention, and fresh research has not had time to be "
                    "cited yet. It is the frontier of the field, not low quality - the "
                    "*note* column flags these."
                )
            sel_rows = table_event.selection.rows if table_event and table_event.selection else []
            if sel_rows:
                match = tm[tm["title"] == results.iloc[sel_rows[0]]["title"]]
                if len(match):
                    paper_detail_panel(match.iloc[0], tm, key="search")


if tab_net.open:      # lazy: skip the body entirely when not looking at it
    with tab_net:
        st.caption("Force-directed network: click a paper to spotlight it and its neighbors; "
                   "double-click a paper to zoom into it; double-click empty space to reset. "
                   f"Edge = strong content similarity (cosine ≥ {config.GRAPH_SIM_THRESHOLD}).")
        # Map the clicked node id back to the SAME frame the network was built from:
        # replicate network_view's exact pipeline (noise filter -> hub pick or scale cap).
        _hub_menu(tm, "net")
        atlas_hubs = tuple(st.session_state.get("atlas_hubs", ()))
        if hide_noise:
            _k = (tm["cluster"] != -1).to_numpy()
            tm_net, v_net = tm[_k].reset_index(drop=True), v_tm[_k]
        else:
            tm_net, v_net = tm, v_tm
        if atlas_hubs:
            tm_net, v_net, hub_trimmed = _hub_subset(tm_net, v_net, atlas_hubs)
            net_capped = True
            c1, c2 = st.columns([5, 1])
            c1.success(f":material/hub: Showing **your Atlas pick**: {len(atlas_hubs)} "
                       f"subtopic(s), {len(tm_net)} papers"
                       + (" (most-cited slice - the pick was physics-big)" if hub_trimmed
                          else "") + ".")
            if c2.button("Clear pick", use_container_width=True):
                del st.session_state["atlas_hubs"]
                st.rerun()
        else:
            tm_net, v_net, net_capped = _cap_for_heavy_views(tm_net, v_net)
            if net_capped:
                st.info(f":material/filter_alt: Big corpus: this tab shows its **largest "
                        f"subtopics whole** ({len(tm_net)} papers) with an island legend on "
                        "each hub - or pick exactly which subtopics to draw from the Atlas "
                        "legend. Papers with no strong link are hidden here (they are in "
                        "Search).")
        # SEED (Batman 2026-07-20): resolve the seed's row position in THIS pick, if it is
        # in it at all - network_view checks it against its own graph too, so passing a
        # position that later turns out weak-linked/dropped degrades to "no marker", never
        # an error.
        seed_id = st.session_state.get("seed_id")
        seed_node_id = None
        if seed_id:
            hit = tm_net.index[tm_net["id"] == seed_id]
            seed_node_id = int(hit[0]) if not hit.empty else None
            sc1, sc2 = st.columns([5, 1])
            sc1.markdown(f":material/target: Seed: **{st.session_state.get('seed_title', '')[:70]}**"
                        + ("" if seed_node_id is not None else
                           " *(not in the current pick - shown in Search/My space instead)*"))
            if sc2.button("Clear seed", use_container_width=True):
                st.session_state.pop("seed_id", None)
                st.session_state.pop("seed_title", None)
                st.rerun()

        # The Know-more panel is rendered ABOVE the map, not under it. Clicking a paper
        # always worked - the panel was simply born below a 780px canvas, i.e. 559px past
        # the bottom of the window (measured on v1), so nobody ever saw it. Reserve the
        # slot first, fill it after the component reports which paper was picked.
        panel_slot = st.container()
        picked_node = _bridge(html=network_view(mcs, years, hide_noise, SLUG, DATA_VERSION,
                                                hubs=atlas_hubs, seed_node=seed_node_id),
                              height=780, key=f"net_bridge_{SLUG}", default=None)
        if picked_node is not None and int(picked_node) in tm_net.index:
            with panel_slot:
                # tm_net is the 400-paper slice the physics can handle; the citation rank
                # shown in the card is deliberately "within what you are looking at", but
                # the must-read flag written to the logbook must come from the whole map.
                paper_detail_panel(tm_net.loc[int(picked_node)], tm_net, key="net",
                                   full_map=tm)

        if seed_id:
            # Ranked over the WHOLE corpus (seed_similar uses subtitled_state directly),
            # independent of whatever subset happens to be drawn - a paper can be a strong
            # cosine match to the seed even below the graph's edge threshold, or in a
            # subtopic you have not picked into the network.
            similar = seed_similar(seed_id, mcs, years, SLUG, DATA_VERSION)
            st.markdown("##### :material/target: Most similar to the seed")
            if similar is None or similar.empty:
                st.caption("No other papers in this corpus to compare against yet.")
            else:
                seed_event = st.dataframe(
                    similar, hide_index=True, on_select="rerun",
                    selection_mode="single-row", key=f"seed_similar_{SLUG}",
                    column_config={
                        "label": st.column_config.TextColumn("subtopic"),
                        "doi": st.column_config.LinkColumn("publisher", display_text="DOI"),
                        "oa_url": st.column_config.LinkColumn("free PDF", display_text="open PDF"),
                    })
                seed_rows = seed_event.selection.rows if seed_event and seed_event.selection else []
                if seed_rows:
                    seed_row_id = similar.iloc[seed_rows[0]].name
                    if seed_row_id in tm.index:
                        paper_detail_panel(tm.loc[seed_row_id], tm, key="seed_similar")

        with st.expander(":material/help: How to read this network"):
            st.markdown(
                "- **Springs are calibrated**: on-screen distance ≈ semantic distance. "
                "Two connected papers sit close when their content is nearly identical, "
                "farther apart when they barely pass the similarity threshold.\n"
                "- **Big nodes with many edges are hubs** - the papers a whole subtopic "
                "leans on; classic review-starters.\n"
                "- **A dashed ring in another cluster's color marks a boundary paper**: "
                "most of its semantic neighbors live in the neighboring subtopic. These "
                "are often the most interdisciplinary papers in the corpus.\n"
                "- **A dashed GRAY ring marks a loner**: no paper reaches the similarity "
                "threshold with it, so it floats free. Usually an off-topic intruder that "
                "slipped in through a term collision (e.g. \"attrition\" also means staff "
                "turnover). We flag it rather than fake a connection.\n"
                "- **Click** a node to spotlight its neighborhood; everything unrelated "
                "fades. Double-click empty space to reset the view.")

if tab_packed.open:      # lazy: skip the body entirely when not looking at it
    with tab_packed:
        # Two ways to read the same papers. The map answers "what is out there"; the list
        # answers "what do I read on Monday". Batman's words for why the list had to exist:
        # "no leer los 40 de isla A que pasaron el threshold y despues 10 de isla B... que
        # esten organizados y rankeados y se me haga mas facil ir leyendo el espectro".
        spectrum = st.toggle(
            "Read by spectrum (a single ranked list across all subtopics)",
            key="packed_spectrum",
            help="Instead of one column per subtopic, one numbered list that takes the best "
                 "of each subtopic in turn. Stop wherever you like and you have still seen "
                 "the whole map.")
        if spectrum:
            budget = st.slider(
                "How many papers", 30, 300, review_mod.READING_BUDGET, step=5,
                key="packed_budget",
                help="115 is the MEDIAN number of references an EMerald master's thesis "
                     "actually cites, counted over 22 of them. Not a round number.")
            order = review_mod.spectrum_reading_list(tm, budget=budget)
            st.caption(f"**{len(order)} papers across {order['island'].nunique()} subtopics.** "
                       "Read top to bottom: each row comes from a different subtopic than "
                       "the last, so the first dozen already cross the whole map. Subtopics "
                       "that cite nothing else here are left out of this list.")
            show = order[["read_order", "island", "title", "year", "citations", "oa_url"]]
            st.dataframe(
                show, hide_index=True, use_container_width=True, height=560,
                column_config={
                    "read_order": st.column_config.NumberColumn("#", width="small"),
                    "island": st.column_config.TextColumn("Subtopic", width="medium"),
                    "title": st.column_config.TextColumn("Title", width="large"),
                    "year": st.column_config.NumberColumn("Year", format="%d", width="small"),
                    "citations": st.column_config.NumberColumn("Cit.", width="small"),
                    "oa_url": st.column_config.LinkColumn("Free PDF", display_text="open"),
                })
            st.download_button(
                "Download this reading list (CSV)", show.to_csv(index=False),
                file_name="froth_reading_list.csv", mime="text/csv",
                icon=":material/download:")
            # st.stop() rather than wrapping the map below in an else, which would mean
            # re-indenting eighty lines for no gain. It is safe here because every tab body
            # sits behind its own `if tab_x.open` guard and only one tab is open at a time,
            # so nothing downstream was going to run anyway. If a footer is ever added
            # after the tabs, this becomes a bug: put it above the tabs, or invert this.
            st.stop()

        st.caption("Reading guide: one column per subtopic, most-cited papers first "
                   "(read left→right, top→down). Above the dashed line = the must-reads - "
                   "an h-index cut computed for EACH subtopic of THIS corpus, not a fixed "
                   "top-N. Bubbles float but always return home. Hover for details, or "
                   "click a bubble to inspect it right here.")
        # Same pick, everywhere (Batman 2026-07-17): the guide honors the Atlas/menu hub
        # selection - a few chosen subtopics render whole and READABLE. All subsets keep
        # original indices (bubble clicks post the original tm index for the detail panel).
        _hub_menu(tm, "packed")
        guide_hubs = tuple(st.session_state.get("atlas_hubs", ()))
        tm_guide = tm
        if guide_hubs:
            tm_guide = tm[tm["cluster"].isin(guide_hubs)]
            if len(tm_guide) > 3 * config.HEAVY_VIEW_MAX_PAPERS:
                tm_guide = tm_guide.loc[
                    tm_guide["citations"].nlargest(3 * config.HEAVY_VIEW_MAX_PAPERS).index]
            st.success(f":material/hub: Reading guide for **your pick**: {len(guide_hubs)} "
                       f"subtopic(s), {len(tm_guide)} papers.")
        elif len(tm) > config.HEAVY_VIEW_MAX_PAPERS:
            tm_guide = tm.loc[tm["citations"].nlargest(config.HEAVY_VIEW_MAX_PAPERS).index]
            st.info(f":material/filter_alt: Reading guide drawn on the "
                    f"**{len(tm_guide)} most-cited** of {len(tm)} papers - pick specific "
                    "subtopics above (or in the Atlas) to read them whole. The must-read "
                    "cut only depends on the top of the citation curve.")
        guide_html, guide_h = visualize.reading_guide_html(tm_guide)
        # Same reserved slot as the Network tab: this frame grows with the number of
        # subtopics, so a panel underneath it can fall off the screen just as easily.
        guide_panel_slot = st.container()
        picked_bubble = _bridge(html=guide_html, height=guide_h + 12,
                                key=f"guide_bridge_{SLUG}", default=None)
        if picked_bubble is not None and int(picked_bubble) in tm.index:
            with guide_panel_slot:
                paper_detail_panel(tm.loc[int(picked_bubble)], tm, key="packed_guide")
        with st.expander(":material/help: What is the h-index cut?"):
            st.markdown(
                "The must-read line is NOT a fixed top-N. Each subtopic gets its own "
                "**h-index**: the largest h such that h papers have at least h citations "
                "each - the point where the evidence stops carrying itself. A mature "
                "subtopic sets a high bar on its own (a 110-paper geology cluster may "
                "demand 35 must-reads); a young niche settles for 3. When citations are "
                "too flat for the h-index to discriminate, a head/tail cut on the mean "
                "takes over. Zero parameters to tune - the cluster sets its own bar.")


if tab_review.open:      # lazy: skip the body entirely when not looking at it
    with tab_review:
        # Production shows ONLY the deterministic v1 scaffold (Batman: v2 draft + Ollama
        # polish are still in development). The v2/polish UI lives in
        # docs/archive/review_v2_dev.py; its engine (review.py, polish.py) stays in the
        # repo. Dropping the v2 lambda-sweep + per-sentence embedding also removes the
        # heavy work that made this tab lag ("only updates when you hit Search").
        st.caption("Literature review scaffold - a structured draft measured from YOUR "
                   "corpus: one section per subtopic (what it studies, milestone papers, "
                   "recent work, and its gap), every reference traceable to a real paper. "
                   "Deterministic template, no LLM, nothing hallucinated - a scaffold to "
                   "write on, not finished prose.")
        _, draft_text = gaps_and_draft(mcs, years, SLUG, DATA_VERSION)
        st.download_button("Download the review scaffold (.md)", data=draft_text,
                           file_name="froth_review_scaffold.md", mime="text/markdown",
                           icon=":material/download:")
        with st.container(height=560, border=True):
            st.markdown(draft_text)


if tab_export.open:      # lazy: skip the body entirely when not looking at it
    with tab_export:
        # PHASE 4.1 - the map leaves the app. Everything here is plain markdown: it opens in
        # Obsidian as a linked graph and in any text editor as ordinary files, so it is worth
        # having whether or not you use Obsidian.
        st.caption("Turn this map into a folder of linked notes. One note per subtopic, one "
                   "per must-read paper, plus an index. Papers that do not get their own "
                   "note are listed inside their subtopic, so nothing is dropped, only "
                   "ranked. Your My space reading stages travel with them.")

        tm_x, v_x = subtitled_state(mcs, years, SLUG, DATA_VERSION)
        n_sub = int(tm_x.loc[tm_x["cluster"] != -1, "cluster"].nunique())
        st.markdown(f"**Ready to export:** {len(tm_x)} papers in {n_sub} subtopics, at the "
                    f"granularity and year range you have set. Changing either changes what "
                    f"gets exported.")

        if st.button("Build the vault", icon=":material/folder_zip:", type="primary"):
            with st.spinner("Writing notes..."):
                # The subtitles are already computed and cached in subtitled_state; handing
                # them over skips re-embedding every candidate keyphrase (50s on this corpus).
                subs = {int(c): (str(l), str(s)) for c, l, s in
                        zip(tm_x["cluster"], tm_x["label"], tm_x["summary"])
                        if int(c) != -1}
                report = export_obsidian.export_vault(
                    tm_x, v_x, SLUG, topic_title=config.TOPIC, subtitles=subs)
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                    for f in sorted(report["root"].rglob("*.md")):
                        z.write(f, f.relative_to(report["root"]))
                st.session_state["export_zip"] = buf.getvalue()
                st.session_state["export_report"] = {
                    k: (str(v) if k == "root" else v) for k, v in report.items()}

        report = st.session_state.get("export_report")
        if report:
            c1, c2, c3 = st.columns(3)
            c1.metric("Notes", report["notes"])
            c2.metric("Subtopics", report["subtopics"])
            c3.metric("Must-reads", report["papers"])
            st.download_button("Download the vault (.zip)",
                               data=st.session_state["export_zip"],
                               file_name=f"froth_vault_{SLUG[:40]}.zip",
                               mime="application/zip", icon=":material/download:")
            st.caption(f"Also written to `{report['root']}`. An existing vault is never "
                       "overwritten in place: it is renamed with a dated suffix first.")
            if not report["gaps"]:
                st.info("No gaps note: this topic has no `gaps.parquet` yet. Open the "
                        "Review tab once to compute it, then export again.", icon=":material/info:")
            st.markdown("**To open it in Obsidian** (free, obsidian.md): unzip it, then "
                        "*Open folder as vault* and point at the unzipped folder. Start at "
                        "`_index`. If you do not use Obsidian, the files are ordinary "
                        "markdown and the `.bib` goes straight into Zotero.")

        st.divider()
        st.subheader("Send it to NotebookLM")
        st.caption("The same curated selection, packed for deep reading: the papers grouped "
                   "by subtopic with their abstracts, the open access links, and prompts "
                   "written from what this map MEASURED. You upload it yourself: Google's "
                   "terms forbid reaching NotebookLM by automated means, and the account at "
                   "risk would be yours.")
        if st.button("Build the pack", icon=":material/inventory_2:"):
            with st.spinner("Packing sources..."):
                subs = {int(c): (str(l), str(s)) for c, l, s in
                        zip(tm_x["cluster"], tm_x["label"], tm_x["summary"])
                        if int(c) != -1}
                prep = export_pack.export_pack(tm_x, v_x, SLUG, topic_title=config.TOPIC,
                                               subtitles=subs)
                pbuf = io.BytesIO()
                with zipfile.ZipFile(pbuf, "w", zipfile.ZIP_DEFLATED) as z:
                    for f in sorted(prep["root"].iterdir()):
                        if f.is_file():
                            z.write(f, f.name)
                st.session_state["pack_zip"] = pbuf.getvalue()
                st.session_state["pack_report"] = {
                    k: (str(v) if k == "root" else v) for k, v in prep.items()}

        prep = st.session_state.get("pack_report")
        if prep:
            d1, d2, d3 = st.columns(3)
            d1.metric("Papers", prep["papers"])
            d2.metric("Open access links", prep["oa_links"])
            d3.metric("Words", f"{prep['words']:,}")
            st.download_button("Download the pack (.zip)",
                               data=st.session_state["pack_zip"],
                               file_name=f"froth_pack_{SLUG[:40]}.zip",
                               mime="application/zip", icon=":material/download:")
            if not prep["gaps"]:
                st.info("The pack has no gap prompts: this topic has no `gaps.parquet` yet. "
                        "They are left out rather than invented. Open the Review tab once, "
                        "then build the pack again.", icon=":material/info:")
            st.caption("Open `READ_ME_FIRST.md` inside the zip: it is three steps. "
                       "`sources.md` counts as ONE source in NotebookLM, so it leaves room "
                       "for whatever else you add.")
