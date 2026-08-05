"""
embed.py - PHASE 2: text to vectors (embeddings).

WHAT IT DOES: takes each abstract and turns it into a list of ~768 numbers (a "vector") that
captures its meaning, using an ALREADY-trained model (SPECTER, built for papers). Saves the
matrix of vectors to 2_Datos/embeddings/.

HOW TO RUN IT (compute and save the vectors for all papers):
    .venv\\Scripts\\python.exe -m froth.embed

WHAT YOU LEARN HERE:
- What an embedding is and why similar papers give nearby vectors (Note 05).
- Using a pretrained model with `sentence-transformers` (no training, Note 06).
- Vectorizing in batch (all at once) and saving the matrix to disk (Note 07).

First "wow" moment (next step): type a phrase and find the most similar papers.
"""

import re
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

from . import config

# sentence_transformers (and the torch it drags in) is imported INSIDE _get_model, not here.
# Measured on Batman's machine: importing it at module load cost 19.7s of the 52.2s the web
# app spent before painting anything, and the home screen never embeds a single sentence.
# Everything that DOES need the model already funnels through _get_model, so one deferred
# import covers the whole module. TYPE_CHECKING keeps the type hints without the runtime cost.
if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

# The model is cached here the first time it loads, to avoid reloading it on every call.
_MODEL: "SentenceTransformer | None" = None


def _get_model() -> "SentenceTransformer":
    """Load SPECTER once and reuse it. First time downloads ~440 MB (then served from cache)."""
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer    # deferred: see note above
        print(f"  loading model '{config.EMBEDDING_MODEL}' ...")
        _MODEL = SentenceTransformer(config.EMBEDDING_MODEL)
    return _MODEL


def _text_of(paper: pd.Series) -> str:
    """SPECTER expects TITLE + ABSTRACT together: the title carries strong topic signal."""
    return f"{paper['title']}. {paper['abstract']}"


def embed_papers(df: pd.DataFrame) -> np.ndarray:
    """Turn the table's abstracts into a matrix of vectors of shape (N, 768).

    Row i of the matrix is the vector of the paper at row i of `df` (same order).
    """
    model = _get_model()
    # Build the list of texts (one per paper) and vectorize them ALL at once.
    # Passing the full list is faster than calling encode() paper by paper (it batches).
    texts = [_text_of(paper) for _, paper in df.iterrows()]
    print(f"  vectorizing {len(texts)} papers ...")
    vectors = model.encode(texts, show_progress_bar=True)
    return np.asarray(vectors)


def save_embeddings(vectors: np.ndarray) -> None:
    """Save the matrix to 2_Datos/embeddings/vectors.npy (NumPy format, fast to reload)."""
    config.DATA_EMBEDDINGS.mkdir(parents=True, exist_ok=True)
    out_path = config.DATA_EMBEDDINGS / "vectors.npy"
    np.save(out_path, vectors)
    print(f"\nSaved {vectors.shape[0]} vectors of dimension {vectors.shape[1]} to:\n  {out_path}")


def load_embeddings(folder=None) -> np.ndarray:
    """Reload the saved matrix (for later phases, without recomputing).

    `folder` pins WHICH topic's vectors to read. Omitted, it falls back to the active
    topic's folder, which is what the pipeline CLIs want (one topic per process). The
    app passes it explicitly so a cached read cannot depend on when it happens to run.
    """
    base = config.DATA_EMBEDDINGS if folder is None else folder
    return np.load(base / "vectors.npy")


def relevance_to_topic(vectors: np.ndarray) -> np.ndarray:
    """Score every paper against the thesis TOPIC itself (cosine similarity).

    The system cleans itself with its own embeddings: off-topic intruders (from colliding
    search terms) score low and can be filtered with config.RELEVANCE_THRESHOLD.
    """
    model = _get_model()
    topic_vec = model.encode([config.TOPIC])
    return cosine_similarity(topic_vec, vectors)[0]


def _symbol_facets(title: str) -> list[str]:
    """Bracketed lists of chemical symbols in a title, as extra scoring facets.

    derive_search_terms() drops what is in brackets, which is fine for SEARCHING but loses
    a real idea when the brackets hold the by-products a thesis is about: "its impact on
    the by-products (Ta, Nb, Be,...) recovery". With no facet speaking for them, tantalum
    coverage fell from 90% to 59% and papers like "Separation of Tantalum and Niobium by
    Solvent Extraction" were dropped.

    Only groups that LOOK like a symbol list qualify: two or more comma-separated tokens,
    each at most 3 characters. "(Ta, Nb, Be,...)" qualifies and "(Allier, France)" does not,
    which matters: measured on the thesis corpus, adding the place name pulls in a taxation
    hub, because a toponym attracts regional-economics literature. Restricting to symbols
    gives the same benefit for half the cost - lepidolite 92 -> 96%, tantalum 68 -> 73%,
    niobium 56 -> 60%, beryllium 80 -> 84%, with one junk hub admitted instead of two.

    The one that still gets in is gender studies, most likely because "Be" is also an
    ordinary English word. Batman accepted that cost knowingly. Filtering symbols that
    collide with common words is a possible refinement, not chased here.
    """
    out = []
    for group in re.findall(r"\(([^)]*)\)", title):
        toks = [t.strip(" .…") for t in re.split(r"[,;/]", group)]
        toks = [t for t in toks if t]
        if len(toks) >= 2 and all(len(t) <= 3 for t in toks):
            out.append(", ".join(toks))
    return out


def relevance_to_topic_v3(vectors: np.ndarray, facets: list[str] | None = None,
                          core_n: int = 200, penalty: float = 0.4) -> np.ndarray:
    """FACET-AWARE contrastive relevance (2026-08-03). One core per idea in the title.

    WHY v2 BROKE, measured on two real corpora. A thesis title usually names a MATERIAL
    and a METHOD: "Flotation of differently sized Li bearing mica minerals",
    "beneficiation of scheelite ores by froth flotation". v2 builds ONE core from the
    papers most similar to the whole title, then re-picks that core using its own score,
    twice. When the harvest is dominated by one facet, that loop feeds itself: the core
    collapses onto the dominant facet and everything about the other one reads as generic.

    What that cost, in papers kept out of papers harvested:

        thesis corpus     lepidolite 191/202 (95%)   flotation  157/2752 (6%)
        scheelite ores   wolframite  84/139 (60%)   froth        16/1454 (1%)

    Both titles have the method in them. Both maps threw the method away and kept the
    mineral, and nothing in the output said so.

    THE FIX: score against each facet SEPARATELY and keep the best.

        v3(paper) = max over facets of [ cos(paper, core_f) - penalty * cos(paper, generic_f) ]

    A facet's core is seeded from that facet's own phrase, so it cannot drift into the
    dominant one; the refinement pass still runs, but anchored per facet. The generic
    reference has that facet's direction projected out, which is v2's own fix for
    punishing a paper on the very words of its title, applied per facet.

    Facets come from terms.derive_search_terms(), the same phrases that drove the harvest,
    so no new notion of "what this topic is about" is invented here.

    Taking the max is deliberately a UNION: a paper about flotation of a different mineral
    scores on the method facet and survives. That is the correct answer for a methods
    thesis, and the flood it might let in is what the hub-level gate exists to stop: whole
    subtopics are judged by their mean, so an off-topic hub still dies entire.
    """
    from . import terms as terms_mod

    if not facets:
        facets = (terms_mod.derive_search_terms(config.TOPIC) or [config.TOPIC]) \
                 + _symbol_facets(config.TOPIC)
    norm = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    global_c = norm.mean(axis=0)
    global_c /= np.linalg.norm(global_c)
    core_n = min(core_n, max(20, len(norm) // 10))

    facet_vecs = _get_model().encode(list(facets))
    facet_vecs = facet_vecs / np.linalg.norm(facet_vecs, axis=1, keepdims=True)

    best = None
    for fv in facet_vecs:
        core = np.argsort(norm @ fv)[::-1][:core_n]     # seeded by THIS facet's phrase
        score = None
        for _ in range(2):
            core_c = norm[core].mean(axis=0)
            core_c /= np.linalg.norm(core_c)
            generic_c = global_c - (global_c @ core_c) * core_c
            gn = np.linalg.norm(generic_c)
            generic_c = generic_c / gn if gn > 1e-9 else global_c
            score = norm @ core_c - penalty * (norm @ generic_c)
            core = np.argsort(score)[::-1][:core_n]
        best = score if best is None else np.maximum(best, score)
    return best


def relevance_to_topic_v2(vectors: np.ndarray, title_sim: np.ndarray | None = None,
                          core_n: int = 200, penalty: float = 0.4) -> np.ndarray:
    """CONTRASTIVE relevance for the uncapped era (Phase R, 2026-07-15).

    WHY v1 broke: v1 scores cosine against the topic TITLE - one short sentence. Titles
    carry generic magnets ("circular economy", "management", "iron"), so at 16k harvested
    papers the junk ("CE in Portuguese SMEs", koala chlamydiosis via 'iron' in biology)
    scores 0.55-0.75 and the distribution is UNIMODAL: no cutoff on v1 separates. Batman
    spotted the symptom: a colored HR hub in a flotation topic.

    The fix reuses the contrastive pattern that fixed the KeyBERT titles (review.py):
    reward closeness to the topic CORE and punish closeness to the GENERIC mass:

        v2 = cos(paper, core_centroid) - penalty * cos(paper, global_centroid)

    - core = the corpus' own heart: top `core_n` papers by title similarity (the high
      band is ~clean), refined once by re-picking the core with the provisional v2 score;
    - generic centroid = the whole harvest MINUS the core direction (Phase 8.5b-fix, from
      Batman's blind judging): the raw global centroid points partly toward the topic
      itself (a "circular economy in tailings" corpus is full of circular-economy papers),
      so a core-aligned paper got rewarded by the core AND punished by the global -
      double-penalized on the very term that is in its OWN title. Projecting the core
      direction out of the global leaves only the OFF-topic generic mass to punish, so
      "Towards Circular Economy Metrics" stops being cut while koala/HR papers still are.
    The result is BIMODAL, so a per-corpus valley threshold exists (auto_relevance_threshold).
    """
    if title_sim is None:
        title_sim = relevance_to_topic(vectors)
    norm = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    global_c = norm.mean(axis=0)
    global_c /= np.linalg.norm(global_c)
    core_n = min(core_n, max(20, len(norm) // 10))
    core = np.argsort(title_sim)[::-1][:core_n]
    score = None
    for _ in range(2):                              # seed pass + one refinement pass
        core_c = norm[core].mean(axis=0)
        core_c /= np.linalg.norm(core_c)
        # Generic reference = global centroid with the topic-core direction removed, so
        # the penalty never punishes a paper for pointing at its own title.
        generic_c = global_c - (global_c @ core_c) * core_c
        gn = np.linalg.norm(generic_c)
        generic_c = generic_c / gn if gn > 1e-9 else global_c
        score = norm @ core_c - penalty * (norm @ generic_c)
        core = np.argsort(score)[::-1][:core_n]
    return score


def auto_relevance_threshold(scores: np.ndarray) -> float:
    """Per-corpus cutoff: the VALLEY between the two modes of the contrastive score
    (rule 9: computed from THIS corpus' distribution, not a fossilized global constant).

    Smoothed histogram -> two tallest well-separated peaks -> deepest bin between them.
    If the distribution turns out unimodal (an already-clean corpus), fall back to the
    5th percentile: trim only the extreme tail rather than invent a cut. Bin count
    adapts to small populations (Phase 8.5b gates ~50-150 CLUSTER means, not 16k papers).
    """
    bins = int(max(10, min(60, len(scores) // 3)))
    min_gap = max(3, bins // 8)                    # "meaningfully apart" scales with bins
    hist, edges = np.histogram(scores, bins=bins)
    kernel = np.ones(5) / 5.0
    smooth = np.convolve(hist, kernel, mode="same")
    peaks = [i for i in range(1, bins - 1)
             if smooth[i] >= smooth[i - 1] and smooth[i] >= smooth[i + 1]
             and smooth[i] > 0.05 * smooth.max()]
    if len(peaks) >= 2:
        # The two tallest peaks that are meaningfully apart (~ separate modes).
        peaks.sort(key=lambda i: -smooth[i])
        for a in peaks:
            for b in peaks:
                if abs(a - b) >= min_gap:
                    lo, hi = sorted((a, b))
                    valley = lo + int(np.argmin(smooth[lo:hi + 1]))
                    return float((edges[valley] + edges[valley + 1]) / 2)
    return float(np.percentile(scores, 5))


def embed_texts_mean(texts: list[str]) -> np.ndarray | None:
    """One query vector for LONG inputs (e.g. instruction PDFs): chunk + mean-pool.

    SPECTER truncates anything beyond ~512 tokens, so feeding it a whole PDF would silently
    use only the first page. Instead we split every text into ~180-word chunks, embed each,
    and average them: the mean vector represents the WHOLE task. Returns shape (1, 768).
    """
    model = _get_model()
    chunks = []
    for t in texts:
        words = str(t).split()
        for i in range(0, len(words), 180):
            chunk = " ".join(words[i:i + 180]).strip()
            if len(chunk) > 40:                      # skip near-empty fragments
                chunks.append(chunk)
    if not chunks:
        return None
    vecs = model.encode(chunks, show_progress_bar=False)
    return np.asarray(vecs).mean(axis=0, keepdims=True)


def rank_by_vector(q_vec: np.ndarray, df: pd.DataFrame, vectors: np.ndarray,
                   k: int = 10) -> pd.DataFrame:
    """Rank papers against a precomputed query vector (used by the Task module).

    Keeps the original row index so the UI can look the full record back up.
    """
    sims = cosine_similarity(q_vec, vectors)[0]
    top = np.argsort(sims)[::-1][:k]
    cols = [c for c in ("title", "year", "citations", "label", "doi", "oa_url") if c in df.columns]
    result = df.iloc[top][cols].copy()
    result.insert(0, "score", sims[top].round(3))
    return result


def most_similar(query: str, df: pd.DataFrame, vectors: np.ndarray, k: int = 5) -> pd.DataFrame:
    """Semantic search: given a phrase, return the k most similar papers BY MEANING.

    Steps: 1) turn the phrase into a vector with the same model (SPECTER);
           2) measure its cosine similarity against the N papers;
           3) return the k with highest cosine, as a table (score, title, year, citations).
    """
    model = _get_model()
    q_vec = model.encode([query])                 # phrase vector, shape (1, 768)
    sims = cosine_similarity(q_vec, vectors)[0]    # cosine against the N papers, shape (N,)
    top = np.argsort(sims)[::-1][:k]               # indices of the top k, highest first

    # Include link columns when available (doi -> publisher page; oa_url -> free PDF),
    # and the subtopic label when the caller passes a topic map instead of the raw table.
    cols = [c for c in ("title", "year", "citations", "label", "doi", "oa_url") if c in df.columns]
    result = df.iloc[top][cols].copy()
    result.insert(0, "score", sims[top].round(3))   # score = how similar (0 to 1)
    return result.reset_index(drop=True)


if __name__ == "__main__":
    path = config.DATA_PROCESSED / "papers.parquet"
    print(f"Reading papers from: {path}")
    df = pd.read_parquet(path)
    vectors = embed_papers(df)
    save_embeddings(vectors)

    # Score relevance to the topic and persist it alongside the papers.
    print("  scoring relevance to TOPIC ...")
    df["relevance"] = relevance_to_topic(vectors)
    df.to_parquet(path, index=False)
    n_low = int((df["relevance"] < config.RELEVANCE_THRESHOLD).sum())
    print(f"Relevance column added ({n_low} papers below threshold {config.RELEVANCE_THRESHOLD}).")
