"""Generate the Windows .ico and the browser .png from the Froth mark.

Run it after editing assets/froth_mark.svg so the raster icons stay in step:

    .venv\\Scripts\\python.exe packaging\\make_icons.py

The geometry is duplicated here on purpose. Rasterising the SVG would need cairosvg,
which pulls a native Cairo build that is a nuisance to install on Windows and would
become a dependency of a project that otherwise needs none for this. The shapes are
six circles and five lines: cheap to keep in sync, and the SVG stays the source of
truth for anything vector (README, web, print).
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

PLATE = "#1f1f23"
EDGE = "#52525b"
BRIDGE_FILL = "#27272a"
AMBER = "#f59e0b"

# (cx, cy, r, fill) in the 64x64 space of assets/froth_mark.svg
BUBBLES = [
    (20, 24, 8, "#6366f1"),
    (33, 17, 5, "#8b5cf6"),
    (45, 27, 5.6, "#378ADD"),
    (43, 44, 4.2, "#14b8a6"),
]
EDGES = [(20, 24, 33, 17), (20, 24, 27, 40), (33, 17, 45, 27),
         (27, 40, 43, 44), (45, 27, 43, 44)]
HIGHLIGHT = (17.6, 21.4, 2.5)
BRIDGE = (27, 40, 6.4)


def render(size: int, plate: bool = True) -> Image.Image:
    """Draw the mark at `size` px. Supersampled 8x, then reduced: Pillow has no
    antialiasing of its own, so shapes drawn at final size come out with hard stair
    steps - visible and ugly at 16px, which is where the icon lives most of the time."""
    ss = 8
    n = size * ss
    k = n / 64.0                                   # 64 is the SVG's coordinate space
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    if plate:
        d.rounded_rectangle([0, 0, n - 1, n - 1], radius=int(15 * k), fill=PLATE)

    for x1, y1, x2, y2 in EDGES:
        d.line([x1 * k, y1 * k, x2 * k, y2 * k], fill=EDGE,
               width=max(1, int(1.3 * k)))

    def disc(cx, cy, r, fill=None, outline=None, width=0):
        d.ellipse([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k],
                  fill=fill, outline=outline, width=width)

    for cx, cy, r, fill in BUBBLES:
        disc(cx, cy, r, fill=fill)

    hx, hy, hr = HIGHLIGHT                         # the bubble-film glint
    disc(hx, hy, hr, fill=(255, 255, 255, 77))

    # The bridge paper: a hollow bubble in an amber ring. The .ico is drawn as a solid
    # ring rather than the SVG's dashes - at 16px a dashed 2px stroke turns into three
    # stray pixels, so it reads as noise instead of as a marked paper.
    bx, by, br = BRIDGE
    disc(bx, by, br, fill=BRIDGE_FILL, outline=AMBER, width=max(1, int(2.4 * k)))

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    ASSETS.mkdir(exist_ok=True)

    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [render(s) for s in sizes]
    ico = ASSETS / "froth.ico"
    frames[-1].save(ico, format="ICO",
                    sizes=[(s, s) for s in sizes], append_images=frames[:-1])
    print(f"wrote {ico.relative_to(ROOT)}  ({', '.join(str(s) for s in sizes)} px)")

    png = ASSETS / "froth_logo.png"
    render(256).save(png, format="PNG")
    print(f"wrote {png.relative_to(ROOT)}  (256 px, the browser tab icon)")


if __name__ == "__main__":
    main()
