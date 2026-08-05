"""
my_space.py - the researcher's logbook (MVP, Batman's product section).

WHAT IT IS: a first-class section, like Network or the reading guide, that tracks the
REVIEW PROCESS itself: which papers you are reading, which you already summarized or
interpreted, which you discarded - so the user never keeps progress in a side spreadsheet.

Storage: a local JSON (2_Datos/my_space.json). It ships EMPTY with the public bundle
(personal data is excluded from packaging, same policy as API keys) and starts empty for
every new user.
"""
import json
import re
import time

from . import config

PATH = config.ROOT / "2_Datos" / "my_space.json"
STAGES = ["to read", "reading", "summarized", "interpreted", "discarded"]
DONE_STAGES = {"summarized", "interpreted", "discarded"}
# One colour per stage, defined here so the buttons and the sheet cannot drift apart.
# Cold blue for what has not started, amber while in hand, greens once it produced
# something, grey for what you decided against.
STAGE_COLORS = {"to read": "#6366f1", "reading": "#f59e0b", "summarized": "#14b8a6",
                "interpreted": "#22c55e", "discarded": "#71717a"}


def _entry_id(title: str, doi: str) -> str:
    if doi:
        return doi.strip().lower()
    return re.sub(r"\W+", "-", str(title).lower())[:80]


FIELDS = {"title": "", "year": 0, "doi": "", "topic_slug": "", "topic_title": "",
          "island": "", "citations": 0, "must_read": False, "stage": STAGES[0],
          "note": "", "added_at": ""}


def load() -> list[dict]:
    """Every record, with any field a record predates filled in. Records written by
    earlier versions of the logbook stay readable instead of crashing the view."""
    if not PATH.exists():
        return []
    try:
        entries = json.loads(PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [{**FIELDS, **e} for e in entries if isinstance(e, dict)]


def save(entries: list[dict]) -> None:
    PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=1),
                    encoding="utf-8")


def add(row, topic_slug: str, topic_title: str = "", island: str = "",
        must_read: bool = False, stage: str = STAGES[0]) -> bool:
    """File a paper (a topic-map row) as a logbook record. False if already filed.

    The record keeps WHERE the paper came from (topic and island) and whether it was a
    must-read of that island, so the sheet stays readable without going back to the map.
    """
    entries = load()
    eid = _entry_id(row.get("title", ""), str(row.get("doi", "") or ""))
    if any(e["id"] == eid for e in entries):
        return False
    entries.append({"id": eid,
                    "title": str(row.get("title", "")),
                    "year": int(row.get("year", 0) or 0),
                    "doi": str(row.get("doi", "") or ""),
                    "citations": int(row.get("citations", 0) or 0),
                    "topic_slug": topic_slug,
                    "topic_title": topic_title,
                    "island": island,
                    "must_read": bool(must_read),
                    "stage": stage if stage in STAGES else STAGES[0],
                    "note": "",
                    "added_at": time.strftime("%Y-%m-%d")})
    save(entries)
    return True


def find(row) -> dict | None:
    """The record already filed for this paper, or None.

    Uses the SAME id rule add() uses, on purpose: a caller that wants to show "already in
    your logbook" must agree with the function that decides whether to file. Re-deriving
    the rule at the call site is how the button and the sheet end up disagreeing.
    """
    eid = _entry_id(row.get("title", ""), str(row.get("doi", "") or ""))
    return next((e for e in load() if e["id"] == eid), None)


def update(eid: str, stage: str | None = None, note: str | None = None) -> None:
    entries = load()
    for e in entries:
        if e["id"] == eid:
            if stage is not None:
                e["stage"] = stage
            if note is not None:
                e["note"] = note
    save(entries)


def remove(eid: str) -> None:
    save([e for e in load() if e["id"] != eid])


def remove_topic(topic_slug: str) -> int:
    """Drop every record filed under ONE topic and return how many were dropped.

    Scoped on purpose: the logbook is a single file spanning every topic, and its whole
    value is that it survives sessions. Clearing one topic must leave the others exactly
    as they were, so this filters rather than truncating the file.
    """
    entries = load()
    keep = [e for e in entries if e["topic_slug"] != topic_slug]
    save(keep)
    return len(entries) - len(keep)
