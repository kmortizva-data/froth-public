# Optional: local LLM polish for the review draft (Ollama)

Froth's review draft is **extractive** (real sentences, traceable citations) and
works fully without any LLM. If you want smoother prose, Froth can ask a **local**
model to rewrite each paragraph - and it verifies that every citation survives
exactly; any section that fails verification keeps its extractive original.

Why local (Ollama) instead of an API: free, private, works offline, no keys.

## Setup (one time, ~10 minutes)

1. Download and install Ollama: https://ollama.com/download (Windows installer).
2. Open a terminal and pull a model (pick ONE):
   ```
   ollama pull llama3.1:8b     # ~4.9 GB, best quality on an 8 GB GPU
   ollama pull qwen2.5:7b      # ~4.7 GB, alternative
   ```
3. Keep Ollama running (it starts a local server on `localhost:11434`).

That's it - the "Polish with a local LLM" panel in the Review tab detects the
server automatically and lists your installed models.

## Notes

- First polish of a draft takes a minute or two (the model warms up).
- The polished draft is a SEPARATE download; the extractive original is always
  kept and remains the default.
- Nothing ever leaves your machine.
