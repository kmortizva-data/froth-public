"""
config.py - the project's "recipe book".

All SETTINGS live here in one place: the topic, folder paths, the embedding model, etc.
Project golden rule: to switch topic you do NOT touch the code, you only change the TOPIC
variable below. That is what makes the system "generalizable".
"""

import os
import re
from pathlib import Path

# --- Folders (derived automatically from where this file lives) ---
ROOT = Path(__file__).resolve().parent.parent      # the "Master Thesis AI" folder
DATA_RAW = ROOT / "2_Datos" / "raw"
DATA_PROCESSED = ROOT / "2_Datos" / "processed"
DATA_EMBEDDINGS = ROOT / "2_Datos" / "embeddings"
DELIVERABLES = ROOT / "3_Resultados"

# --- Current topic (change ONLY this to try another subject) ---
# TOPIC = the FULL, LITERAL thesis title, copied CHARACTER BY CHARACTER from the allocation
# spreadsheet (EMerald_masterthesis_allocation_cohort11.csv, author: Fareed Ahmad Azizi).
# RULE: full fidelity, do NOT "fix" or simplify. The system will be reused with other titles
# we do not know yet; each must go in exactly as written in its source.
TOPIC = ("Flotation of differently sized Li bearing mica minerals and its impact on the "
         "by-products (Ta, Nb, Be,…) recovery from Rare Metal Granite of Beauvoir deposit "
         "(Allier, France)")

# SEARCH_TERMS = broad, concept-based terms for the API (the literal title would return too few papers).
SEARCH_TERMS = [
    "lepidolite flotation", "lithium mica flotation", "zinnwaldite flotation",
    "particle size effect froth flotation", "fine particle flotation",
    "tantalum niobium beryllium recovery", "Ta Nb Be by-product mineral",
    "Rare Metal Granite", "Beauvoir deposit Allier", "LCT pegmatite granite lithium",
]
MAX_PAPERS = 400          # how many papers to download for the first map

# --- Multi-topic engine (Phase 6.1) ---
# The values above are the DEFAULT (test) topic with its hand-tuned terms, living in the
# legacy root data folders so nothing breaks. Any OTHER topic gets its own data folders
# under 2_Datos/topics/<slug>/ and derived search terms - no code edits needed.
DEFAULT_TOPIC = TOPIC
DEFAULT_SEARCH_TERMS = list(SEARCH_TERMS)
# The first topic predates per-topic folders, so its slug is this literal rather than
# slugify(DEFAULT_TOPIC), and its data stays in the legacy 2_Datos/ layout. Defined once
# here because app.py and paths_for() must agree on it exactly.
DEFAULT_SLUG = "default"


def slugify(text: str, max_len: int = 60) -> str:
    """'Scheelite ores...' -> 'scheelite-ores...-a1b2c3' (readable + unique).

    The short hash suffix guarantees two different titles NEVER share a folder - learned
    the hard way in the cohort batch: two near-identical grinding titles truncated to the
    same 50-char slug and one silently reused the other's data.
    """
    import hashlib
    import unicodedata
    digest = hashlib.md5(text.encode("utf-8")).hexdigest()[:6]
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return f"{slug[:max_len].rstrip('-')}-{digest}"


TOPICS_REGISTRY = ROOT / "2_Datos" / "topics_registry.csv"


def register_topic(title: str) -> None:
    """Remember slug<->title (slugs are truncated+hashed, so titles can't be rebuilt)."""
    if title == DEFAULT_TOPIC:
        return
    slug = slugify(title)
    lines = TOPICS_REGISTRY.read_text(encoding="utf-8").splitlines() if TOPICS_REGISTRY.exists() else []
    if any(line.split(",", 1)[0] == slug for line in lines):
        return
    TOPICS_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    with TOPICS_REGISTRY.open("a", encoding="utf-8") as f:
        f.write(f"{slug},{title}\n")


def known_topics() -> list[tuple[str, bool]]:
    """(title, is_harvested) for the default topic + every registered one."""
    out = [(DEFAULT_TOPIC, (ROOT / "2_Datos" / "processed" / "topic_map.parquet").exists())]
    if TOPICS_REGISTRY.exists():
        for line in TOPICS_REGISTRY.read_text(encoding="utf-8").splitlines():
            if "," not in line:
                continue
            slug, title = line.split(",", 1)
            ready = (ROOT / "2_Datos" / "topics" / slug / "processed" / "topic_map.parquet").exists()
            out.append((title, ready))
    return out


def paths_for(slug: str) -> dict:
    """Folders of ONE topic, resolved from its slug alone. Reads no mutable state.

    set_topic() rewrites module-level globals, which makes "which topic am I reading?"
    depend on WHEN you ask. That is fine for the pipeline CLIs (single topic per process)
    but wrong for the app's cached loaders: a cache keyed by slug whose body reads the
    globals can store one topic's data under another topic's key, and the mislabelled
    entry then survives every later rerun. Resolving from the slug makes that impossible
    by construction.

    The default topic predates per-topic folders and still lives in the legacy layout.
    """
    if slug == DEFAULT_SLUG:
        base = ROOT / "2_Datos"
        return {"raw": base / "raw", "processed": base / "processed",
                "embeddings": base / "embeddings",
                "deliverables": ROOT / "3_Resultados"}
    base = ROOT / "2_Datos" / "topics" / slug
    return {"raw": base / "raw", "processed": base / "processed",
            "embeddings": base / "embeddings",
            "deliverables": ROOT / "3_Resultados" / "topics" / slug}


def set_topic(topic: str, search_terms: list[str] | None = None) -> None:
    """Point the WHOLE engine at another topic (paths + terms), in-process.

    Every pipeline module reads config attributes at call time, so after set_topic()
    the same pull/embed/cluster/graph/gaps functions work on the new topic's folders.
    """
    global TOPIC, SEARCH_TERMS, DATA_RAW, DATA_PROCESSED, DATA_EMBEDDINGS, DELIVERABLES
    TOPIC = topic
    if topic == DEFAULT_TOPIC:
        SEARCH_TERMS = list(DEFAULT_SEARCH_TERMS)      # keep the hand-tuned ones
        DATA_RAW = ROOT / "2_Datos" / "raw"
        DATA_PROCESSED = ROOT / "2_Datos" / "processed"
        DATA_EMBEDDINGS = ROOT / "2_Datos" / "embeddings"
        DELIVERABLES = ROOT / "3_Resultados"
        return
    if search_terms is None:
        from .terms import derive_search_terms
        search_terms = derive_search_terms(topic)
    SEARCH_TERMS = list(search_terms)
    base = ROOT / "2_Datos" / "topics" / slugify(topic)
    DATA_RAW = base / "raw"
    DATA_PROCESSED = base / "processed"
    DATA_EMBEDDINGS = base / "embeddings"
    DELIVERABLES = ROOT / "3_Resultados" / "topics" / slugify(topic)

# --- OpenAlex API key (secret: NOT written here, NOT committed to Git) ---
# With a key, OpenAlex gives uninterrupted access ($1/day ~ 1000 searches). Without a key it
# rate-limits you when overloaded (the 503 error we saw). The key is read from two places,
# in this order:
#   1) the OPENALEX_API_KEY environment variable, or
#   2) a text file ".openalex_key" in the project root (a single line).
# That file is in .gitignore, so your key is never uploaded anywhere.
def _load_api_key() -> str | None:
    key = os.getenv("OPENALEX_API_KEY")
    if key:
        return key.strip()
    key_file = ROOT / ".openalex_key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip() or None
    return None

OPENALEX_API_KEY = _load_api_key()

# Email for OpenAlex's "polite pool" (better priority even without a key).
MAILTO = "kmortizva@datageeksunited.com"

# --- Multi-source connectors (Phase 5.6): the user's own accounts ---
# The "Connect institutional account" panel writes .froth_keys (gitignored): one KEY=value
# per line. Env vars win over the file. Public-web builds must keep keys session-only.
def load_keyfile() -> dict:
    path = ROOT / ".froth_keys"
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def get_key(name: str) -> str | None:
    """Read a connector credential FRESH each call (env var wins over .froth_keys),
    so the app picks up newly saved keys without a restart."""
    return os.getenv(name) or load_keyfile().get(name) or None


INSTITUTIONAL_EMAIL = get_key("INSTITUTIONAL_EMAIL") or MAILTO
# Free extra sources (Semantic Scholar keyless tier + Crossref) are ON by default and
# fail soft; set USE_EXTRA_SOURCES=false in .froth_keys to pull from OpenAlex only.
USE_EXTRA_SOURCES = (get_key("USE_EXTRA_SOURCES") or "true").lower() != "false"

# --- Coverage, not a ceiling (Batman: a thesis review can't say "not in the first 200,
# not relevant"). Every source PAGINATES until its results are exhausted; the only
# guard against a hang is a per-source time budget (seconds). NOT a magic paper count -
# the real limit is "results ran out or the budget elapsed", and the relevance filter
# cleans the extra. Raise PULL_TIME_BUDGET for an even more exhaustive sweep. ---
PULL_TIME_BUDGET = int(get_key("PULL_TIME_BUDGET") or 180)

# --- Per-topic watchdog (Phase A-fix) ---
# The per-source time budget guards a single source, but a whole topic can still wedge
# (a stalled network read, a GPU stall, or the DBCV sweep on a huge corpus). The batch runs
# each topic in a SUBPROCESS with this hard wall-clock timeout: if a topic overruns it is
# killed and marked FAILED, so ONE bad topic can never freeze the whole run again. Generous
# on purpose - the slowest legitimate topic so far took 38 min.
TOPIC_TIMEOUT_S = int(get_key("TOPIC_TIMEOUT_S") or 2400)

# --- Model that turns text into vectors (Phase 2) ---
# Production = specter-mineral-v1 WHEN the local folder exists (Batman blind-picked its
# map twice - 2026-07-12 and 2026-07-16 - and it beats base on DBCV 14/22): his personal
# install gets the domain-tuned maps. Public installs have no models/ folder and fall
# back to stock SPECTER from the HF hub - zero friction, nothing to download by hand.
# (v3, the citation-triplet model, reads WORSE as a map despite the best DBCV - kept for
# the future seed-mode where citation geometry is exactly the wanted signal.)
_V1_LOCAL = ROOT / "models" / "specter-mineral-v1"
EMBEDDING_MODEL = str(_V1_LOCAL) if _V1_LOCAL.exists() else "allenai-specter"

# --- Relevance filter (Phase 1/3 data quality) ---
# Every paper gets a relevance score = cosine similarity to the TOPIC itself. Papers below
# this threshold are dropped from the map (off-topic intruders from colliding search terms).
# 0.55 was chosen by LOOKING AT THE DATA: intruders scored <= 0.543, everything legit
# (including lithium recycling/economy papers) scored >= 0.587 - a natural gap.
RELEVANCE_THRESHOLD = 0.55

# --- Clustering (Phase 3) ---
MIN_CLUSTER_SIZE = 8      # minimum size of a subtopic for HDBSCAN
# DBCV (hdbscan's relative_validity_) is ~O(n^2): the auto-granularity sweep runs it ~18x,
# which on tens of thousands of points can take hours or thrash RAM (Phase A-fix: the batch
# froze on a huge topic). Above this many points the sweep runs on a random subsample - the
# granularity it picks is stable, the cost is not. The final clustering still uses ALL points.
DBCV_SUBSAMPLE_CAP = int(get_key("DBCV_SUBSAMPLE_CAP") or 5000)

# --- Similarity network (Phase 4) ---
# Each paper connects to its GRAPH_KNN most similar papers (cosine in 768D), keeping only
# edges >= GRAPH_SIM_THRESHOLD. Chosen by comparing K in {3,5,8,10,15} and thr in
# {0.70..0.85}: K=5/0.75 gives ~7.6 connections per paper (readable), 21% cross-cluster
# edges (bridges visible) and a single connected network (no islands).
GRAPH_KNN = 5
GRAPH_SIM_THRESHOLD = 0.75

# --- Scale guard for the heavy views (Phase D.5) ---
# The uncapped harvest grew corpora from ~220 to 8k-16k papers. The Network (vis.js physics)
# and Reading-guide (animated SVG) views draw one element per paper, so above this many
# papers those tabs render a most-cited subset (whole clusters, see _cap_for_heavy_views)
# with an honest notice; the Atlas (WebGL, Phase D) is the full-corpus view. Not a ceiling
# on DATA - only on what these two physics/animation renderers are asked to draw.
#
# HISTORY OF THIS NUMBER, honestly:
#   2026-07-23  I raised it 400 -> 2500 "measured in the browser". That measurement was
#               wrong for the decision: it timed GENERATION (Python building the HTML) and
#               vis.js's stabilization EVENT, both of which are cheap at 1879 nodes (~6s).
#               It did NOT measure INTERACTION, because this environment freezes
#               requestAnimationFrame in an unfocused pane, so I cannot feel zoom/pan here.
#   2026-07-25  Batman ran it on his real machine at 1772 nodes: a frozen hairball, no
#               zoom, no pan. That is the ground truth. forceAtlas2 recomputes forces every
#               frame AND vis.js hit-tests every node on mouse-move, so past a few hundred
#               nodes the main thread has nothing left for the wheel. The bounded physics
#               (minVelocity, restPhysics) stops the SETTLING but not the per-frame cost.
# Lesson kept on purpose: a render being fast to PRODUCE says nothing about being fluid to
# USE. Measure the thing the user actually does.
#
# Reverted to 400 (~266 nodes on Beauvoir), the pre-uncapped smooth zone. This is NOT a
# regression: it is division of labour. The Network is now a readable map of the most-cited
# CORE neighbourhood, where physics genuinely helps; the Atlas (WebGL, no physics, one
# canvas) is the view for seeing all 2759 papers at once. Right renderer per zoom level,
# which is the whole point of the Atlas.
#
# Interactive smoothness is the ONE thing only Batman's machine can judge (rAF is frozen
# here). If 400 feels too sparse and his machine handles more, bump HEAVY_VIEW_MAX_PAPERS
# in .froth_keys - no code change. A per-view split (a higher cap for the SVG reading
# guide, which has no physics) is a future option, deliberately not taken now to keep this
# a one-line fix.
HEAVY_VIEW_MAX_PAPERS = int(get_key("HEAVY_VIEW_MAX_PAPERS") or 400)

# How many papers ONE subtopic may contribute to the heavy views. Without this, the budget
# above is spent by the first one or two subtopics: on the 5752-paper thesis corpus the
# Network drew 2 of 44 subtopics, so no paper could sit between two subtopics and the bridge
# markers were always empty (Batman, 2026-08-13: "aca literal ningun paper es puente").
# Measured on that corpus at the same 400-paper budget: no cap = 2 islands / 0 bridges;
# 60 = 8 / 17; 30 = 14 / 25; 20 = 21 / 23. Batman chose 30 looking at that table: the most
# bridges before the islands thin out into the confetti the whole-cluster rule was avoiding.
# Corpus-dependent like every other knob here, so it is overridable in .froth_keys.
NETWORK_MAX_PER_CLUSTER = int(get_key("NETWORK_MAX_PER_CLUSTER") or 30)
