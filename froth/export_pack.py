"""
export_pack.py - a curated source pack to hand to NotebookLM (or any deep-reading tool).

WHY THE UPLOAD IS NOT AUTOMATED, AND WILL NOT BE
NotebookLM has no official API. There is an unofficial library (notebooklm-py, June 2026)
that reverse-engineers the internal endpoints its web frontend calls, and it works. It is
still not used here, for two reasons that do not expire:

  1. Google's terms forbid accessing the service "through the use of any automated means
     (such as robots, spiders or scrapers)". Driving those endpoints from a script is
     exactly that, and the account carrying the risk is the user's, most likely their
     institutional one.
  2. Reverse-engineered endpoints break whenever Google changes them, silently and at the
     worst moment.

This is the same call the project already made about ResearchGate. So Froth does the part
no one else can do - decide WHICH papers out of thousands are worth deep reading, and say
why - and the user drags the result in. Two clicks, no legal grey area, nothing to maintain.

WHAT MAKES THE PACK WORTH ANYTHING
Not the papers: anyone can paste 50 PDFs. It is the prompts, which are written from the
measured map. "Summarise this" is what you ask when you know nothing about your corpus.
"Subtopics A and B share 0.69 similarity but only one cross-citation, what would explain
that silence?" is what you ask when a tool measured it for you first.
"""
from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .export_obsidian import (_display_title, _int, _must_reads,  # noqa: F401
                              load_aligned)

SOURCES_MD = "sources.md"
LINKS_TXT = "open_access_links.txt"
PROMPTS_MD = "prompts.md"
README_MD = "READ_ME_FIRST.md"


def _paper_block(row, n: int) -> list[str]:
    """One paper as a citable block. The abstract is quoted, never rewritten."""
    doi = str(row.get("doi", "") or "")
    # Same title handling as the vault: newlines collapsed so a heading cannot
    # split in two, and records the source left untitled say so instead of
    # rendering as an empty line.
    out = [f"### [{n}] {_display_title(row)}", ""]
    meta = [f"**Year:** {_int(row.get('year'))}",
            f"**Citations:** {_int(row.get('citations'))}"]
    authors = str(row.get("authors", "") or "").strip()
    if authors:
        meta.append(f"**Authors:** {authors}")
    journal = str(row.get("source", "") or "").strip()
    if journal and journal.lower() != "nan":
        meta.append(f"**Journal:** {journal}")
    if doi and doi.lower() != "nan":
        meta.append(f"**DOI:** {doi}")
    out += [" · ".join(meta), ""]
    abstract = str(row.get("abstract", "") or "").strip()
    out += [abstract if abstract else "_No abstract available for this record._", ""]
    return out


def _prompts(tm: pd.DataFrame, subtitles: dict[int, tuple[str, str]],
             gaps: pd.DataFrame | None) -> list[str]:
    """Questions built from what the map MEASURED, not generic reading prompts.

    Every number quoted here comes from the corpus, so the answers can be checked against
    it. Where a measurement is missing the question is simply not written: a prompt citing
    a made-up figure would be worse than no prompt.
    """
    L = ["# Prompts worth asking", "",
         "_Generic prompts get generic answers. These name subtopics and quote numbers "
         "that Froth measured on YOUR corpus, so the answers can be checked against it. "
         "Paste them one at a time._", ""]

    sizes = (tm[tm["cluster"] != -1].groupby("cluster").size()
             .sort_values(ascending=False))
    named = [(int(c), subtitles.get(int(c), ("", ""))[0] or str(
        tm[tm["cluster"] == c]["label"].iloc[0]), int(n)) for c, n in sizes.items()]

    # find_gaps names subtopics with the raw c-TF-IDF keywords saved in the map, so a gap
    # prompt reads "jiningian, qiaomaishan, baiyunxian" where the rest of this file says
    # "Coal flotation process". Nobody can paste that into NotebookLM and expect an answer,
    # so the raw labels are swapped for the readable titles the map already carries.
    readable = {str(tm[tm["cluster"] == c]["label"].iloc[0]): t
                for c, t, _ in named if t}

    def humanise(text: str) -> str:
        out = str(text)
        for raw, nice in sorted(readable.items(), key=lambda kv: -len(kv[0])):
            out = out.replace(raw, nice)
        return out

    # A counter, not hardcoded numbers: whole sections are skipped when the measurement
    # behind them is missing, and a list that jumps from 2 to 6 looks like a bug.
    count = 0

    def ask(text: str) -> None:
        nonlocal count
        count += 1
        L.extend([f"{count}. {text}", ""])

    L += ["## The shape of the field", ""]
    if len(named) >= 3:
        top = ", ".join(f'"{t}" ({n} papers)' for _, t, n in named[:3])
        ask(f"This corpus splits into {len(named)} subtopics. The three largest are {top}. "
            "What question is each of them really trying to answer, and where do they "
            "disagree?")
    if len(named) >= 5:
        small = ", ".join(f'"{t}" ({n})' for _, t, n in named[-3:])
        ask(f"The smallest subtopics here are {small}. Are these genuinely emerging areas, "
            "or fragments of the larger ones? Use the sources to argue it.")

    L += ["## The gaps the map measured", ""]
    if gaps is not None and len(gaps):
        silos = gaps[gaps["type"] == "silo"]
        # A bare "similarity 0.48" reads as low to anyone who has not seen the rest of the
        # distribution. On this corpus the median pair sits at 0.23 and the maximum at 0.54,
        # so 0.48 is in fact in the top decile. Say where the number falls, or the prompt
        # undersells its own evidence.
        sims = silos["evidence"].str.extract(r"similarity ([0-9.]+)")[0].astype(float)
        for i, (_, r) in enumerate(silos.head(3).iterrows()):
            here = sims.iloc[i] if i < len(sims) else None
            rank = ""
            if here is not None and len(sims) > 5 and not pd.isna(here):
                pct = float((sims < here).mean()) * 100
                rank = (f" That similarity is higher than {pct:.0f}% of all subtopic pairs "
                        f"in this corpus, where the median pair sits at {sims.median():.2f}.")
            ask(f"{r['evidence']}, between {humanise(r['where'])}.{rank} Two literatures studying "
                "closely related things while barely citing each other. What would explain "
                "that silence, and what would a paper bridging them have to show?")
        for _, r in gaps[gaps["type"].str.startswith("scarce")].head(1).iterrows():
            ask(f"{humanise(r['where'])}: {r['evidence']}. Which of the sources sit on that boundary, "
                "and what stops there being more of them?")
    else:
        L += ["_No gap table was available when this pack was built, so no gap prompts were "
              "written rather than inventing them. Open the Review tab once to compute "
              "them, then export again._", ""]

    years = [_int(y) for y in tm["year"] if _int(y)]
    if years:
        recent = int(sum(1 for y in years if y >= 2024))
        L += ["## Time", ""]
        ask(f"{recent} of {len(years)} papers here are from 2024 or later. Compare what the "
            "recent work assumes with what the older work assumed. What changed, and what "
            "quietly stayed the same?")

    L += ["## Reading your own corpus critically", ""]
    ask("Which claims in these sources rest on a single study that everyone else cites, "
        "rather than on independent replication?")
    ask("If you had to argue that this field's dominant method is the wrong one, which of "
        "these sources would you use, and what would still be missing from your case?")
    return L


def export_pack(tm: pd.DataFrame, vectors: np.ndarray, slug: str, topic_title: str = "",
                out_dir: Path | None = None,
                subtitles: dict[int, tuple[str, str]] | None = None) -> dict:
    """Write the pack. Returns a report of what was produced.

    The curated set is the same one the vault promotes to its own note: the more selective
    of each subtopic's h-index and head/tail cuts. That selection is the product; sending
    everything would just move the reader's problem somewhere else.
    """
    paths = config.paths_for(slug)
    root = Path(out_dir) if out_dir else paths["deliverables"] / "notebooklm_pack"
    if root.exists():
        backup = root.with_name(f"{root.name}_prev_{date.today().isoformat()}")
        if backup.exists():
            shutil.rmtree(backup)
        root.rename(backup)
    root.mkdir(parents=True, exist_ok=True)

    tm = tm.reset_index(drop=True)
    if subtitles is None:
        from .review import cluster_subtitles
        subtitles = cluster_subtitles(tm, vectors)
    clusters = sorted(int(c) for c in tm["cluster"].unique() if c != -1)

    L = [f"# {topic_title or slug}: curated sources", "",
         f"_{len(tm)} papers were mapped by meaning; the ones below are the selection worth "
         "deep reading, grouped by subtopic. Each subtopic's cut comes from its own citation "
         "distribution, not from a fixed top-N. Abstracts are quoted verbatim from the "
         f"source records, each with its DOI. Built {date.today().isoformat()}._", ""]
    n, n_papers, per_sub = 0, 0, []
    for c in clusters:
        part = tm[tm["cluster"] == c]
        must = _must_reads(part)
        if not len(must):
            continue
        title = subtitles.get(c, ("", ""))[0] or str(part["label"].iloc[0])
        sentence = subtitles.get(c, ("", ""))[1]
        L += [f"## {title}", ""]
        if sentence:
            L += [f"> {sentence}", ""]
        L += [f"_{len(must)} of {len(part)} papers in this subtopic._", ""]
        for _, r in must.assign(_c=[_int(x) for x in must["citations"]]).sort_values(
                "_c", ascending=False).iterrows():
            n += 1
            L += _paper_block(r, n)
        n_papers += len(must)
        per_sub.append((title, len(must)))
    (root / SOURCES_MD).write_text("\n".join(L), encoding="utf-8")

    # Open access links, so the reader can add the FULL TEXTS as sources. That matters:
    # everything above is abstracts, and an abstract-only pack can only support
    # abstract-deep answers.
    oa = []
    for c in clusters:
        for _, r in _must_reads(tm[tm["cluster"] == c]).iterrows():
            url = str(r.get("oa_url", "") or "")
            if url and url.lower() != "nan" and url.startswith("http"):
                oa.append(url)
    oa = list(dict.fromkeys(oa))
    (root / LINKS_TXT).write_text("\n".join(oa) + ("\n" if oa else ""), encoding="utf-8")

    gaps_file = paths["processed"] / "gaps.parquet"
    gaps = pd.read_parquet(gaps_file) if gaps_file.exists() else None
    (root / PROMPTS_MD).write_text("\n".join(_prompts(tm, subtitles, gaps)),
                                   encoding="utf-8")

    readme = [f"# How to use this pack", "",
              f"Froth mapped {len(tm)} papers and picked the {n_papers} worth reading "
              f"closely, across {len(per_sub)} subtopics.", "",
              "## Three steps", "",
              "1. Open NotebookLM (notebooklm.google.com) and create a new notebook.",
              f"2. Upload `{SOURCES_MD}`. It counts as ONE source, so it leaves room for "
              "whatever else you want to add.",
              f"3. Open `{PROMPTS_MD}` and paste the questions one at a time.", "",
              f"`{LINKS_TXT}` holds {len(oa)} links to freely available full texts. Adding "
              "some of them is worth it: the pack itself carries abstracts, and abstracts "
              "only support abstract-deep answers.", "",
              "## Why you upload it yourself", "",
              "There is no official NotebookLM API, and Google's terms forbid reaching the "
              "service through automated means. Automating the upload would put your Google "
              "account at risk to save you two clicks, and it would break the day Google "
              "changes an internal endpoint. So Froth does the part that actually needs "
              "doing, deciding which papers matter and why, and stops there.", "",
              "## What is in each file", "",
              f"- `{SOURCES_MD}`: the curated papers, grouped by subtopic, abstracts quoted "
              "verbatim with DOIs.",
              f"- `{PROMPTS_MD}`: questions written from what the map measured on this "
              "corpus, numbers included.",
              f"- `{LINKS_TXT}`: open access URLs, one per line.", ""]
    (root / README_MD).write_text("\n".join(readme), encoding="utf-8")

    return {"root": root, "papers": n_papers, "subtopics": len(per_sub),
            "oa_links": len(oa), "gaps": gaps is not None,
            "words": len(" ".join(L).split())}
