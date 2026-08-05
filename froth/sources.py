"""
sources.py - PHASE 5.6: multi-source connectors (the user's own accounts).

WHAT IT DOES: queries sources beyond OpenAlex - Semantic Scholar (free key optional),
Crossref (just an email), Scopus/Elsevier (institutional API key) - normalizes every result
to the papers schema, and de-duplicates against the OpenAlex base by DOI then title.
Every extra source FAILS SOFT: if one is down or rate-limited, the pull continues.

ResearchGate is deliberately NOT here: it has no public API and scraping breaks its ToS.
Legal alternatives already covered: Semantic Scholar, Crossref (and CORE/Lens if ever needed).

Credentials come from env vars or the gitignored .froth_keys file (see config.get_key);
the app's "Connect institutional account" panel writes that file.
"""

import re
import time

import pandas as pd
import requests

from . import config

S2_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
CROSSREF_URL = "https://api.crossref.org/works"
SCOPUS_URL = "https://api.elsevier.com/content/search/scopus"


def source_status() -> dict:
    """Which connectors are usable right now (drives the Sources panel badges)."""
    return {
        "openalex": {"connected": True,
                     "detail": "API key" if config.OPENALEX_API_KEY else "polite pool (email)"},
        "semantic_scholar": {"connected": True,
                             "detail": "API key" if config.get_key("SEMANTIC_SCHOLAR_API_KEY")
                             else "free tier (rate-limited)"},
        "crossref": {"connected": True, "detail": f"email: {config.INSTITUTIONAL_EMAIL}"},
        "scopus": {"connected": bool(config.get_key("ELSEVIER_API_KEY")),
                   "detail": "institutional API key" if config.get_key("ELSEVIER_API_KEY")
                   else "needs an Elsevier API key"},
    }


def _row(origin: str, id_: str, doi: str, title: str, year: int, citations,
         authors: str, abstract: str, source: str, oa_url: str = "", query: str = "") -> dict:
    """Normalize any source's paper into the exact papers.parquet schema."""
    return {"id": id_, "doi": doi or "", "title": title or "", "year": int(year),
            "citations": int(citations or 0), "authors": authors or "",
            "abstract": abstract or "", "source": source or "", "references": [],
            "is_oa": bool(oa_url), "oa_url": oa_url or "", "query": query, "origin": origin}


def search_semantic_scholar(query: str, time_budget: float | None = None) -> list[dict]:
    """Semantic Scholar Graph API, PAGINATED (offset) until exhausted or the time
    budget elapses. Keyless is rate-limited; a free key steadies it."""
    budget = time_budget if time_budget is not None else config.PULL_TIME_BUDGET
    headers = {}
    key = config.get_key("SEMANTIC_SCHOLAR_API_KEY")
    if key:
        headers["x-api-key"] = key
    t0, offset, rows = time.time(), 0, []
    while time.time() - t0 < budget:
        params = {"query": query, "limit": 100, "offset": offset,
                  "fields": "title,abstract,year,citationCount,authors,externalIds,"
                            "openAccessPdf,venue"}
        r = requests.get(S2_URL, params=params, headers=headers, timeout=30)
        if r.status_code == 429:                   # throttle: one polite retry
            time.sleep(5)
            r = requests.get(S2_URL, params=params, headers=headers, timeout=30)
            if r.status_code == 429:
                if rows:
                    break                          # keep what we have
                raise RuntimeError("rate-limited (free tier) - a free API key steadies access")
        r.raise_for_status()
        data = r.json()
        page = data.get("data", []) or []
        if not page:
            break
        for p in page:
            if not p.get("year"):
                continue
            doi = (p.get("externalIds") or {}).get("DOI") or ""
            rows.append(_row(
                "semantic_scholar", f"s2:{p.get('paperId', '')}",
                f"https://doi.org/{doi}" if doi else "",
                p.get("title"), p["year"], p.get("citationCount"),
                "; ".join(a.get("name", "") for a in (p.get("authors") or [])),
                p.get("abstract") or "", p.get("venue") or "",
                (p.get("openAccessPdf") or {}).get("url") or "", query))
        nxt = data.get("next")                     # absent/None when results run out
        if nxt is None:
            break
        offset = nxt
        time.sleep(1.1)                            # S2 free tier: ~1 req/s
    return rows


def _strip_jats(text: str) -> str:
    """Crossref abstracts come as JATS XML; strip tags AND HTML entities to plain text.

    (Caught in the 2nd-topic test: '&nbsp;' survived and became a c-TF-IDF keyword.)
    """
    import html
    text = html.unescape(text or "").replace("\xa0", " ")
    return re.sub(r"<[^>]+>", " ", text).replace("\n", " ").strip()


def search_crossref(query: str, time_budget: float | None = None) -> list[dict]:
    """Crossref REST API (free, email only), PAGINATED with a deep-paging cursor until
    results run out or the time budget elapses."""
    budget = time_budget if time_budget is not None else config.PULL_TIME_BUDGET
    t0, cursor, out = time.time(), "*", []
    while cursor and time.time() - t0 < budget:
        params = {"query.bibliographic": query, "rows": 100, "cursor": cursor,
                  "mailto": config.INSTITUTIONAL_EMAIL,
                  "select": "DOI,title,abstract,author,issued,is-referenced-by-count,"
                            "container-title"}
        r = requests.get(CROSSREF_URL, params=params, timeout=30)
        r.raise_for_status()
        msg = r.json().get("message", {})
        items = msg.get("items", []) or []
        if not items:
            break
        for it in items:
            year = ((it.get("issued") or {}).get("date-parts") or [[None]])[0][0]
            if not year:
                continue
            doi = it.get("DOI") or ""
            authors = "; ".join(f"{a.get('given', '')} {a.get('family', '')}".strip()
                                for a in (it.get("author") or []))
            out.append(_row(
                "crossref", f"crossref:{doi}",
                f"https://doi.org/{doi}" if doi else "",
                "; ".join(it.get("title") or []), year,
                it.get("is-referenced-by-count"), authors,
                _strip_jats(it.get("abstract")),
                "; ".join(it.get("container-title") or []), "", query))
        nxt = msg.get("next-cursor")
        cursor = nxt if nxt and nxt != cursor else None
        time.sleep(0.3)
    return out


def search_scopus(query: str, time_budget: float | None = None) -> list[dict]:
    """Elsevier Scopus Search API (institutional key), PAGINATED with start+count
    (25/request, its max) until the reported total is reached or the budget elapses."""
    key = config.get_key("ELSEVIER_API_KEY")
    if not key:
        return []
    budget = time_budget if time_budget is not None else config.PULL_TIME_BUDGET
    headers = {"X-ELS-APIKey": key, "Accept": "application/json"}
    t0, start, out = time.time(), 0, []
    while time.time() - t0 < budget:
        params = {"query": f"TITLE-ABS-KEY({query})", "count": 25, "start": start}
        r = requests.get(SCOPUS_URL, params=params, headers=headers, timeout=30)
        r.raise_for_status()
        sr = r.json().get("search-results", {})
        entries = sr.get("entry", []) or []
        if not entries or entries[0].get("error"):
            break
        for e in entries:
            if e.get("error"):
                continue
            year = (e.get("prism:coverDate") or "")[:4]
            if not year.isdigit():
                continue
            doi = e.get("prism:doi") or ""
            out.append(_row(
                "scopus", f"scopus:{e.get('dc:identifier', '')}",
                f"https://doi.org/{doi}" if doi else "",
                e.get("dc:title"), int(year), e.get("citedby-count"),
                e.get("dc:creator") or "",          # Scopus search returns 1st author only
                e.get("dc:description") or "",       # abstract needs entitlement; often empty
                e.get("prism:publicationName") or "", "", query))
        total = int(sr.get("opensearch:totalResults", 0) or 0)
        start += 25
        if start >= total:
            break
        time.sleep(0.3)
    return out


def pull_extra_sources(terms: list[str], per_term: int = 25) -> pd.DataFrame:
    """Query every available extra source for every term, each source PAGINATING to
    exhaustion within its time budget. Each source fails soft: one bad source never
    kills the pull. (`per_term` kept for signature compatibility; paging is now
    time-bounded, not count-bounded.)"""
    searchers = [("semantic_scholar", search_semantic_scholar),
                 ("crossref", search_crossref)]
    if config.get_key("ELSEVIER_API_KEY"):
        searchers.append(("scopus", search_scopus))

    # Share each source's budget across its terms; the per-source clock is the guard
    # against a hang (fix for the old 41-min outlier), not a paper-count ceiling.
    per_term_budget = config.PULL_TIME_BUDGET / max(len(terms), 1)
    rows = []
    for name, fn in searchers:
        print(f"  extra source: {name} ...")
        got, t0 = 0, time.time()
        for t in terms:
            if time.time() - t0 > config.PULL_TIME_BUDGET:
                print(f"    ({name}: time budget hit; moving on)")
                break
            try:
                found = fn(t, time_budget=per_term_budget)
                rows += found
                got += len(found)
            except Exception as e:
                print(f"    (warning) {name} stopped: {e}")
                break                              # this source is down; move on to the next
            time.sleep(0.3)                        # per-page pacing lives inside each searcher
        print(f"    {name}: {got} raw results")
    return pd.DataFrame(rows)


def enrich_missing_abstracts(df: pd.DataFrame) -> pd.DataFrame:
    """Second chance for rows that arrived WITHOUT an abstract but WITH a DOI.

    Scopus search results carry no abstract (entitlement) and many Crossref records skip
    it too - but OpenAlex often has it. We batch-look those DOIs up in OpenAlex (50 per
    call) and rebuild the abstract from its inverted index. Discovery from one source,
    content from another: connectors composing instead of competing.
    """
    from .pull import _reconstruct_abstract          # call-time import: no circularity

    need = df[(df["abstract"].str.len() <= 20) & (df["doi"].astype(str) != "")]
    if need.empty:
        return df

    found: dict[str, str] = {}
    dois = [_norm_doi(d) for d in need["doi"] if _norm_doi(d)]
    # This is the ONE pull loop without its own time cap (Phase A-fix): on a huge corpus with
    # thousands of abstract-less rows it can fire hundreds of sequential lookups. Bound it by
    # the same budget the sources use, and use a (connect, read) timeout so no single call wedges.
    t0 = time.time()
    for i in range(0, len(dois), 50):
        if time.time() - t0 > config.PULL_TIME_BUDGET:
            print("    (abstract enrichment: time budget hit; moving on)")
            break
        chunk = dois[i:i + 50]
        params = {"filter": "doi:" + "|".join(chunk), "per_page": 50,
                  "select": "doi,abstract_inverted_index", "mailto": config.MAILTO}
        key = config.get_key("OPENALEX_API_KEY") or config.OPENALEX_API_KEY
        if key:
            params["api_key"] = key
        try:
            r = requests.get("https://api.openalex.org/works", params=params, timeout=(10, 30))
            r.raise_for_status()
            for w in r.json().get("results", []):
                text = _reconstruct_abstract(w.get("abstract_inverted_index"))
                if len(text) > 20:
                    found[_norm_doi(w.get("doi"))] = text
        except Exception as e:
            print(f"    (warning) abstract enrichment stopped: {e}")
            break
        time.sleep(0.3)

    if found:
        mask = df.index.isin(need.index)
        df.loc[mask, "abstract"] = [
            found.get(_norm_doi(d), a) for d, a in zip(df.loc[mask, "doi"],
                                                       df.loc[mask, "abstract"])]
        print(f"  abstract enrichment: recovered {len(found)} abstracts via OpenAlex DOI lookup")
    return df


def _norm_doi(s) -> str:
    return str(s or "").lower().replace("https://doi.org/", "").strip()


def _norm_title(s) -> str:
    return re.sub(r"\W+", "", str(s or "").lower())[:80]


def merge_dedup(base: pd.DataFrame, extra: pd.DataFrame):
    """Union keeping OpenAlex as the preferred record (richest: abstracts + references).
    Dedup key: normalized DOI first, then normalized title (papers without DOI)."""
    if extra is None or extra.empty:
        return base, {"added": 0, "dupes": 0}
    seen_doi = {_norm_doi(d) for d in base["doi"] if _norm_doi(d)}
    seen_title = {_norm_title(t) for t in base["title"]}
    keep = []
    for _, r in extra.iterrows():
        nd, nt = _norm_doi(r["doi"]), _norm_title(r["title"])
        if (nd and nd in seen_doi) or (nt and nt in seen_title):
            continue
        if nd:
            seen_doi.add(nd)
        seen_title.add(nt)
        keep.append(r)
    if not keep:
        return base, {"added": 0, "dupes": len(extra)}
    merged = pd.concat([base, pd.DataFrame(keep)], ignore_index=True)
    return merged, {"added": len(keep), "dupes": len(extra) - len(keep)}
