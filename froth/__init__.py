"""
froth - project package.

The pipeline, in order:
    config    -> settings (topic, paths, model)
    pull      -> Phase 1: download papers
    embed     -> Phase 2: text to vectors
    cluster   -> Phase 3: bubbles and clusters
    graph     -> Phase 4: mind map
    gaps      -> Phase 5: gaps + review draft
    visualize -> render the views
"""

# --- SSL certificate fix (once, for the whole package) ---
# On Windows, Python sometimes cannot find the root certificates and fails to connect over
# HTTPS ("CERTIFICATE_VERIFY_FAILED"). truststore tells Python to use Windows' own
# certificate store, which is kept up to date. With this, any module that uses the internet
# (pull, embed, ...) connects fine.
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    # If truststore is not installed, carry on: the environment may already have certificates.
    pass

# --- UTF-8 output (once, for the whole package) ---
# Windows' console sometimes uses cp1252 and cannot print characters like "…" or accents,
# so a print with such symbols crashes. We force UTF-8 so no print fails. This matters
# because thesis titles (current and future) contain symbols and accents.
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass
