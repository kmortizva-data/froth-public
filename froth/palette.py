"""
palette.py - hierarchical color for the Atlas (Phase D).

Batman's idea: in the overview each TERRITORY (top-level cluster) owns one HUE; when you
zoom into a hub, that same hue is KEPT and its sub-clusters become TONES of it (lightness
ramped) - "same theme, different facets". So color itself encodes the hierarchy, and the
reader never loses track of which subtopic they are inside.

Two rules that matter here:
- territory_hues(n): n well-separated colors so 50-80 territories each get their OWN color.
  (visualize.PALETTE has 10 colors recycled with `% len` - past ~10 clusters colors
  repeat, and two same-colored blobs read as "the same subtopic". This replaces that.)
- subtones(base_hex, k): k tones of the SAME hue, with k = the number of sub-clusters
  (data-driven, not a fixed list) - Batman's "calculated each time" knob (rule 9).

Colors are built in HSL via the stdlib `colorsys` (no new dependency): we fix the HUE and
ramp LIGHTNESS, so every tone in a family is unmistakably the same color, just lighter or
darker, and all stay readable on the dark #18181b canvas. (A perceptual space like HSLuv
would make the lightness steps even more uniform - noted as a drop-in upgrade if we ever
add the dep; kept out for now to avoid install friction on the corporate network.)
"""
import colorsys

# The signature flotation blue (#378ADD in visualize.PALETTE) sits near hue 210 deg; we
# start the color wheel there so the Atlas still "tastes" like Froth even with many colors.
BRAND_HUE_ANCHOR = 210.0
# Golden-angle steps spread consecutive cluster ids as far apart on the wheel as possible,
# so neighboring subtopics rarely land on look-alike hues (a standard categorical-palette
# trick; far better than evenly slicing the circle, which bunches greens together).
GOLDEN_ANGLE = 137.508
DARK_BG = "#18181b"


def _hex(r: float, g: float, b: float) -> str:
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def _to_rgb01(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def territory_hues(n: int, sat: float = 0.62, light: float = 0.60) -> list[str]:
    """n distinct colors for the top-level territories - one hue each, walked around the
    wheel by the golden angle from the brand blue. Adjacent ids get well-separated colors."""
    hues = []
    for i in range(max(n, 1)):
        hue = ((BRAND_HUE_ANCHOR + GOLDEN_ANGLE * i) % 360.0) / 360.0
        hues.append(_hex(*colorsys.hls_to_rgb(hue, light, sat)))
    return hues


def subtones(base_hex: str, k: int, lo: float = 0.40, hi: float = 0.76) -> list[str]:
    """k tones of base_hex's OWN hue, lightness ramped lo->hi (the readable band on the dark
    canvas), saturation kept high. k = number of sub-clusters in the hub (data-driven).
    Returns dark -> light so the ramp reads as one coherent family."""
    hue, _l, s = colorsys.rgb_to_hls(*_to_rgb01(base_hex))
    s = max(s, 0.52)                                    # keep facets vivid, never washed out
    out = []
    for i in range(max(k, 1)):
        frac = i / (k - 1) if k > 1 else 0.5
        out.append(_hex(*colorsys.hls_to_rgb(hue, lo + (hi - lo) * frac, s)))
    return out


def hub_color_array(base_hex: str, sub_labels) -> list[str]:
    """Per-point colors for a hub's local map: every paper takes the subtone of its
    sub-cluster; noise (-1) is a muted gray. `sub_labels` is one label per paper (as from
    cluster.cluster_points). The whole hub therefore stays inside the parent's hue."""
    uniq = sorted(c for c in set(sub_labels) if c != -1)
    tones = dict(zip(uniq, subtones(base_hex, len(uniq))))
    return ["#5F5E5A" if c == -1 else tones[c] for c in sub_labels]


if __name__ == "__main__":
    print("territory_hues(8):")
    for c in territory_hues(8):
        print(f"  {c}")
    print("\nsubtones of the brand blue #378ADD into 6 facets:")
    for c in subtones("#378ADD", 6):
        print(f"  {c}")
