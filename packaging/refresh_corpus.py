"""
refresh_corpus.py - Phase A resume + hardening (2026-07-14).

The first uncapped run FROZE 9h on one huge topic because run_topic caught crashes but not
HANGS, and topics run in series. This runner fixes that:
  - topics already on disk are read INLINE (cheap, no torch/GPU) -> the report stays complete
    and finished corpora are never re-harvested;
  - topics that still need work run in a CHILD PROCESS with a hard wall-clock timeout
    (config.TOPIC_TIMEOUT_S), so a wedged topic is killed and marked FAILED instead of
    freezing the whole batch.

Run (long, background):
    .venv\\Scripts\\python.exe packaging\\refresh_corpus.py
"""
import json
import subprocess
import sys
import time
from pathlib import Path

# Runnable as a plain script: python puts packaging/ (not the repo root) on sys.path,
# so froth would not be importable without this.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

# Import ONLY config (lightweight) - importing froth.batch drags in umap/scipy/torch,
# whose DLLs the corporate WDAC policy sometimes blocks (it killed this orchestrator once).
# The parent just reads CSVs and spawns children; heavy imports stay in the CHILD process,
# where a block turns into one FAILED row instead of a dead batch.
from froth import config

REPORT = config.ROOT / "2_Datos" / "batch_report.csv"
WDAC_HINTS = ("Control de aplicaciones", "DLL load failed")


def cohort_titles() -> list[str]:
    """Same as batch.cohort_titles, inlined so the parent never imports froth.batch."""
    df = pd.read_csv(config.ROOT / "2_Datos" / "cohort_thesis_titles.csv")
    df.columns = [c.strip() for c in df.columns]
    return [str(t).strip() for t in df["thesis title"].dropna() if str(t).strip()]


def _topic_map_path(slug: str):
    """Where a finished topic's map lives: its per-topic folder, or the flat default folder."""
    per_topic = config.ROOT / "2_Datos" / "topics" / slug / "processed" / "topic_map.parquet"
    if per_topic.exists():
        return per_topic
    flat = config.ROOT / "2_Datos" / "processed" / "topic_map.parquet"
    if slug == config.slugify(config.DEFAULT_TOPIC) and flat.exists():
        return flat
    return None


def _cached_row(title: str):
    """Read a finished topic's numbers straight from disk - no subprocess, no torch/GPU
    (which also dodges the corporate WDAC DLL block for topics that don't need to recompute)."""
    slug = config.slugify(title)
    tm_path = _topic_map_path(slug)
    if tm_path is None:
        return None
    tm = pd.read_parquet(tm_path)
    papers = tm_path.parent / "papers.parquet"
    df = pd.read_parquet(papers) if papers.exists() else tm
    relevant = (int((df["relevance"] >= config.RELEVANCE_THRESHOLD).sum())
                if "relevance" in df.columns else len(df))
    return {"slug": slug, "status": "cached", "error": "", "papers": len(df),
            "relevant": relevant, "clusters": int(tm["cluster"].max() + 1),
            "noise": int((tm["cluster"] == -1).sum()),
            "mcs": int(tm["mcs_used"].iloc[0]) if "mcs_used" in tm.columns else 0, "secs": 0}


def _failed_row(title: str, error: str, secs: int = 0):
    return {"slug": config.slugify(title), "status": "FAILED", "error": error[:140],
            "papers": 0, "relevant": 0, "clusters": 0, "noise": 0, "mcs": 0, "secs": secs}


def _run_one(title: str, extra: list[str] | None = None):
    """Run ONE topic in a child process with a hard wall-clock timeout."""
    t0 = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "froth.batch", "--one", title]
            + (extra or []),
            cwd=str(config.ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=config.TOPIC_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return _failed_row(title,
                           f"timed out after {config.TOPIC_TIMEOUT_S}s (killed by watchdog)",
                           config.TOPIC_TIMEOUT_S)
    for line in reversed(proc.stdout.splitlines()):
        if line.startswith("ROW_JSON:"):
            return json.loads(line[len("ROW_JSON:"):])
    tail = (proc.stderr or proc.stdout or "no output").strip()[-120:]
    return _failed_row(title, f"no row emitted; {tail}", round(time.time() - t0))


def _run_one_with_retry(title: str, extra: list[str] | None = None):
    """WDAC (Smart App Control) transiently blocks native DLLs on first touch; a fresh
    process a minute later usually loads fine. One retry, then honesty."""
    row = _run_one(title, extra)
    if row["status"] == "FAILED" and any(h in row["error"] for h in WDAC_HINTS):
        print(f"    (WDAC blocked a DLL; retrying once in 60s ...)")
        time.sleep(60)
        row = _run_one(title, extra)
    return row


def main() -> None:
    # --remap (Phase R): re-gate every topic from its saved harvest (pull+embed reused).
    # --reembed (Phase 8.8): re-embed with the CURRENT config.EMBEDDING_MODEL (production
    # model switch, e.g. base -> v1), then re-gate. Both always run (no cached shortcut).
    mode = ("--reembed" if "--reembed" in sys.argv
            else "--remap" if "--remap" in sys.argv else None)
    titles = cohort_titles()
    # Crash/sleep resume for mode runs: topics already 'remapped' in the incremental
    # report are DONE (each topic's vectors+gate+map are written atomically before its
    # row) - skip them, so an interrupted migration resumes instead of restarting.
    # The laptop slept through two runs before this existed.
    done_rows = []
    if mode and REPORT.exists():
        try:
            prev = pd.read_csv(REPORT).fillna("")
            done_rows = prev[prev["status"] == "remapped"].to_dict("records")
        except Exception:
            done_rows = []
    done_slugs = {r["slug"] for r in done_rows}
    print(f"{mode or 'resume'}: {len(titles)} topics "
          f"({config.TOPIC_TIMEOUT_S}s per-topic watchdog"
          + (f"; resuming past {len(done_slugs)} already done" if done_slugs else "")
          + ")\n")
    rows = list(done_rows)
    for i, title in enumerate(titles, 1):
        if mode and config.slugify(title) in done_slugs:
            continue
        if mode:
            row = _run_one_with_retry(title, [mode])
        else:
            row = _cached_row(title) or _run_one_with_retry(title)
        rows.append(row)
        pd.DataFrame(rows).to_csv(REPORT, index=False)      # crash-safe, incremental
        print(f"[{i:>2}/{len(titles)}] {row['status']:>6}  {row['papers']:>6} papers  "
              f"{row['secs']:>4}s  {row['slug'][:44]}  {row['error']}")
    total = sum(r["papers"] for r in rows)
    ok = sum(1 for r in rows if r["status"] in ("ok", "cached", "remapped"))
    print(f"\nDONE. {ok}/{len(rows)} topics OK. total papers {total}. report: {REPORT}")


if __name__ == "__main__":
    main()
