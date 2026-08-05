"""
export_obsidian.py - turn a measured topic map into a linked markdown vault.

WHY THIS EXISTS
Froth finishes its work and leaves it in 3_Resultados/. The map says what exists and what
to read, but the reader's own thinking about what they read has nowhere to accumulate, and
none of what Froth measured reaches the tools where the deep reading actually happens.
This module closes that last stretch: it writes a folder of plain markdown notes wired
together with [[wikilinks]], which Obsidian reads as a graph and which any text editor reads
as ordinary files. Nothing here needs Obsidian installed to be worth having.

WHAT IT DOES NOT DO
It does not write one note per paper. On a 2,243-paper corpus that would bury a vault under
2,243 files and make the graph unreadable. The export is CURATED: one note per subtopic, one
note per must-read (the h-index cut, note 32), a gaps note and a master index. Papers that
are not promoted to their own note are still listed inside their subtopic's note, so nothing
is lost, only ranked.

It also never writes to my_space.json. The logbook is the user's; this module reads it.
"""
from __future__ import annotations

import re
import shutil
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, my_space
from .review import _bibtex_key, _h_index, cluster_subtitles

# Windows forbids these in filenames, and Obsidian additionally treats [ ] # ^ | as link
# syntax, so they cannot appear in a note name that something else has to [[link]] to.
_UNSAFE = re.compile(r'[\\/:*?"<>|\[\]#^]')
MAX_STEM = 80                      # keep paths short: Windows still has a 260-char ceiling


def load_aligned(slug: str) -> tuple[pd.DataFrame, np.ndarray]:
    """(topic map, vectors) for one topic, with row i of one matching row i of the other.

    They are NOT aligned on disk: vectors.npy holds one row per HARVESTED paper (4,937 on
    the Beauvoir corpus) while topic_map.parquet holds only the papers that passed the
    relevance gate (2,243). The gate mask is what lines them up, exactly as the app does it
    in app.py:342-347. Getting this wrong does not raise: it silently attaches the wrong
    vector to every paper, so it is worth one shared function instead of two eyeballed
    copies.

    Uses the clustering saved by the pipeline. The app can re-cluster live with its
    granularity slider; an export takes the map as it stands on disk.
    """
    paths = config.paths_for(slug)
    df = pd.read_parquet(paths["processed"] / "papers.parquet")
    vectors = np.load(paths["embeddings"] / "vectors.npy")
    tm = pd.read_parquet(paths["processed"] / "topic_map.parquet")
    if len(vectors) != len(df):
        raise ValueError(f"{slug}: {len(vectors)} vectors vs {len(df)} harvested papers")
    mask = (df["relevance"] >= config.RELEVANCE_THRESHOLD).to_numpy()
    v = vectors[mask]
    if len(v) != len(tm):
        raise ValueError(f"{slug}: relevance gate leaves {len(v)} vectors but the topic "
                         f"map has {len(tm)} rows")
    return tm.reset_index(drop=True), v


def _safe_stem(text: str, fallback: str = "untitled") -> str:
    """A filename that Windows and Obsidian both accept, from any paper title.

    The file NAME is sanitised; the title INSIDE the note is written character for
    character (project rule: the source data is never silently corrected).
    """
    stem = _UNSAFE.sub(" ", str(text or ""))
    stem = " ".join(stem.split())[:MAX_STEM].strip().rstrip(".")
    return stem or fallback


_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def _yaml_value(text: str) -> str:
    """Quote a scalar for YAML frontmatter without mangling what it says.

    Control characters are stripped, and only here. Two journal names in the Beauvoir
    corpus arrive from the source database as mojibake ('\\x98The \\x9cNephron journals'),
    and a raw C1 byte makes the whole frontmatter block unparseable, which silently costs
    the note every property a query could filter on. This is metadata, not the quoted
    source: the title and abstract in the note body stay character for character.
    """
    clean = _CTRL.sub("", str(text or ""))
    return '"' + clean.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _int(value, default: int = 0) -> int:
    """Year and citation cells are empty in part of the corpus (see graph.py)."""
    try:
        return default if pd.isna(value) else int(value)
    except (TypeError, ValueError):
        return default


def _neighbours(tm: pd.DataFrame, vectors: np.ndarray, top: int = 3
                ) -> dict[int, list[tuple[int, float]]]:
    """The `top` most semantically similar subtopics of each subtopic.

    graph.build_topic_graph() answers this too, but it also counts cross-citations by
    walking every paper's reference list, which costs minutes on a corpus this size. The
    export only needs "which subtopics are neighbours", and cosine between cluster
    centroids answers that from a 96x96 matrix in milliseconds. The expensive citation
    counting stays where it earns its keep: the gaps analysis.
    """
    ids = sorted(int(c) for c in tm["cluster"].unique() if c != -1)
    if len(ids) < 2:
        return {c: [] for c in ids}
    norm = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    col = tm["cluster"].to_numpy()
    cents = np.vstack([norm[col == c].mean(axis=0) for c in ids])
    cents /= np.linalg.norm(cents, axis=1, keepdims=True)
    sim = cents @ cents.T
    np.fill_diagonal(sim, -1.0)                      # a subtopic is not its own neighbour
    out = {}
    for i, c in enumerate(ids):
        order = np.argsort(sim[i])[::-1][:top]
        out[c] = [(ids[j], float(sim[i][j])) for j in order]
    return out


def _has_title(row) -> bool:
    t = str(row.get("title", "") or "").strip()
    return bool(t) and t.lower() != "nan"


def _safe_key(row) -> str:
    """A citation key for a paper, tolerating records the source left without a title.

    Six records in the thesis corpus have an empty title (one of them with 105 citations,
    so it is a genuine must-read). review._bibtex_key crashes on those: it does
    `str(title).split()[0]` and an empty string has no first word. The title is NOT invented
    to paper over it - the note says the source has none and identifies the paper by DOI.
    """
    if _has_title(row):
        return _bibtex_key(row.get("authors", ""), _int(row.get("year")), row["title"])
    doi = str(row.get("doi", "") or "").rstrip("/").split("/")[-1]
    return f"untitled-{_safe_stem(doi, str(row.get('id', 'record')))}"


def _display_title(row) -> str:
    """What to show as the note's heading. No word is changed; absent titles are said.

    Runs of whitespace are collapsed to one space. Four titles in the thesis corpus arrive
    with newlines inside them, leaked markup from the source record ('Complexes of
    niobium(\\n <scp>IV</scp>\\n )'), and a markdown heading physically cannot span lines:
    the second half would silently become body text. Collapsing invisible whitespace is not
    correcting the data, and every word stays exactly as the source has it.
    """
    if _has_title(row):
        return " ".join(str(row["title"]).split())
    doi = str(row.get("doi", "") or "")
    return f"[Untitled record: the source database has no title] {doi}".strip()


def _mean_cut(cits: list[int]) -> int:
    """Head/tail breaks, ONE pass: how many papers sit above the subtopic's mean citations.

    In a long-tailed distribution the mean sits above most values, so what is left above it
    is the heavy head. This is the fallback note 32 specifies, and it is deliberately a
    SINGLE cut. An earlier version of this file repeated it up to six times, which sounds
    stricter and is in fact broken: in the 340-paper subtopic one paper with 4,250 citations
    drags the mean so hard that repeating collapses the head to a single paper. Measured
    across the thesis corpus, repeating left 20 of the 29 subtopics with 30+ papers with two
    must-reads or fewer. One pass never does that.
    """
    if not cits:
        return 0
    mean = sum(cits) / len(cits)
    return max(1, sum(1 for c in cits if c > mean))


def _must_reads(part: pd.DataFrame) -> pd.DataFrame:
    """The reading list of one subtopic, by the rule note 32 documents.

    The h-index decides: the largest h such that h papers have at least h citations each.
    The subtopic sets its own bar, so a mature one demands hundreds of citations and a young
    one settles for a handful, with no fixed number anywhere.

    It has one failure mode, and note 32 already named it: on subtopics whose citations are
    flat the h-index degenerates and would mark almost everything as a must-read. The note's
    own test for that is h > half the subtopic, and its fallback is a single cut at the mean.
    That fallback had never actually been implemented; it is implemented here.

    Measured on the thesis corpus: 893 must-reads over 104 subtopics, median 8, and NO
    subtopic of 30+ papers is left with two or fewer.
    """
    cits = [_int(c) for c in part["citations"]]
    n = len(part)
    h = _h_index(cits)
    if not h:
        return part.head(0)
    keep = h if h <= n / 2 else _mean_cut(cits)
    return part.assign(_c=cits).sort_values("_c", ascending=False).head(keep)


def _stage_of(logbook: list[dict], title: str, doi: str) -> tuple[str, str]:
    """(stage, note) from the user's My space logbook, empty if the paper is not in it."""
    for e in logbook:
        if (doi and str(e.get("doi", "")) == str(doi)) or e.get("title") == title:
            return str(e.get("stage", "")), str(e.get("note", ""))
    return "", ""


def _paper_note(row, subtopic_link: str, stage: str, user_note: str) -> str:
    """One must-read as a note: queryable frontmatter, verbatim abstract, link home."""
    title = _display_title(row)
    doi = str(row.get("doi", "") or "")
    fm = ["---",
          f"title: {_yaml_value(title)}",
          f"year: {_int(row.get('year'))}",
          f"citations: {_int(row.get('citations'))}",
          f"doi: {_yaml_value(doi)}",
          f"authors: {_yaml_value(row.get('authors', ''))}",
          f"journal: {_yaml_value(row.get('source', ''))}",
          f"subtopic: {_yaml_value(str(row.get('label', '')))}",
          "must_read: true"]
    if stage:
        fm.append(f"stage: {_yaml_value(stage)}")
    fm += ["tags: [froth, paper]", "---", ""]

    body = [f"# {title}", ""]
    body.append(f"Part of {subtopic_link}.")
    body.append("")
    if doi:
        body.append(f"- DOI: [{doi}]({doi})")
    oa = str(row.get("oa_url", "") or "")
    if oa and oa.lower() != "nan":
        body.append(f"- Open access PDF: [{oa}]({oa})")
    body.append("")
    if stage:
        body.append(f"**Your reading stage:** {stage}")
        if user_note:
            body.append("")
            body.append(f"> {user_note}")
        body.append("")
    abstract = str(row.get("abstract", "") or "").strip()
    if abstract:
        body += ["## Abstract (quoted from the source)", "", abstract, ""]
    body += ["## My notes", "", ""]
    return "\n".join(fm + body)


def _subtopic_note(label: str, title: str, sentence: str, part: pd.DataFrame,
                   must: pd.DataFrame, paper_links: dict[str, str],
                   neighbour_links: list[str]) -> str:
    """One subtopic as a note: what it is, what to read, what it borders on."""
    years = [_int(y) for y in part["year"] if _int(y)]
    fm = ["---",
          f"title: {_yaml_value(title)}",
          f"papers: {len(part)}",
          f"citations: {sum(_int(c) for c in part['citations'])}",
          "tags: [froth, subtopic]", "---", ""]

    body = [f"# {title}", ""]
    if sentence:
        body += [f"> {sentence}", "",
                 "_The sentence above is quoted verbatim from an abstract in this "
                 "subtopic: it is the one closest to the subtopic's centre of meaning._", ""]
    span = f"{min(years)} to {max(years)}" if years else "unknown"
    body.append(f"**{len(part)} papers**, published {span}. "
                f"Keywords: {label}.")
    body.append("")

    if len(must) >= len(part) and len(part):
        # Both cuts kept everything, which happens on small subtopics where the citations
        # are flat. Calling that a must-read list would pretend a selection was made.
        body += ["## Read it whole", "",
                 f"_This subtopic has only {len(part)} papers and their citation counts do "
                 "not separate a head from a tail, so there is nothing to rank: read them "
                 "all._", ""]
        for _, r in part.assign(_c=[_int(c) for c in part["citations"]]).sort_values(
                "_c", ascending=False).iterrows():
            link = paper_links.get(str(r["id"]))
            shown = f"[[{link}]]" if link else _display_title(r)
            body.append(f"- {shown} ({_int(r.get('year'))}, "
                        f"{_int(r.get('citations'))} citations)")
        body.append("")
        body += ["## My notes", "", ""]
        return "\n".join(fm + body)

    if len(must):
        body += ["## Must-reads", "",
                 f"_Chosen by this subtopic's own citation distribution, not by a fixed "
                 f"top-N: {len(must)} of {len(part)} papers clear the bar._", ""]
        for _, r in must.iterrows():
            link = paper_links.get(str(r["id"]))
            shown = f"[[{link}]]" if link else _display_title(r)
            body.append(f"- {shown} ({_int(r.get('year'))}, "
                        f"{_int(r.get('citations'))} citations)")
        body.append("")

    rest = part[~part["title"].isin(must["title"])] if len(must) else part
    if len(rest):
        body += ["## The rest of the subtopic", "",
                 f"_{len(rest)} more papers, most cited first. They have no note of their "
                 "own on purpose: promoting every paper would bury the vault._", ""]
        rest = rest.assign(_c=[_int(c) for c in rest["citations"]])
        for _, r in rest.sort_values("_c", ascending=False).iterrows():
            doi = str(r.get("doi", "") or "")
            tail = f" [DOI]({doi})" if doi and doi.lower() != "nan" else ""
            body.append(f"- {_display_title(r)} ({_int(r.get('year'))}, "
                        f"{_int(r.get('citations'))} cit.){tail}")
        body.append("")

    if neighbour_links:
        body += ["## Borders on", "",
                 "_Nearest subtopics by meaning. A high similarity with few shared "
                 "citations is where the gaps live (note 21)._", ""]
        body += neighbour_links
        body.append("")

    body += ["## My notes", "", ""]
    return "\n".join(fm + body)


def export_vault(tm: pd.DataFrame, vectors: np.ndarray, slug: str,
                 topic_title: str = "", out_dir: Path | None = None,
                 subtitles: dict[int, tuple[str, str]] | None = None) -> dict:
    """Write the curated vault. Returns a report dict of what was produced.

    Never overwrites in place: if the destination exists it is moved aside with a dated
    suffix first, because a vault may already hold notes the user wrote by hand.

    `subtitles` ({cluster: (title, centroid sentence)}) lets a caller hand over titles it
    already has. The app does: its subtitled_state() computed and cached them, and
    recomputing embeds every candidate keyphrase again, which is 50 of the 52 seconds this
    function otherwise costs. Left None, they are computed here.
    """
    paths = config.paths_for(slug)
    root = Path(out_dir) if out_dir else paths["deliverables"] / "obsidian_vault"
    if root.exists():
        backup = root.with_name(f"{root.name}_prev_{date.today().isoformat()}")
        if backup.exists():
            shutil.rmtree(backup)
        root.rename(backup)
    (root / "subtopics").mkdir(parents=True, exist_ok=True)
    (root / "papers").mkdir(parents=True, exist_ok=True)

    tm = tm.reset_index(drop=True)
    if subtitles is None:
        subtitles = cluster_subtitles(tm, vectors)
    neighbours = _neighbours(tm, vectors)
    logbook = my_space.load()
    clusters = sorted(int(c) for c in tm["cluster"].unique() if c != -1)

    # Pass 1: decide every note's filename BEFORE writing anything, so a [[wikilink]] can
    # never point at a name that does not exist. Broken links are the failure mode that
    # makes a generated vault feel like junk.
    sub_stem: dict[int, str] = {}
    used: set[str] = set()
    for c in clusters:
        title = subtitles.get(c, ("", ""))[0] or str(
            tm[tm["cluster"] == c]["label"].iloc[0])
        stem = f"{c:02d} {_safe_stem(title, f'subtopic {c}')}"
        while stem in used:
            stem += "_"
        used.add(stem)
        sub_stem[c] = stem

    must_by_cluster: dict[int, pd.DataFrame] = {}
    # Keyed by paper id, not title: the same paper can be a must-read in two subtopics
    # (one is, in this corpus), and a title-keyed map silently loses one of the two notes.
    paper_stem: dict[str, str] = {}
    for c in clusters:
        must = _must_reads(tm[tm["cluster"] == c])
        must_by_cluster[c] = must
        for _, r in must.iterrows():
            pid = str(r["id"])
            if pid in paper_stem:
                continue
            key = _safe_key(r)
            stem = _safe_stem(f"{key} {_display_title(r)[:60]}", key)
            while stem in used:
                stem += "_"
            used.add(stem)
            paper_stem[pid] = stem

    # Pass 2: write.
    n_papers_written = 0
    for c in clusters:
        part = tm[tm["cluster"] == c]
        label = str(part["label"].iloc[0])
        title, sentence = subtitles.get(c, (label, ""))
        must = must_by_cluster[c]
        for _, r in must.iterrows():
            stage, note = _stage_of(logbook, str(r["title"]), str(r.get("doi", "") or ""))
            text = _paper_note(r, f"[[{sub_stem[c]}]]", stage, note)
            (root / "papers" / f"{paper_stem[str(r['id'])]}.md").write_text(
                text, encoding="utf-8")
            n_papers_written += 1
        nb = [f"- [[{sub_stem[n]}]] (similarity {s:.2f})"
              for n, s in neighbours.get(c, []) if n in sub_stem]
        (root / "subtopics" / f"{sub_stem[c]}.md").write_text(
            _subtopic_note(label, title, sentence, part, must, paper_stem, nb),
            encoding="utf-8")

    # The gaps note reuses the table the pipeline already saved. It is NOT recomputed here:
    # find_gaps() walks every paper's reference list and costs minutes, and an export should
    # never silently launch a heavy analysis. No table yet = say so, do not fake it.
    gaps_file = paths["processed"] / "gaps.parquet"
    gaps_written = False
    if gaps_file.exists():
        gaps = pd.read_parquet(gaps_file)
        L = ["---", "tags: [froth, gaps]", "---", "", "# Research gaps", "",
             "_Candidates ranked from the measured map. A hole can be empty because nobody "
             "explored it or because there is nothing there: no algorithm tells a mine from "
             "a desert, so these are candidates with evidence, not conclusions (note 24)._",
             ""]
        for gtype, block in gaps.groupby("type"):
            L += [f"## {gtype}", ""]
            for _, r in block.head(8).iterrows():
                L.append(f"- **{r['where']}** - {r['evidence']} (score {r['score']})")
            L.append("")
        (root / "gaps.md").write_text("\n".join(L), encoding="utf-8")
        gaps_written = True

    # The review draft and its BibTeX are copied as they are: already traceable, and the
    # .bib is what makes this vault useful in Zotero even to someone who never opens Obsidian.
    copied = []
    for name in ("review_draft_v2.md", "review_draft_v2.bib"):
        src = paths["deliverables"] / name
        if src.exists():
            shutil.copy2(src, root / name)
            copied.append(name)

    index = ["---", "tags: [froth, index]", "---", "",
             f"# {topic_title or slug}", "",
             f"_Map exported from Froth on {date.today().isoformat()}: "
             f"{len(tm)} papers, {len(clusters)} subtopics, {n_papers_written} must-reads "
             "promoted to their own note._", "",
             "Every subtopic below is a note. Inside each one you get what it is about, "
             "which papers to read first, and which subtopics it borders on. Papers without "
             "their own note are listed inside their subtopic.", "", "## Subtopics", ""]
    for c in clusters:
        part = tm[tm["cluster"] == c]
        n_must = len(must_by_cluster[c])
        tail = ("read whole" if n_must >= len(part)
                else f"{n_must} must-read{'' if n_must == 1 else 's'}")
        index.append(f"- [[{sub_stem[c]}]] - {len(part)} papers, {tail}")
    index.append("")
    if gaps_written:
        index += ["## Analysis", "", "- [[gaps]]", ""]
    if copied:
        index += ["## Draft", ""]
        index += [f"- `{n}`" for n in copied]
        index.append("")
    (root / "_index.md").write_text("\n".join(index), encoding="utf-8")

    return {"root": root, "subtopics": len(clusters), "papers": n_papers_written,
            "gaps": gaps_written, "copied": copied,
            "notes": len(clusters) + n_papers_written + 1 + int(gaps_written)}
