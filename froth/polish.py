"""
polish.py - PHASE 7.6: OPTIONAL local-LLM polish of the extractive draft.

WHAT IT DOES: asks a local Ollama model to rewrite each section's narrative
paragraph into smoother prose - then VERIFIES the result before accepting it:
every citation [n] must survive exactly, and the length must stay in a sane
band. Any section that fails verification silently keeps its extractive
original. The draft can only get smoother, never less truthful.

WHY LOCAL: free, private, offline - and a differentiator (competitors depend
on OpenAI APIs). Requires Ollama running (https://ollama.com); see
docs/OLLAMA_SETUP.md. Everything here soft-fails when it is not.
"""

import json
import re
import urllib.request

OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1:8b"

_PROMPT = """You are polishing ONE section of a scientific literature review.
Rewrite the sentences below into a single smoother, connected paragraph.

STRICT RULES:
- Keep every citation marker like [12] or [3]† exactly once, attached to the
  claim it supports. Do not invent, renumber, drop or merge citations.
- Do not add any fact, number, mineral, method or claim that is not already
  in the text. Do not remove any claim.
- Keep the technical terms exactly as written.
- Output ONLY the rewritten paragraph, no preamble, no notes.

Text:
{body}
"""


def available_models(timeout: float = 1.5) -> list[str]:
    """Names of the models the local Ollama server offers ([] when it is down)."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def _generate(prompt: str, model: str, timeout: float = 180) -> str:
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False,
                          "options": {"temperature": 0.2}}).encode("utf-8")
    req = urllib.request.Request(f"{OLLAMA_URL}/api/generate", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8")).get("response", "").strip()


def _citations(text: str) -> list[str]:
    return sorted(re.findall(r"\[(\d+)\]", text))


def _verified(original: str, rewritten: str) -> bool:
    """The polish gate: same citations (each exactly once), sane length."""
    if not rewritten:
        return False
    if _citations(rewritten) != _citations(original):
        return False
    ratio = len(rewritten) / max(len(original), 1)
    return 0.5 <= ratio <= 1.7


def polish_draft(md: str, model: str = DEFAULT_MODEL) -> tuple[str, int, int]:
    """Polish the narrative paragraph of each section; keep everything else
    (headings, must-reads, freshness, references) untouched.

    Returns (polished_md, sections_polished, sections_kept_extractive).
    """
    lines = md.splitlines()
    out, polished, kept = [], 0, 0
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        if not line.startswith("## ") or line.startswith("## References"):
            continue
        # The narrative paragraph is the first non-empty, non-bold line after
        # the heading (draft_review_v2 emits exactly one).
        while i < len(lines) and not lines[i].strip():
            out.append(lines[i])
            i += 1
        if i >= len(lines) or lines[i].startswith(("**", "#", "[")):
            continue
        body = lines[i]
        try:
            rewritten = _generate(_PROMPT.format(body=body), model)
        except Exception:
            rewritten = ""
        if _verified(body, rewritten):
            out.append(rewritten)
            polished += 1
        else:
            out.append(body)                       # extractive original wins
            kept += 1
        i += 1
    return "\n".join(out), polished, kept


if __name__ == "__main__":
    models = available_models()
    if not models:
        print("Ollama is not running (or not installed) - see docs/OLLAMA_SETUP.md")
    else:
        print("Ollama models available:", ", ".join(models))
