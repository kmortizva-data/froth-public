"""
build.py - compiles every .tex note in 1_Apuntes/src/ to a PDF in 1_Apuntes/.

USAGE (from the project root):
    .venv\\Scripts\\python.exe 1_Apuntes\\build.py

Uses the Tectonic compiler that lives in tools/tectonic.exe (no LaTeX install required).
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TECTONIC = ROOT / "tools" / "tectonic.exe"
SRC = ROOT / "1_Apuntes" / "src"
# Batman reorganized the library (2026-07-09): individual PDFs live in this subfolder,
# the root keeps the merged volume + LEEME. Respect his curation.
OUT = ROOT / "1_Apuntes" / "1. Apuntes acumulados"

def main() -> int:
    if not TECTONIC.exists():
        print(f"Compiler not found: {TECTONIC}")
        return 1
    # Every .tex except the preamble (an included fragment, not a standalone document) and
    # the volume masters written by build_book.py, whose names start with "_". Without that
    # second rule this script compiled the whole 93-page book as if it were note number 47
    # and dropped it into Batman's curated folder.
    docs = sorted(f for f in SRC.glob("*.tex")
                  if f.name != "preamble.tex" and not f.name.startswith("_"))
    if not docs:
        print("No .tex notes to compile.")
        return 0
    failures = 0
    for tex in docs:
        r = subprocess.run([str(TECTONIC), "-o", str(OUT), str(tex)],
                           capture_output=True, text=True)
        if r.returncode == 0:
            print(f"OK   {tex.stem}.pdf")
        else:
            failures += 1
            print(f"FAIL {tex.name}\n{r.stderr[-500:]}")
    print(f"\nDone: {len(docs) - failures}/{len(docs)} compiled.")
    return 1 if failures else 0

if __name__ == "__main__":
    sys.exit(main())
