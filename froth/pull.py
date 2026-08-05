"""
pull.py - PHASE 1: get the papers (first working version).

WHAT IT DOES: for each search term in config.SEARCH_TERMS it queries the OpenAlex API,
merges the results, removes duplicates, rebuilds the abstracts, and saves a clean table to
2_Datos/processed/papers.parquet.

HOW TO RUN IT:
    python -m froth.pull

CONCEPTS YOU LEARN HERE (read top to bottom; the main function is at the end):
- API: you request data from a server with requests.get(url, params=...).
- JSON: the response comes back as Python dicts/lists (r.json()).
- OpenAlex stores the abstract in an odd way ("inverted index"): instead of the text, it
  stores which positions each word appears at. We must rebuild it -> _reconstruct_abstract().
- pandas.DataFrame: a table; drop_duplicates() removes repeats; to_parquet() saves it.
"""

import time
import requests
import pandas as pd

from . import config

OPENALEX = "https://api.openalex.org/works"


def _reconstruct_abstract(inverted_index) -> str:
    """OpenAlex gives the abstract as {word: [positions]}. We turn it back into plain text."""
    if not inverted_index:
        return ""
    positions = {}
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions[i] = word
    return " ".join(positions[i] for i in sorted(positions))


def _authors(authorships) -> str:
    """Turn OpenAlex's author list into a plain string 'A; B; C'."""
    if not authorships:
        return ""
    names = [a.get("author", {}).get("display_name", "") for a in authorships]
    return "; ".join(n for n in names if n)


def search_openalex(query: str, per_page: int = 200,
                    time_budget: float | None = None) -> list[dict]:
    """Query OpenAlex for ONE term, PAGINATING (cursor) until its results run out or
    the time budget elapses (Batman: coverage, not a 25-result ceiling). per_page=200
    is OpenAlex's max; the relevance filter cleans any off-topic overreach later."""
    budget = time_budget if time_budget is not None else config.PULL_TIME_BUDGET
    t0, cursor, results = time.time(), "*", []
    while cursor and time.time() - t0 < budget:
        params = {
            "search": query, "per_page": per_page, "cursor": cursor,
            "mailto": config.MAILTO,
            "select": "id,doi,title,publication_year,cited_by_count,"
                      "abstract_inverted_index,authorships,primary_location,"
                      "referenced_works,open_access",
        }
        if config.OPENALEX_API_KEY:            # key = uninterrupted access when overloaded
            params["api_key"] = config.OPENALEX_API_KEY

        r = requests.get(OPENALEX, params=params, timeout=30)
        if r.status_code == 503:               # overloaded: one polite retry, then stop
            print("    (OpenAlex overloaded; waiting 5s and retrying once...)")
            time.sleep(5)
            r = requests.get(OPENALEX, params=params, timeout=30)
            if r.status_code == 503:
                if not results:
                    reason = "without API key" if not config.OPENALEX_API_KEY else "even with API key"
                    raise RuntimeError(
                        f"OpenAlex still overloaded ({reason}). Try again later"
                        + ("" if config.OPENALEX_API_KEY else " or add a free API key (.openalex_key)."))
                break                          # keep what we already have
        r.raise_for_status()
        data = r.json()
        page = data.get("results", [])
        if not page:
            break
        for w in page:
            results.append({
                "id": w.get("id"),
                "doi": w.get("doi"),
                "title": w.get("title") or "",
                "year": w.get("publication_year"),
                "citations": w.get("cited_by_count", 0),
                "authors": _authors(w.get("authorships")),
                "abstract": _reconstruct_abstract(w.get("abstract_inverted_index")),
                "source": (((w.get("primary_location") or {}).get("source")) or {}).get("display_name") or "",
                "references": w.get("referenced_works") or [],
                "is_oa": bool((w.get("open_access") or {}).get("is_oa", False)),
                "oa_url": (w.get("open_access") or {}).get("oa_url") or "",
                "query": query,
                "origin": "openalex",
            })
        cursor = (data.get("meta") or {}).get("next_cursor")
        time.sleep(0.2)                        # courtesy between pages
    return results


def pull_papers(topic: str | None = None,
                terms: list[str] = None,
                per_term: int = 25) -> pd.DataFrame:
    """Loop over all terms, merge, drop duplicates and save. Returns the table.

    NOTE: topic/terms default to config AT CALL TIME (not import time), so
    config.set_topic() from Phase 6.1 is respected.
    """
    topic = topic or config.TOPIC
    terms = terms or config.SEARCH_TERMS
    rows = []
    # Share OpenAlex's time budget across its terms (each paginates to exhaustion or
    # its slice), so no single term eats the whole allowance.
    oa_term_budget = config.PULL_TIME_BUDGET / max(len(terms), 1)
    for term in terms:
        print(f"  searching: {term!r} ...")
        try:
            found = search_openalex(term, time_budget=oa_term_budget)
            rows += found
            print(f"    openalex: {len(found)} results")
        except Exception as e:
            print(f"    (warning) term '{term}' failed: {e}")
        time.sleep(0.3)                        # courtesy: don't hammer the API

    df = pd.DataFrame(rows)
    if df.empty:
        print("No papers returned. Internet down? Terms too obscure?")
        return df

    # Drop duplicates: the same paper can show up in several searches.
    df = df.drop_duplicates(subset="id").reset_index(drop=True)

    # Phase 5.6 - extra connectors (Semantic Scholar, Crossref, Scopus with the user's key).
    # OpenAlex stays the base record (richest: abstracts + references); extras only ADD
    # papers we did not have, deduplicated by DOI then title.
    if config.USE_EXTRA_SOURCES:
        from . import sources
        extra = sources.pull_extra_sources(terms, per_term=per_term)
        df, stats = sources.merge_dedup(df, extra)
        print(f"  extra sources: +{stats['added']} new papers "
              f"({stats['dupes']} already known from OpenAlex)")
        # Discovery from one source, content from another: DOIs that arrived without an
        # abstract (Scopus always, Crossref often) get it filled from OpenAlex in batch.
        df = sources.enrich_missing_abstracts(df)

    # Drop papers with no abstract (useless for content embeddings).
    df = df[df["abstract"].str.len() > 20].reset_index(drop=True)

    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    out_path = config.DATA_PROCESSED / "papers.parquet"
    df.to_parquet(out_path, index=False)
    print(f"\nSaved {len(df)} unique papers with abstract to:\n  {out_path}")
    return df


if __name__ == "__main__":
    print(f"Topic: {config.TOPIC}")
    if config.OPENALEX_API_KEY:
        print("API key: found (uninterrupted access)\n")
    else:
        print("API key: NOT found - using anonymous access (may fail if OpenAlex is overloaded)\n")
    pull_papers()
