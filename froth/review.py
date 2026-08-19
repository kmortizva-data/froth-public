"""
review.py - PHASE 7: Review 2.0 (extractive summarization).

WHAT IT DOES: upgrades the per-cluster review scaffold into readable text WITHOUT
generating a single word: it SELECTS real sentences from the corpus abstracts
(extractive summarization). Every selected sentence has a source paper, so every
claim is traceable by construction - hallucination is impossible.

Phase 7.1 (this file): sentence splitting + centroid ranking - the sentence whose
SPECTER vector sits closest to the cluster's center is the most representative
one. TextRank (7.2) and MMR (7.3) will build on the same sentence table.

Preview on the current corpus:
    .venv\\Scripts\\python.exe -m froth.review
"""

import re

import numpy as np
import pandas as pd

from . import config
from .embed import _get_model, load_embeddings

# Process-level memo of SPECTER vectors keyed by the exact text. Moving the
# granularity slider re-clusters (candidate keyphrases and non-noise sentences
# shift), but the corpus vocabulary is stable, so most texts are already
# embedded - this makes the slider fast (the KeyBERT titles were re-embedding
# hundreds of candidates on every rerun, painful on the CPU portable build).
_EMB_CACHE: dict[str, np.ndarray] = {}
_EMB_CACHE_MAX = 40000


def _embed_cached(texts: list[str], model) -> np.ndarray:
    """SPECTER-embed `texts`, reusing any already computed. Normalized vectors."""
    if not texts:
        return np.empty((0, 0))
    missing = [t for t in dict.fromkeys(texts) if t not in _EMB_CACHE]
    if missing:
        if len(_EMB_CACHE) + len(missing) > _EMB_CACHE_MAX:
            _EMB_CACHE.clear()                       # simple reset when it grows big
        embs = model.encode(missing, batch_size=64, normalize_embeddings=True,
                            show_progress_bar=False)
        for t, e in zip(missing, embs):
            _EMB_CACHE[t] = np.asarray(e, dtype=np.float32)
    return np.array([_EMB_CACHE[t] for t in texts])


def split_sentences(text: str) -> list[str]:
    """Split an abstract into sentences (regex, no extra dependency).

    Cut after sentence-final punctuation followed by whitespace and a capital
    letter - good enough for scientific prose, where abbreviations like "e.g."
    are not followed by a capital.
    """
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(])", str(text or ""))
    return [p.strip() for p in parts if p.strip()]


# A review sentence must stand alone. Sentences opening with an anaphor ("This
# method...", "It also...") or a discourse connector ("In addition, ...")
# point back to text the reader will not see. Rejected, never trimmed: quoted
# sentences stay verbatim (source-fidelity rule).
_ANAPHORA = {"this", "these", "those", "it", "they", "such", "here", "we",
             "our", "however", "moreover", "furthermore", "also", "thus",
             "additionally", "meanwhile", "besides", "finally", "hence",
             "therefore", "consequently", "nevertheless", "firstly",
             "secondly", "thirdly", "lastly", "then", "next"}
_CONNECTORS = ("in addition", "on the other hand", "in contrast",
               "on the contrary", "as a result", "for this reason",
               "in this context", "at the same time")


def _self_contained(sentence: str) -> bool:
    words = sentence.split()
    if not 8 <= len(words) <= 60:                  # fragments and run-ons out
        return False
    if words[0].strip(",").lower() in _ANAPHORA:
        return False
    if sentence.lower().startswith(_CONNECTORS):
        return False
    return sentence[0].isupper() or sentence[0] == "("


def sentence_table(tm: pd.DataFrame) -> pd.DataFrame:
    """Explode abstracts into one row per usable sentence.

    Keeps the source paper's metadata on every row: that link IS the traceable
    citation later. Row order of `tm` is preserved via the `row` column.
    """
    def _year(value) -> int:
        """0 for an unknown year rather than a crash.

        Not theoretical: 3 of the 3,032 papers in the scheelite ores corpus have no year,
        and `int(NaN)` raised, which took the whole review and the Obsidian export down with
        it. graph.py learned this in phase 1.5 (12 of 21 corpora had empty year/citation
        cells); this was the same hole, still open. The paper is kept and the year reads as
        unknown, never invented.
        """
        try:
            return 0 if pd.isna(value) else int(value)
        except (TypeError, ValueError):
            return 0

    rows = []
    for pos, (_, r) in enumerate(tm.iterrows()):
        for s in split_sentences(r.get("abstract", "")):
            if _self_contained(s):
                rows.append({"row": pos, "cluster": int(r["cluster"]),
                             "sentence": s, "title": r["title"],
                             "year": _year(r["year"]), "doi": r.get("doi", ""),
                             "authors": r.get("authors", ""),
                             "source": r.get("source", "")})
    return pd.DataFrame(rows)


def _sentences_and_embeddings(tm: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    """Shared prep for every ranker: the sentence table + its SPECTER vectors.

    Embedding is the expensive step, so both 7.1 (centroid) and 7.2 (TextRank)
    eat from this same table instead of encoding twice.
    """
    sents = sentence_table(tm[tm["cluster"] != -1].reset_index(drop=True))
    if sents.empty:
        return sents, np.empty((0, 0))
    emb = _embed_cached(sents["sentence"].tolist(), _get_model())
    return sents, emb


def _pick_top(part: pd.DataFrame, scores: np.ndarray,
              top_n: int, per_paper_cap: int) -> list[dict]:
    """Take the best-scored sentences, capping how many one paper may supply."""
    picked, per_paper = [], {}
    for j in np.argsort(scores)[::-1]:
        row = part.iloc[j]
        if per_paper.get(row["title"], 0) >= per_paper_cap:
            continue
        picked.append({**row.to_dict(), "score": float(scores[j])})
        per_paper[row["title"]] = per_paper.get(row["title"], 0) + 1
        if len(picked) >= top_n:
            break
    return picked


def key_sentences(tm: pd.DataFrame, vectors: np.ndarray,
                  top_n: int = 5, per_paper_cap: int = 2) -> pd.DataFrame:
    """PHASE 7.1 - rank each cluster's sentences by closeness to its centroid.

    The centroid is the mean of the cluster's PAPER vectors (768D) - the same
    space the map lives in. Sentences are embedded with the same model, so the
    cosine between a sentence and the centroid says "how typical of this
    subtopic is this sentence". `vectors` must be row-aligned with `tm` (the
    app's filtered_state already provides exactly that pair).

    per_paper_cap keeps one prolific abstract from monopolizing a summary.
    Returns [cluster, sentence, score, title, year, doi] sorted by cluster+rank.
    """
    sents, emb = _sentences_and_embeddings(tm)
    if sents.empty:
        return sents

    norm = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    clusters_col = tm["cluster"].to_numpy()

    picked = []
    for c in sorted(sents["cluster"].unique()):
        centroid = norm[clusters_col == c].mean(axis=0)
        centroid /= np.linalg.norm(centroid)
        part = sents[sents["cluster"] == c]
        scores = emb[part.index.to_numpy()] @ centroid
        picked.extend(_pick_top(part, scores, top_n, per_paper_cap))
    return pd.DataFrame(picked).drop(columns=["row"])


def textrank_sentences(tm: pd.DataFrame, top_n: int = 5,
                       per_paper_cap: int = 2, damping: float = 0.85) -> pd.DataFrame:
    """PHASE 7.2 - rank each cluster's sentences with TextRank (PageRank on a
    sentence graph).

    Nodes = the cluster's sentences; edge weights = cosine similarity between
    them. PageRank then finds the sentences that the whole cluster "points at":
    a sentence matters if sentences that matter resemble it - literally the hub
    idea from Phase 4, applied to sentences. Unlike the centroid (which rewards
    the most TYPICAL sentence), TextRank rewards the most ENDORSED one; the two
    rankings often agree at the top and disagree in interesting ways below it.

    Implemented as plain power iteration (no dependency): 50 rounds of
    r = (1-d)/N + d * W r  on the column-normalized similarity matrix.
    """
    sents, emb = _sentences_and_embeddings(tm)
    if sents.empty:
        return sents

    picked = []
    for c in sorted(sents["cluster"].unique()):
        part = sents[sents["cluster"] == c]
        vecs = emb[part.index.to_numpy()]
        picked.extend(_pick_top(part, _pagerank(vecs, damping),
                                top_n, per_paper_cap))
    return pd.DataFrame(picked).drop(columns=["row"])


def _pagerank(vecs: np.ndarray, damping: float = 0.85) -> np.ndarray:
    """Power-iteration PageRank on the sentence similarity graph."""
    n = len(vecs)
    if n == 1:
        return np.ones(1)
    sim = np.clip(vecs @ vecs.T, 0, None)          # negative cosine = no edge
    np.fill_diagonal(sim, 0.0)
    col_sums = sim.sum(axis=0)
    col_sums[col_sums == 0] = 1.0                  # isolated sentence: no votes out
    walk = sim / col_sums                           # column-stochastic transition
    rank = np.full(n, 1.0 / n)
    for _ in range(50):
        rank = (1 - damping) / n + damping * (walk @ rank)
    return rank


def _mmr_pick(part: pd.DataFrame, vecs: np.ndarray, rel: np.ndarray,
              top_n: int, lam: float, per_paper_cap: int) -> list[dict]:
    """Greedy MMR selection: each pick maximizes
    lam * relevance  -  (1 - lam) * similarity_to_already_selected.

    lam=1 collapses to plain centroid ranking; lower lam trades relevance for
    diversity. Selection is greedy because the exact optimum is combinatorial
    - the classic Carbonell & Goldstein (1998) formulation.
    """
    selected, sel_vecs, per_paper = [], [], {}
    candidates = list(range(len(part)))
    while candidates and len(selected) < top_n:
        best_j, best_val = None, -np.inf
        for j in candidates:
            row = part.iloc[j]
            if per_paper.get(row["title"], 0) >= per_paper_cap:
                continue
            redundancy = max((float(vecs[j] @ v) for v in sel_vecs), default=0.0)
            val = lam * rel[j] - (1 - lam) * redundancy
            if val > best_val:
                best_j, best_val = j, val
        if best_j is None:
            break
        row = part.iloc[best_j]
        selected.append({**row.to_dict(), "score": float(rel[best_j])})
        sel_vecs.append(vecs[best_j])
        per_paper[row["title"]] = per_paper.get(row["title"], 0) + 1
        candidates.remove(best_j)
    return selected


def mmr_sentences(tm: pd.DataFrame, vectors: np.ndarray, top_n: int = 5,
                  lam: float = 0.7, per_paper_cap: int = 2) -> pd.DataFrame:
    """PHASE 7.3 - centroid relevance + MMR anti-redundancy.

    Same contract as key_sentences (tm and vectors row-aligned); the difference
    is WHICH of the relevant sentences survive: MMR forces each new pick to say
    something the previous picks did not. Use recommend_lambda() to choose lam
    from the corpus instead of trusting the default.
    """
    sents, emb = _sentences_and_embeddings(tm)
    if sents.empty:
        return sents

    norm = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    clusters_col = tm["cluster"].to_numpy()

    picked = []
    for c in sorted(sents["cluster"].unique()):
        centroid = norm[clusters_col == c].mean(axis=0)
        centroid /= np.linalg.norm(centroid)
        part = sents[sents["cluster"] == c]
        vecs = emb[part.index.to_numpy()]
        rel = vecs @ centroid
        picked.extend(_mmr_pick(part, vecs, rel, top_n, lam, per_paper_cap))
    return pd.DataFrame(picked).drop(columns=["row"])


def recommend_lambda(tm: pd.DataFrame, vectors: np.ndarray, top_n: int = 5,
                     grid: tuple = (0.5, 0.6, 0.7, 0.8, 0.9, 1.0)) -> tuple[float, pd.DataFrame]:
    """Data-driven lambda (project rule: knobs come from the data, not defaults).

    For each candidate lambda, run MMR and measure the two things it trades:
    mean relevance of the picked sentences (cosine to centroid) and their mean
    pairwise similarity (redundancy).

    Rule: recommend the SMALLEST lambda whose relevance keeps >= 99% of the
    lambda=1 relevance - i.e. take all the diversity that is free, stop when
    it starts costing real relevance. (First attempt maximized relevance minus
    redundancy, but that objective is degenerate: it always improves as lambda
    drops, so it pins to the grid edge - kept in the sweep table as evidence.)
    Returns (best_lambda, diagnostics table) like recommend_min_cluster_size.
    """
    sents, emb = _sentences_and_embeddings(tm)
    if sents.empty:
        return 0.7, pd.DataFrame()

    norm = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    clusters_col = tm["cluster"].to_numpy()

    rows = []
    for lam in grid:
        rels, reds = [], []
        for c in sorted(sents["cluster"].unique()):
            centroid = norm[clusters_col == c].mean(axis=0)
            centroid /= np.linalg.norm(centroid)
            part = sents[sents["cluster"] == c]
            vecs = emb[part.index.to_numpy()]
            rel = vecs @ centroid
            picks = _mmr_pick(part, vecs, rel, top_n, lam, per_paper_cap=2)
            if len(picks) < 2:
                continue
            idx = [part.index.get_loc(i) for i in
                   part[part["sentence"].isin([p["sentence"] for p in picks])].index]
            pv = vecs[idx]
            rels.append(np.mean([p["score"] for p in picks]))
            pair = pv @ pv.T
            reds.append(float(pair[np.triu_indices(len(pv), k=1)].mean()))
        mean_rel, mean_red = float(np.mean(rels)), float(np.mean(reds))
        rows.append({"lambda": lam, "relevance": round(mean_rel, 3),
                     "redundancy": round(mean_red, 3),
                     "gap": round(mean_rel - mean_red, 3)})
    table = pd.DataFrame(rows)
    ceiling = table[table["lambda"] == max(grid)]["relevance"].iloc[0]
    keeps = table[table["relevance"] >= 0.99 * ceiling]
    best_lam = float(keeps["lambda"].min())
    return best_lam, table


def _mmr_phrases(cands: list[str], emb: np.ndarray, rel: np.ndarray,
                 top_n: int, lam: float = 0.6) -> list[str]:
    """Greedy MMR over keyphrase candidates: relevant to the centroid but not
    near-duplicates of each other (so 'lepidolite flotation' + 'fine particles',
    not 'lepidolite flotation' + 'flotation of lepidolite')."""
    picked, sel_idx = [], []
    order = list(np.argsort(rel)[::-1])
    while order and len(picked) < top_n:
        best_j, best_val = None, -np.inf
        for j in order:
            red = max((float(emb[j] @ emb[s]) for s in sel_idx), default=0.0)
            val = lam * rel[j] - (1 - lam) * red
            if val > best_val:
                best_j, best_val = j, val
        picked.append(cands[best_j])
        sel_idx.append(best_j)
        order.remove(best_j)
    return picked


def cluster_subtitles(tm: pd.DataFrame, vectors: np.ndarray,
                      n_support: int = 2) -> dict[int, tuple[str, str]]:
    """PHASE 7.1b, v2 (Batman: truncated sentences read like Bibles) - a SHORT,
    sense-making title per cluster via KeyBERT-style keyphrase extraction.

    The field's fix for "c-TF-IDF keywords don't read well" is KeyBERTInspired
    (also BERTopic's representation layer): make candidate keyphrases, embed
    them, keep the ones closest to the cluster's meaning, MMR for diversity.
    Built by hand here on the SPECTER + cosine + MMR pieces Froth already has:

      1. candidates = 2-3 word n-grams of the cluster's title+abstract text,
         through cluster.py's hardened vectorizer (no digits, chem elements kept);
      2. rank by cosine of each candidate's SPECTER vector to the cluster centroid;
      3. MMR picks the best phrase + a couple of diverse supporters.

    Returns {cluster: (title, centroid_sentence)}: the keyphrase title is the
    label every view shows; the full centroid sentence goes to the hover.
    """
    from sklearn.feature_extraction.text import CountVectorizer

    from . import cluster as cl
    from .embed import _get_model

    tm_ok = tm[tm["cluster"] != -1]
    if tm_ok.empty:
        return {}
    norm = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    clusters_col = tm["cluster"].to_numpy()
    global_centroid = norm.mean(axis=0)                  # for the contrastive score
    global_centroid /= np.linalg.norm(global_centroid)
    model = _get_model()
    sents, sent_emb = _sentences_and_embeddings(tm)      # for the hover sentence

    out: dict[int, tuple[str, str]] = {}
    for c in sorted(int(x) for x in tm_ok["cluster"].unique()):
        centroid = norm[clusters_col == c].mean(axis=0)
        centroid /= np.linalg.norm(centroid)
        part_papers = tm_ok[tm_ok["cluster"] == c]
        docs = (part_papers["title"].fillna("") + ". "
                + part_papers["abstract"].fillna("")).tolist()

        title = ""
        # min_df >= 2 drops OCR junk that lives in ONE abstract ('limu', 'nmic').
        # 2-3 word phrases read as titles; relax progressively for tiny clusters.
        for ngram, mdf in (((2, 3), 3), ((2, 3), 2), ((1, 3), 2), ((1, 3), 1)):
            try:
                vec = CountVectorizer(stop_words=cl.STOP_WORDS, ngram_range=ngram,
                                      token_pattern=cl.TOKEN_PATTERN,
                                      min_df=min(mdf, max(1, len(docs))),
                                      max_features=500)
                vec.fit(docs)
            except ValueError:
                continue
            cands = [t for t in vec.get_feature_names_out() if cl.is_good_term(t)]
            if not cands:
                continue
            cemb = _embed_cached(cands, model)       # memoized: fast slider moves
            # CONTRASTIVE score (c-TF-IDF idea in embedding space): close to THIS
            # cluster, far from the whole corpus - rewards specific terms
            # ('lepidolite flotation') over generic ones ('ore flotation').
            rel = cemb @ centroid - 0.4 * (cemb @ global_centroid)
            phrases = _mmr_phrases(cands, cemb, rel, top_n=1 + n_support)
            title = phrases[0]
            break

        sentence = ""
        if not sents.empty:
            part = sents[sents["cluster"] == c]
            if len(part):
                sentence = str(part.iloc[int(np.argmax(
                    sent_emb[part.index.to_numpy()] @ centroid))]["sentence"])
        if not title:                                    # last resort
            title = " ".join(sentence.split()[:5]) or f"subtopic {c}"
        title = title[:1].upper() + title[1:]            # sentence case (Batman)
        out[c] = (title, sentence)
    return out


def _h_index(citations: list[int]) -> int:
    """Largest h such that h papers have at least h citations each."""
    cits = sorted((int(c) for c in citations), reverse=True)
    h = 0
    for i, c in enumerate(cits, start=1):
        if c >= i:
            h = i
    return h


def _bibtex_key(authors: str, year: int, title: str) -> str:
    surname = str(authors or "anon").split(",")[0].split()[-1]
    first_word = re.sub(r"[^a-zA-Z]", "", str(title).split()[0]) or "paper"
    return f"{re.sub(r'[^a-zA-Z]', '', surname).lower()}{year}{first_word.lower()}"


def draft_review_v2(tm: pd.DataFrame, vectors: np.ndarray, lam: float = 0.7,
                    support_n: int = 2, save: bool = True) -> tuple[str, str]:
    """PHASE 7.4 - assemble the extractive review draft (Batman's mix).

    Per cluster section: TextRank OPENS (panorama sentences collect the most
    votes), centroid+MMR SUPPORT with diverse specifics, and a sentence both
    rankers rank top-3 is flagged as a consensus pick (†). Every sentence is
    quoted verbatim from an abstract and cited [n] - traceable by
    construction, nothing generated. Also emits must-reads (h-index cut) and
    a freshness line per cluster, plus a BibTeX file of every cited paper.

    lam: pass recommend_lambda()'s pick; default 0.7 (the Beauvoir vote).
    Returns (markdown, bibtex, refs table [n/title/year]); saves the first two
    to 3_Resultados/ when save=True.
    """
    from .gaps import _first_author, safe_int

    sents, emb = _sentences_and_embeddings(tm)
    if sents.empty:
        return "", ""

    norm = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    clusters_col = tm["cluster"].to_numpy()

    refs: dict[str, int] = {}                      # title -> [n], order of appearance
    ref_rows: dict[str, dict] = {}

    def cite(row) -> str:
        title = str(row["title"])
        if title not in refs:
            refs[title] = len(refs) + 1
            ref_rows[title] = dict(row)
        return f"[{refs[title]}]"

    def with_cite(row, consensus: bool) -> str:
        s = str(row["sentence"]).rstrip()
        mark = "†" if consensus else ""
        body = s[:-1] if s.endswith(".") else s
        return f"{body} {cite(row)}{mark}."

    L = [f"# Literature review draft v2 - {config.TOPIC}", "",
         "_Extractive draft: every sentence is quoted verbatim from a corpus "
         "abstract and carries its citation - nothing is generated, so nothing "
         "can be hallucinated. Section openers are chosen by Borda rank across "
         "two independent rankers (centroid + TextRank); support sentences are "
         f"typical but diverse (MMR, lambda={lam}). † = both rankers "
         "independently agree on the sentence._", ""]

    for c in sorted(sents["cluster"].unique()):
        papers = tm[clusters_col == c]
        part = sents[sents["cluster"] == c]
        vecs = emb[part.index.to_numpy()]
        centroid = norm[clusters_col == c].mean(axis=0)
        centroid /= np.linalg.norm(centroid)
        rel = vecs @ centroid
        pr = _pagerank(vecs)

        top_rel = set(part.iloc[np.argsort(rel)[::-1][:3]]["sentence"])
        top_pr = set(part.iloc[np.argsort(pr)[::-1][:3]]["sentence"])
        consensus = top_rel & top_pr

        # Opener by Borda: best combined RANK across both methods (scores live
        # on different scales, ranks don't). Hijacking the opener would require
        # fooling centroid AND TextRank at once - the dense-subgroup capture of
        # note 36 loses because centroid ranks those sentences low.
        rank_rel = np.argsort(np.argsort(rel)[::-1])
        rank_pr = np.argsort(np.argsort(pr)[::-1])
        opener = part.iloc[int(np.argmin(rank_rel + rank_pr))]
        support = [p for p in _mmr_pick(part, vecs, rel, support_n + 1, lam, 2)
                   if p["sentence"] != opener["sentence"]][:support_n]

        label = papers["label"].iloc[0]
        y0, y1 = int(papers["year"].min()), int(papers["year"].max())
        L.append(f"## {label} ({len(papers)} papers, {y0}–{y1})")
        L.append("")
        body = [with_cite(opener, opener["sentence"] in consensus)]
        body += [with_cite(p, p["sentence"] in consensus) for p in support]
        L.append(" ".join(body))
        L.append("")

        h = _h_index(papers["citations"].tolist())
        must = papers.sort_values("citations", ascending=False).head(min(h, 5))
        if h and len(must):
            entries = "; ".join(f"{str(r['title'])[:70]} ({safe_int(r['year'])}) {cite(r)}"
                                for _, r in must.iterrows())
            L.append(f"**Must-reads (h-index = {h}, top {len(must)} shown):** {entries}")
        fresh = int((papers["year"] >= 2024).sum())
        L.append(f"**Freshness:** {fresh} of {len(papers)} papers are from 2024 "
                 "or later.")
        L.append("")

    L.append("## References")
    L.append("")
    bib = []
    for title, n in refs.items():
        r = ref_rows[title]
        year = safe_int(r["year"])
        journal = str(r.get("source", "") or "")
        doi = str(r.get("doi", "") or "")
        tail = f" {journal}." if journal else ""
        tail += f" {doi}" if doi else ""
        L.append(f"[{n}] {_first_author(r.get('authors', ''))} ({year}). "
                 f"{title}.{tail}")
        key = _bibtex_key(r.get("authors", ""), year, title)
        fields = [f"  title = {{{title}}}",
                  f"  author = {{{r.get('authors', '')}}}",
                  f"  year = {{{year}}}"]
        if journal:
            fields.append(f"  journal = {{{journal}}}")
        if doi:
            fields.append(f"  doi = {{{doi.replace('https://doi.org/', '')}}}")
        bib.append("@article{" + key + ",\n" + ",\n".join(fields) + "\n}")

    md_text, bib_text = "\n".join(L) + "\n", "\n\n".join(bib) + "\n"
    refs_df = pd.DataFrame([{"n": n, "title": t, "year": int(ref_rows[t]["year"])}
                            for t, n in refs.items()])
    if save:
        config.DELIVERABLES.mkdir(parents=True, exist_ok=True)
        (config.DELIVERABLES / "review_draft_v2.md").write_text(md_text,
                                                                encoding="utf-8")
        (config.DELIVERABLES / "review_draft_v2.bib").write_text(bib_text,
                                                                 encoding="utf-8")
        print(f"Saved review draft v2 ({len(refs)} traceable refs) to:\n"
              f"  {config.DELIVERABLES / 'review_draft_v2.md'}\n"
              f"  {config.DELIVERABLES / 'review_draft_v2.bib'}")
    return md_text, bib_text, refs_df


if __name__ == "__main__":
    from . import cluster

    df = pd.read_parquet(config.DATA_PROCESSED / "papers.parquet")
    vectors = load_embeddings()
    if "relevance" in df.columns:                  # mirror build_topic_map's filter
        mask = (df["relevance"] >= config.RELEVANCE_THRESHOLD).to_numpy()
        vectors = vectors[mask]
    tm = cluster.load_topic_map()
    assert len(tm) == len(vectors), "topic_map and vectors are out of sync"

    # Judge mode: both rankers side by side - the expert (Batman) decides which
    # one reads better per cluster (7.1 vs 7.2 comparison).
    ks = key_sentences(tm, vectors, top_n=2)
    tr = textrank_sentences(tm, top_n=2)
    for c in sorted(ks["cluster"].unique()):
        label = tm[tm["cluster"] == c]["label"].iloc[0]
        print(f"\n[{c}] {label}")
        print("  CENTROID (most typical):")
        for _, r in ks[ks["cluster"] == c].iterrows():
            print(f"    {r['score']:.3f} | {r['sentence'][:105]}")
        print("  TEXTRANK (most endorsed):")
        for _, r in tr[tr["cluster"] == c].iterrows():
            print(f"    {r['score']:.4f} | {r['sentence'][:105]}")

    # 7.3 demo: lambda chosen from the data, then before/after on the cluster
    # where plain centroid ranking repeats itself the most.
    print("\n--- MMR lambda sweep (knob from the data, not a default) ---")
    lam, sweep = recommend_lambda(tm, vectors)
    print(sweep.to_string(index=False))
    print(f"recommended lambda = {lam}")

    model = _get_model()
    ks3 = key_sentences(tm, vectors, top_n=3)
    worst_c, worst_red = None, -1.0
    for c in sorted(ks3["cluster"].unique()):
        sent3 = ks3[ks3["cluster"] == c]["sentence"].tolist()
        if len(sent3) < 3:
            continue
        v = model.encode(sent3, normalize_embeddings=True, show_progress_bar=False)
        red = float((v @ v.T)[np.triu_indices(len(v), k=1)].mean())
        if red > worst_red:
            worst_c, worst_red = c, red
    mm3 = mmr_sentences(tm, vectors, top_n=3, lam=lam)
    label = tm[tm["cluster"] == worst_c]["label"].iloc[0]
    print(f"\n--- most redundant cluster under plain centroid: [{worst_c}] {label} "
          f"(mean pairwise sim {worst_red:.3f}) ---")
    print("  CENTROID top-3:")
    for _, r in ks3[ks3["cluster"] == worst_c].iterrows():
        print(f"    {r['score']:.3f} | {r['sentence'][:105]}")
    print(f"  MMR top-3 (lambda={lam}):")
    for _, r in mm3[mm3["cluster"] == worst_c].iterrows():
        print(f"    {r['score']:.3f} | {r['sentence'][:105]}")

    print("\n--- assembling review draft v2 (7.4) ---")
    md, _, _ = draft_review_v2(tm, vectors, lam=lam)
    print("\nFirst section preview:")
    lines = md.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("## "))
    for l in lines[start:start + 8]:
        print("  " + l[:115])


# Median references cited by an EMerald master's thesis, counted over the 22 in the local
# corpus: 115, mean 155, quartiles 73 and 234. Batman guessed 60 and chose this number with
# the measurement in front of him. It is what a thesis in his programme actually cites, not
# a round number.
READING_BUDGET = 115


def spectrum_reading_list(topic_map, budget: int = READING_BUDGET):
    """A single ranked reading list that CROSSES the islands instead of emptying them.

    Batman's own description of the problem: "no leer los 40 de isla A que pasaron el
    threshold y después 10 de isla B y después 5 de isla C... que estén organizados y
    rankeados y se me haga más fácil ir leyendo el espectro".

    The existing guide is one column per subtopic, most-cited first, which is exactly the
    read-A-then-B order he does not want. This returns the same papers in a different
    ORDER, built in two steps:

    1. HOW MANY from each island. Proportional to relevance x sqrt(size): a more relevant
       island earns more of the budget, and the square root stops a 571-paper island from
       eating it. Every island gets at least one, because a list that skips an island is
       not a spectrum. Never more than that island's own must-read count (the per-subtopic
       h-index cut), since recommending past it would be padding.
    2. IN WHAT ORDER. By rounds: the best paper of every island first, then each island's
       second, and so on. The first N entries cover N islands, so stopping early still
       leaves him with a view of the whole map rather than the top of one corner.
    """
    import numpy as np

    from .visualize import _must_count

    from .graph import isolated_islands

    tm = topic_map[topic_map["cluster"] != -1]
    if tm.empty:
        return tm.head(0)

    # Islands that cite nothing else on the map are EXCLUDED here, not merely demoted as
    # they are on the Network. The distinction is deliberate: a map shows what the corpus
    # contains and a stray island is information, but a reading list is a claim that these
    # papers are worth hours of his time. Left in, the junk hub took four of the 115 slots.
    try:
        skip = isolated_islands(topic_map)
    except Exception:
        skip = set()

    islands, weights = [], []
    for c in sorted(tm["cluster"].unique()):
        if int(c) in skip:
            continue
        part = tm[tm["cluster"] == c].sort_values("citations", ascending=False)
        rel = float(part["relevance"].mean()) if "relevance" in part.columns else 1.0
        islands.append((int(c), part))
        weights.append(rel * np.sqrt(len(part)))

    # Rounds visit the islands in order of weight, not in order of cluster id. Without this
    # the first entries came out in whatever order HDBSCAN numbered the clusters, so the
    # third thing he was told to read was a paper on BaTiO3 piezoelectrics. Reading breadth
    # first is the point; reading it in an arbitrary order is not.
    ranked = sorted(zip(islands, weights), key=lambda x: -x[1])
    islands = [i for i, _ in ranked]
    weights = [w for _, w in ranked]

    total = sum(weights) or 1.0
    quota = {}
    for (c, part), w in zip(islands, weights):
        share = int(round(budget * w / total))
        ceiling = max(1, _must_count(part["citations"].tolist()))
        quota[c] = max(1, min(share, ceiling, len(part)))

    picked = {c: part.head(quota[c]) for c, part in islands}
    rows, round_i = [], 0
    while sum(len(v) for v in picked.values()) > len(rows):
        for c, part in islands:
            if round_i < len(picked[c]):
                r = picked[c].iloc[round_i].copy()
                r["island"] = str(part["label"].iloc[0])
                r["island_rank"] = round_i + 1
                rows.append(r)
        round_i += 1

    out = __import__("pandas").DataFrame(rows).reset_index(drop=True)
    out.insert(0, "read_order", range(1, len(out) + 1))
    return out
