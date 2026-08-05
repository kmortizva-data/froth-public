# LitMap v1.0.0 - first public release

Map the literature of any research topic by meaning, not by citations.

## Highlights

- **Semantic corpus engine**: multi-source harvest (OpenAlex, Crossref, Scopus,
  Semantic Scholar), SPECTER embeddings, relevance self-cleaning, UMAP + HDBSCAN
  clustering with per-corpus DBCV-recommended granularity. Hardened on 22 real
  master-thesis topics (22/22 passed).
- **Subtopics named by real sentences** (centroid sentence), not keyword soup.
- **Extractive review draft**: every sentence quoted verbatim from a corpus
  abstract with a traceable [n] citation and BibTeX export. Openers chosen by
  Borda rank across two rankers (centroid + TextRank), support de-duplicated
  with MMR swept on your corpus.
- **Optional local LLM polish** (Ollama): rewrites paragraphs behind a
  verification gate; any section that loses or invents a citation keeps its
  extractive original.
- **Interactive views**: semantic search with corpus-calibrated match grades,
  force-directed network with calibrated spring lengths and boundary-paper
  rings, per-subtopic reading guide with h-index must-read cuts. Click any
  paper anywhere for the full record and copy-ready citations.
- **Two modes, one engine**: Thesis (explore a topic) and Task (attach
  assignment PDFs).
- **Desktop app**: native window with animated flotation splash; portable zip
  runs without installing anything.

## Downloads

- **Source (this repo)**: clone and `pip install -r requirements.txt` (see README).
- **LitMap-portable-win64.zip** (~0.52 GB, attached to this release): unzip and
  double-click the launcher. Python, all dependencies and the desktop window
  included; first run downloads the SPECTER model (~440 MB, cached).

## Notes

- Your API keys never ship anywhere: the app has a Connect panel and
  `docs/GET_YOUR_KEYS.md` walks you through getting your own free keys.
- License: MIT.
