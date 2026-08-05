"""Does reading a topic depend on WHEN you ask, or only on WHICH slug you ask for?

Reproduces the hazard in one process: config still points at topic A (as it does after a
full run) while a cache miss asks for topic B's data - which is what a fragment rerun can
do, since it does not re-execute the top of the script. A pure loader returns B; the buggy
one returns A and caches it under B's key.
"""
import io
import sys

sys.path.insert(0, r"C:\Users\Bruce Wayne\Documents\Master Thesis AI")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import pandas as pd

from froth import cluster, config, embed

rows = [l.split(",", 1) for l in
        config.TOPICS_REGISTRY.read_text(encoding="utf-8").splitlines() if "," in l]
other_slug, other_title = next(
    (s, t) for s, t in rows
    if (config.ROOT / "2_Datos" / "topics" / s / "processed" / "papers.parquet").exists())


def titles(slug):
    p = config.paths_for(slug)["processed"] / "papers.parquet"
    return set(pd.read_parquet(p, columns=["title"])["title"].head(20))


truth_default = titles(config.DEFAULT_SLUG)
truth_other = titles(other_slug)
print(f"default : {len(truth_default)} títulos de muestra")
print(f"otro    : {other_slug[:44]} -> {len(truth_other)}")
print(f"difieren: {truth_default != truth_other}\n")


def load_like_app(slug):
    """The body of app.load_data as it stands now (without Streamlit's cache)."""
    paths = config.paths_for(slug)
    df = pd.read_parquet(paths["processed"] / "papers.parquet")
    embed.load_embeddings(paths["embeddings"])
    cluster.load_topic_map(paths["processed"])
    return set(df["title"].head(20))


# Globals point at the DEFAULT topic, then ask for the OTHER one.
config.set_topic(config.DEFAULT_TOPIC)
got = load_like_app(other_slug)

print("--- pidiendo el OTRO topic con config apuntando al default ---")
if got == truth_other:
    print("PASS - devolvió los papers del topic pedido")
elif got == truth_default:
    print("FAIL - devolvió los del DEFAULT bajo el slug del otro")
else:
    print("FAIL - devolvió otra cosa")

# And the reverse direction, which the v1 test did not cover.
config.set_topic(other_title)
back = load_like_app(config.DEFAULT_SLUG)
print("\n--- y al revés: pidiendo el default con config en el otro ---")
print("PASS - devolvió el default" if back == truth_default else "FAIL")
