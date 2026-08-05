# Get your API keys (5–10 minutes, all free)

Froth works out of the box with public sources, but connecting your own accounts makes
harvests **bigger, faster and steadier**. Keys are stored ONLY on your machine (a
gitignored `.froth_keys` file) - they never leave your computer.

| Source | Needed? | What it unlocks |
|---|---|---|
| OpenAlex | Recommended | Uninterrupted pulls ($1/day free budget ≈ 1,000 searches) |
| Semantic Scholar | Optional | Steady access (keyless tier is heavily rate-limited) |
| Elsevier / Scopus | Optional (university) | Scopus results, often fresher than anywhere else |
| Crossref | No key - just your email | Publisher metadata at scale |

## 1. OpenAlex (~2 min)

1. Go to **https://openalex.org/settings/api**
2. Sign in (any email works; institutional is fine).
3. Copy your key.

## 2. Semantic Scholar (~3 min + approval wait)

1. Go to **https://www.semanticscholar.org/product/api**
2. Click **Request an API key** and fill the short form
   (purpose: e.g. *"academic literature mapping for my studies"*).
3. The key arrives **by email** - sometimes instantly, sometimes in a few days.
   Froth works fine while you wait (just slower on this source).
4. Their free tier allows **1 request/second**; Froth already paces itself below that.

## 3. Elsevier / Scopus (~3 min, needs a university subscription)

1. Go to **https://dev.elsevier.com**
2. Click **I want an API Key** and sign in with your institutional Elsevier account
   (the one you use for ScienceDirect/Scopus - create it with your university email
   if you don't have one).
3. **My API Key → Create API Key**: any label, website `http://localhost`, accept the
   agreements - the key appears instantly.
4. Note: quotas and some content follow your institution - if results look thin,
   try from campus network or VPN.

## Where to put them

**Easiest - inside the app**: sidebar → **Connect institutional account** → paste each
key → **Save connections**. Done.

**Or by hand**: create a file named `.froth_keys` next to `app.py`:

```
INSTITUTIONAL_EMAIL=you@university.edu
SEMANTIC_SCHOLAR_API_KEY=your-s2-key
ELSEVIER_API_KEY=your-elsevier-key
```

and your OpenAlex key in a one-line file named `.openalex_key`.

## Security notes

- Both files are **gitignored**: even if you fork and push this repo, your keys stay home.
- Never paste keys into issues, commits or screenshots.
- On any future hosted/web deployment, keys must live only in your browser session -
  never hand your keys to someone else's server.
