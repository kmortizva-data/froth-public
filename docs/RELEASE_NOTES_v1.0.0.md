# LitMap v1.0.0 - first public release

Maps the literature of any research topic **by meaning, not citations**: uncapped
multi-source harvest, SPECTER embeddings, auto-named subtopics, an interactive Atlas of
the whole field, a semantically-seeded network, research-gap measurement and a fully
traceable extractive review draft.

## Highlights

- **The Atlas**: the full corpus (15,000+ papers) as WebGL points with per-subtopic
  colors, noise/relevance toggles and a zoom-adaptive legend. Pick subtopics there to
  open them in the Network or the reading guide.
- **Semantic islands**: the Network seeds its physics from the semantic map - adjacent
  hubs are actually related - with island name legends and an honest shown/hidden panel.
- **Cluster-level relevance gate**: contrastive score + per-corpus valley threshold;
  off-topic hubs are dropped whole, real subtopics keep every paper.
- **My space**: a built-in researcher's logbook (to read → reading → summarized →
  interpreted / discarded, with notes and progress).
- **Expert-validated embedding model**: `specter-mineral-v1`, blind-picked twice by a
  domain expert over stock SPECTER and two alternative fine-tunes; automatic fallback
  to stock SPECTER on fresh installs.
- **Verifiable review draft**: every sentence quoted verbatim and cited; optional
  local-LLM polish with a citation-preserving gate.

## Download

**LitMap-portable-win64.zip** (attached): unzip, double-click the launcher. Python and
all dependencies travel inside. No keys required (OpenAlex works anonymously); free
keys make harvests bigger and steadier - see `docs/GET_YOUR_KEYS.md`.
