"""
terms.py - PHASE 6.1: derive search terms from ANY thesis title.

WHAT IT DOES: the original SEARCH_TERMS were hand-written for one topic. To generalize,
this module derives them automatically from a title: it keeps the meaningful words, forms
the phrases as they appear in the title (bigrams/trigrams), preserves acronyms (XRD, LIBS)
and parenthetical content (Ta, Nb, Be...), and returns a capped list of API-friendly terms.

Deterministic heuristic BASELINE - always works, zero dependencies. An optional local-LLM
layer (Ollama) can refine/expand these later (Phase 6 decision: local, private, free).
"""

import re

# Filler words that carry no search signal in thesis titles (English core + academic filler).
STOPWORDS = {
    "a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "its", "it",
    "of", "on", "or", "the", "their", "through", "to", "toward", "towards", "via",
    "with", "using", "use", "used", "based", "study", "studies", "method", "methods",
    "approach", "approaches", "innovative", "novel", "new", "implementation",
    "exploring", "effect", "effects", "impact", "possibilities", "increased",
    "obtaining", "additional", "routine", "tool", "small", "scale", "small-scale",
    "complex", "differently", "sized", "applied", "derived",
}

_ACRONYM = re.compile(r"^[A-Z][A-Za-z]?[A-Z0-9]*$")     # XRD, LIBS, FTIR, PGE, NiMH, 3D


def _content_words(text: str) -> list[str]:
    """Title words that carry meaning: not stopwords, and either long or acronym-like."""
    words = re.findall(r"[A-Za-z][A-Za-z0-9\-]*", text)
    out = []
    for w in words:
        if w.lower() in STOPWORDS:
            continue
        if len(w) > 2 or _ACRONYM.match(w):
            out.append(w)
    return out


def derive_search_terms(title: str, max_terms: int = 8) -> list[str]:
    """Turn a thesis title into a list of broad, API-friendly search terms.

    Strategy: (1) parenthetical content becomes its own term (it holds the specifics:
    elements, deposit names); (2) consecutive content-word pairs/triples keep the title's
    real phrases ('froth flotation', 'scheelite ores', 'quantitative XRD'); (3) the
    cleaned title itself goes first (search engines handle long queries well).
    """
    terms: list[str] = []

    def add(t: str):
        t = t.strip()
        if t and t.lower() not in (x.lower() for x in terms):
            terms.append(t)

    # (1) parentheses hold the payload: "(Ta, Nb, Be,…)" / "(Allier, France)"
    parens = re.findall(r"\(([^)]+)\)", title)
    body = re.sub(r"\([^)]*\)", " ", title)

    # (3) the cleaned full title, trimmed to something an API likes
    words = _content_words(body)
    add(" ".join(words[:8]))

    # (2) phrases as they appear in the title: consecutive content words
    for size in (3, 2):
        for i in range(len(words) - size + 1):
            add(" ".join(words[i:i + size]))

    for p in parens:
        cleaned = re.sub(r"[^\w\s\-]", " ", p).strip()
        if cleaned:
            add(cleaned)

    return terms[:max_terms]


def broaden_terms(title: str) -> list[str]:
    """Fallback query when the derived terms return NOTHING - a niche title whose specific
    proper nouns match no papers (e.g. 'Recovery ... from the a rare-metal granite' -> 0 in Phase A).
    A title usually leads with its topic, so the first few generic content words make one
    broad, high-recall query. Used by batch.run_topic before it gives a topic up as FAILED."""
    words = _content_words(re.sub(r"\([^)]*\)", " ", title))
    return [" ".join(w.lower() for w in words[:3])] if words else []
