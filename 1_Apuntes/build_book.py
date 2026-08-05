"""
build_book.py - joins every note in 1_Apuntes/src/ into ONE navigable volume.

Why this exists instead of stapling the individual PDFs together: the previous merged
volume (00-30) was built with pypdf, which concatenates pages and nothing else. It had
59 pages, zero bookmarks, and every note restarted its page numbering at 1, so there was
no way to jump to note 23 or to cite "page 40". Rebuilding the notes as a single LaTeX
document instead gives a real table of contents, continuous page numbers and a clickable
bookmark per note, at the cost of one extra compile.

USAGE (from the project root):
    .venv\\Scripts\\python.exe 1_Apuntes\\build_book.py        # Spanish volume (src/)
    .venv\\Scripts\\python.exe 1_Apuntes\\build_book.py en     # English volume (src_en/)

The English set is a translation in progress, so the builder accepts a partial folder and
reports how far along it is instead of failing or quietly shipping an incomplete book.

Uses the Tectonic compiler in tools/tectonic.exe (no LaTeX install required).
Writes the generated master .tex next to the notes so the result is reproducible and
inspectable, not a black box.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TECTONIC = ROOT / "tools" / "tectonic.exe"
OUT = ROOT / "1_Apuntes"

# The English volume is a translation in progress, so the builder has to work with a partial
# set and say so, instead of failing or pretending the book is complete.
LANGS = {
    "es": {"src": OUT / "src", "master": "_libro_es.tex",
           "book": "Froth_Apuntes_completos_ES",
           "head": r"Froth --- Apuntes de ML (volumen completo)",
           "pdftitle": "Froth - Apuntes de Machine Learning"},
    "en": {"src": OUT / "src_en", "master": "_book_en.tex",
           "book": "Froth_Study_Notes_EN",
           "head": r"Froth: ML study notes (complete volume)",
           "pdftitle": "Froth - Machine Learning study notes"},
}

# Pulled from each note's \cabecera{number}{title}.
HEADER = re.compile(r"\\cabecera\{([^}]*)\}\{(.*?)\}\s*$", re.M | re.S)

PREAMBLE_EXTRA = r"""
% --- Book mode: the notes keep their own look, the volume adds navigation ---
\setcounter{secnumdepth}{0}  % no global numbering: note 45's sections are not "sections 201..."
\setcounter{tocdepth}{0}     % the contents list the NOTES, not every heading inside them
\usepackage{bookmark}        % real PDF bookmarks, one per note
% hyperref takes its bookmark depth FROM tocdepth, so the line above silently produced a
% volume with zero bookmarks. The two settings have to be decoupled by hand.
% Notes are registered one level ABOVE their own headings (part vs section) so the reader's
% bookmark pane is a tree: 46 notes, each unfolding into its sections, instead of 211 flat
% entries where a note title looks the same as a heading inside it.
\hypersetup{bookmarksdepth=1,bookmarksopen=true,bookmarksopenlevel=0,
            pdftitle={__PDFTITLE__}}
\fancyhead[L]{\small\color{litblue}__HEAD__}
"""

COVERS = {"es": r"""
\begin{titlepage}
\centering
\vspace*{3cm}
{\Huge\bfseries\color{litblue} Froth}\\[6pt]
{\Large\color{litblue} Apuntes de Machine Learning}\\[2cm]
{\large Aprender construyendo: __N__ apuntes nacidos de un proyecto real}\\[1cm]
{\normalsize De qué es un embedding a por qué 10.921 papers caben en pantalla.\\
Cada apunte salió de algo que pasó de verdad, tropiezos incluidos.}\\[2cm]
{\small\color{litblue} Proyecto Froth --- mapeo semántico de literatura científica}\\[4pt]
{\small Compilado el __DATE__}
\vfill
\end{titlepage}
\tableofcontents
\clearpage
""", "en": r"""
\begin{titlepage}
\centering
\vspace*{3cm}
{\Huge\bfseries\color{litblue} Froth}\\[6pt]
{\Large\color{litblue} Machine Learning study notes}\\[2cm]
{\large Learning by building: __N__ notes that came out of a real project}\\[1cm]
{\normalsize From what an embedding is to why 10,921 papers fit on screen and 1,772 do not.\\
Every note came from something that actually happened, mistakes included.}\\[2cm]
{\small\color{litblue} Froth project: semantic mapping of scientific literature}\\[4pt]
{\small Built on __DATE__}
\vfill
\end{titlepage}
\tableofcontents
\clearpage
"""}


def split_note(tex: Path) -> tuple[list[str], str]:
    """Returns (extra preamble lines, body).

    Four notes (05, 08, 12, 19) load tikz for their diagrams in their OWN preamble, not in
    the shared one. In a single volume those lines have to be hoisted to the top or the
    diagrams fail to compile, so the split is done here instead of assuming every note is
    preamble-free.
    """
    text = tex.read_text(encoding="utf-8")
    head, _, rest = text.partition(r"\begin{document}")
    extra = [ln.strip() for ln in head.splitlines()
             if ln.strip().startswith("\\")
             and not ln.strip().startswith((r"\documentclass", r"\input{preamble}"))]
    return extra, rest[:rest.rindex(r"\end{document}")].strip()


def toc_entry(body: str, fallback: str) -> tuple[str, str]:
    """Reads the note's own \\cabecera so the contents match the page, character for character."""
    m = HEADER.search(body)
    if not m:
        return fallback, fallback
    number, title = m.group(1).strip(), " ".join(m.group(2).split())
    return number, title


def main() -> int:
    if not TECTONIC.exists():
        print(f"Compiler not found: {TECTONIC}")
        return 1
    lang = sys.argv[1] if len(sys.argv) > 1 else "es"
    if lang not in LANGS:
        print(f"Unknown language {lang!r}. Use one of: {', '.join(LANGS)}")
        return 1
    cfg = LANGS[lang]
    src, master = cfg["src"], cfg["src"] / cfg["master"]
    entry = "Apunte" if lang == "es" else "Note"

    notes = sorted(f for f in src.glob("*.tex")
                   if f.name != "preamble.tex" and not f.name.startswith("_"))
    if not notes:
        print(f"No .tex notes to join in {src}.")
        return 0
    # The Spanish set is the reference: it says how much of the translation is done.
    total = len([f for f in LANGS["es"]["src"].glob("*.tex")
                 if f.name != "preamble.tex" and not f.name.startswith("_")])
    if len(notes) < total:
        print(f"NOTE: partial volume, {len(notes)} of {total} notes translated "
              f"({100 * len(notes) // total}%).")

    from datetime import date
    bodies, hoisted = [], []
    for tex in notes:
        extra, body = split_note(tex)
        bodies.append((tex, body))
        for line in extra:
            if line not in hoisted:
                hoisted.append(line)
    if hoisted:
        print("Hoisted to the volume preamble: " + ", ".join(hoisted))

    head = (PREAMBLE_EXTRA.replace("__PDFTITLE__", cfg["pdftitle"])
                          .replace("__HEAD__", cfg["head"]))
    parts = [r"\documentclass[11pt,a4paper]{article}", r"\input{preamble}",
             *hoisted, head, r"\begin{document}",
             COVERS[lang].replace("__N__", str(len(notes)))
                         .replace("__DATE__", date.today().isoformat())]

    listing = []
    for tex, body in bodies:
        number, title = toc_entry(body, tex.stem)
        listing.append(f"{number} {title}")
        # The bookmark and the contents entry are added by hand, because the note's title
        # is drawn by \cabecera (a coloured box), not by a \section LaTeX can index.
        sep = "---" if lang == "es" else ":"   # no em dashes in English, public-facing text
        parts.append(r"\phantomsection")
        parts.append(r"\addcontentsline{toc}{part}{%s %s %s %s}" % (entry, number, sep, title))
        parts.append(body)
        parts.append(r"\clearpage")

    parts.append(r"\end{document}")
    master.write_text("\n".join(parts), encoding="utf-8")

    r = subprocess.run([str(TECTONIC), "-o", str(OUT), str(master)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"FAIL\n{r.stderr[-2000:]}")
        return 1
    (OUT / f"{master.stem}.pdf").replace(OUT / f"{cfg['book']}.pdf")
    print(f"OK   {cfg['book']}.pdf  ({len(notes)} notes)")
    for line in listing:
        print(f"     {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
