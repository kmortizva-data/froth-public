# Froth

**Relevant papers float to the top - like value on a flotation bubble.**

Froth maps the literature of a research topic **by meaning, not by citations**: it
harvests hundreds of papers, embeds their abstracts (SPECTER), clusters them into
subtopics named by real sentences, draws interactive maps, and writes an **extractive
review draft where every sentence is quoted verbatim from the corpus** with a traceable
citation. Nothing is generated, so nothing can be hallucinated.

Built from scratch as a learn-ML-by-building project around a real EMerald
master-thesis topic (Li-mica flotation at the Beauvoir deposit, France). It works for
**any** topic: paste a thesis title in the app and it harvests, embeds and maps it.

## What makes it different

- **Content, not citations.** Papers that study the same thing sit together even if
  they never cite each other (SPECTER embeddings + UMAP + HDBSCAN).
- **Scales to the WHOLE field.** The harvest has no result ceiling (every source is
  paginated to exhaustion - a thesis can't say "it wasn't in the first 200, so it's
  not relevant"), and the **Atlas** draws the full corpus (15,000+ papers) as WebGL
  points with a zoom-adaptive legend. Pick subtopics there and the Network / reading
  guide render exactly those, whole and readable.
- **A relevance gate that kills junk by the hub.** Uncapped harvests drag in off-topic
  clusters (koala veterinary papers arrived via "iron"). A contrastive score (close to
  the topic core AND far from the generic mass, title-protected) judges whole clusters
  against a per-corpus valley threshold - junk hubs die entire, real subtopics keep
  every paper.
- **My space: the review's logbook.** File any paper from its detail panel and track it
  through *to read → reading → summarized → interpreted / discarded* with your notes
  and a progress bar - the review process itself is traceable, no side spreadsheet.
- **Subtopics named by sentences, not keywords.** Each cluster is titled by its
  centroid sentence: the real abstract sentence closest to the cluster's semantic
  center.
- **A review draft you can defend.** Extractive summarization: sentence openers picked
  by Borda rank across two independent rankers (centroid + TextRank), support sentences
  de-duplicated with MMR (the diversity knob is swept on YOUR corpus, not defaulted),
  every sentence cited [n], BibTeX export included.
- **Optional local LLM polish, verified.** Ollama rewrites each paragraph and a gate
  checks that every citation survives exactly; failing sections keep the extractive
  original. Free, private, offline. No OpenAI dependency.
- **Knobs chosen by data, not defaults.** Cluster granularity recommended per corpus by
  DBCV; must-reads cut per subtopic by h-index; search scores graded against measured
  same-subtopic similarity.
- **Two doors, same engine.** Thesis mode (explore a topic) or Task mode (attach
  assignment PDFs, get the papers that matter for it).
- **Your own sources.** Connect institutional accounts: Scopus/Elsevier key, Semantic
  Scholar, Crossref, merged and de-duplicated against the OpenAlex base. Keys never
  leave your machine.
- **Open, local, reproducible.** MIT licensed, no freemium walls, fixed seeds, every
  stage saves its output.

## Download (no install)

Grab **Froth-portable-win64.zip** from the
[Releases page](https://github.com/kmortizva-data/froth/releases): unzip anywhere and
double-click the launcher. Python and every dependency travel inside the zip.

## Quickstart (Windows)

```powershell
git clone https://github.com/kmortizva-data/froth.git
cd froth
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py
```

First run downloads the SPECTER model (~440 MB, cached). Then paste any thesis title in
the app and hit "Harvest & map it": the whole pipeline (harvest, embed, cluster) runs
from the UI. Optional but recommended: connect your own free API keys for bigger,
steadier harvests. Step-by-step guide: `docs/GET_YOUR_KEYS.md`.

Prefer a native window? `python desktop.py` boots the same app inside its own desktop
window with an animated flotation splash. For the optional LLM polish install Ollama
(`docs/OLLAMA_SETUP.md`); Froth starts it automatically when present.

## The app

Six views, one shared state (granularity, years, filters and the subtopic pick live in
the sidebar / Atlas legend and govern every tab):

- **Atlas**: the whole corpus as WebGL points - wheel zoom, pan, one own hue per
  subtopic, noise and low-relevance toggles, and a legend where you pick the subtopics
  to open elsewhere.
- **Search**: semantic search with match grades measured against the corpus itself,
  plus DOI / open-access PDF links.
- **Network**: the microscope - draws your Atlas pick (or the biggest subtopics) with
  physics seeded from the semantic map, so neighboring hubs really are related; island
  legends name each hub and a corner panel says what is shown and hidden.
- **Packed bubbles**: a reading guide for the picked subtopics, one column each,
  must-reads above an h-index line computed per cluster.
- **Review**: the extractive draft with adjustable density, lambda sweep transparency,
  .md and .bib downloads, and one-click local-LLM polish.
- **My space**: the researcher's logbook (stages, notes, progress).

Click any paper anywhere for the full record with in-text, APA and IEEE citations ready
to copy - and a one-click "Add to My space".

## Screenshots

| The Atlas (full corpus) | Network (semantic islands) | My space |
|---|---|---|
| ![Atlas](docs/img/atlas.png) | ![Network](docs/img/network.png) | ![My space](docs/img/my_space.png) |

## The research behind it

The engine was hardened on 22 real master-thesis topics harvested WITHOUT a result
ceiling: **189,737 papers**, gated down to ~72,000 relevant by the contrastive
cluster-level filter. Three fine-tunes of SPECTER were trained and compared honestly
(DBCV over the 22 clean corpora + double-blind expert rankings):

- **More data did not help** - the 3x-bigger title-abstract fine-tune LOSES to stock
  SPECTER on clean corpora. Method beats quantity.
- **Citation triplets** (SPECTER's own training recipe on the corpus' internal
  citation graph, 150k triplets) achieve the best geometric score - and the domain
  expert blind-ranked its map LAST. Geometric cluster quality is not narrative
  quality; that model is kept for citation-similarity features instead.
- **Production** uses the small curated fine-tune (`specter-mineral-v1`): blind-picked
  by the domain expert twice and better than stock on 14/22 topics. Installs without
  the local model fall back to stock SPECTER automatically.

Every verdict, including the negative ones, is documented in the learning notes.

## Project structure

```
froth/            engine (one module per pipeline stage) + bridge component
app.py             Streamlit app (all views and modes)
desktop.py         native desktop window (pywebview) with splash
packaging/         portable-zip builder (deliverable that runs without installing)
docs/              key setup, Ollama setup, working-method guides, archived views
1_Apuntes/         learning notes (Spanish, LaTeX/PDF): the project doubles as a course
2_Datos/           harvested data (gitignored)
3_Resultados/      generated outputs: interactive HTMLs, review drafts (gitignored)
assets/            brand (logo, icon)
```

## License

MIT. See `LICENSE`.
