"""
make_infographics.py - render the 6 LinkedIn carousel slides with code.

WHY CODE INSTEAD OF AN IMAGE GENERATOR: pixel-exact brand identity, no watermark
to crop, English copy with zero spelling roulette, and regenerable forever with
one command. Flat Linear-style slides are what 2D drawing does best.

Run:
    .venv\\Scripts\\python.exe packaging\\make_infographics.py

Output: assets/linkedin/slide_1.png ... slide_6.png (1080x1080).
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "linkedin"

SIZE = 1080
FRAME_MARGIN = 64                 # breathing room outside the frame
PAD = 72                          # padding inside the frame

BG_OUT = "#0e0e10"
BG_IN = "#18181b"
BORDER = "#3f3f46"
WHITE = "#fafafa"
GRAY = "#a1a1aa"
INDIGO = "#6366f1"
VIOLET = "#8b5cf6"
TEAL = "#14b8a6"
BLUE = "#378ADD"
RED = "#e24b4a"

FONTS = Path("C:/Windows/Fonts")


def font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    name = {"regular": "segoeui.ttf", "semibold": "seguisb.ttf",
            "bold": "segoeuib.ttf"}[weight]
    return ImageFont.truetype(str(FONTS / name), size)


def new_slide() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (SIZE, SIZE), BG_OUT)
    d = ImageDraw.Draw(img)
    f0, f1 = FRAME_MARGIN, SIZE - FRAME_MARGIN
    d.rounded_rectangle([f0, f1 - (f1 - f0), f1, f1], radius=28,
                        fill=BG_IN, outline=BORDER, width=2)
    return img, d


def bubbles(img: Image.Image, spots: list[tuple[int, int, int, str, int]]) -> None:
    """spots: (x, y, radius, color, alpha 0-255). Glossy look (Batman preferred
    the earlier bubbles): translucent body, bright rim, white top-left shine."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    dl = ImageDraw.Draw(layer)
    for x, y, r, color, a in spots:
        rgb = tuple(int(color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        dl.ellipse([x - r, y - r, x + r, y + r], fill=rgb + (max(60, a - 90),),
                   outline=rgb + (min(255, a + 60),), width=max(2, r // 6))
        hl = max(2, int(r * 0.30))
        hx, hy = x - int(r * 0.38), y - int(r * 0.38)
        dl.ellipse([hx - hl, hy - hl, hx + hl, hy + hl],
                   fill=(255, 255, 255, 150))
    img.paste(layer, (0, 0), layer)


def edge_bubbles(img: Image.Image, side: str = "right") -> None:
    xs = SIZE - FRAME_MARGIN - 34 if side == "right" else FRAME_MARGIN + 34
    pts = [(xs, 170, 13, INDIGO, 150), (xs - 18, 260, 6, TEAL, 140),
           (xs + 6, 360, 9, TEAL, 120), (xs - 8, 520, 5, VIOLET, 130),
           (xs, 700, 11, INDIGO, 110), (xs - 14, 830, 6, TEAL, 130)]
    bubbles(img, pts)


def wordmark(d: ImageDraw.ImageDraw) -> None:
    f = font(42, "bold")
    lit_w = d.textlength("Lit", font=f)
    map_w = d.textlength("Map", font=f)
    x1 = SIZE - FRAME_MARGIN - PAD // 2
    y = SIZE - FRAME_MARGIN - 76
    d.text((x1 - lit_w - map_w, y), "Lit", font=f, fill=WHITE)
    d.text((x1 - map_w, y), "Map", font=f, fill=VIOLET)


def draw_x(d: ImageDraw.ImageDraw, x: int, y: int, s: int = 13, w: int = 6) -> None:
    d.line([x - s, y - s, x + s, y + s], fill=RED, width=w)
    d.line([x - s, y + s, x + s, y - s], fill=RED, width=w)


def draw_check(d: ImageDraw.ImageDraw, x: int, y: int, s: int = 14, w: int = 6) -> None:
    d.line([x - s, y, x - s // 3, y + s * 2 // 3], fill=TEAL, width=w)
    d.line([x - s // 3, y + s * 2 // 3, x + s, y - s * 2 // 3], fill=TEAL, width=w)


def paper_icon(d: ImageDraw.ImageDraw, x: int, y: int, w: int = 22, h: int = 28,
               color: str = "#d4d4d8") -> None:
    d.rounded_rectangle([x, y, x + w, y + h], radius=3, fill=color)
    for i in range(3):
        d.line([x + 4, y + 7 + i * 7, x + w - 4, y + 7 + i * 7], fill="#71717a", width=2)


def multiline(d: ImageDraw.ImageDraw, x: int, y: int, lines: list[str],
              f: ImageFont.FreeTypeFont, fill: str, leading: int) -> int:
    for ln in lines:
        d.text((x, y), ln, font=f, fill=fill)
        y += leading
    return y


# ---------------------------------------------------------------- slide 1
def slide_1() -> None:
    img, d = new_slide()
    edge_bubbles(img, "right")
    edge_bubbles(img, "left")
    d = ImageDraw.Draw(img)
    x = FRAME_MARGIN + PAD
    y = FRAME_MARGIN + PAD + 10
    y = multiline(d, x, y, ["500 papers.", "One thesis. Zero map."],
                  font(76, "bold"), WHITE, 96) + 46

    items = [["Keyword search misses papers", "that say it differently"],
             ["ChatGPT invents references", "that do not exist"],
             ["You cite 20 papers and hope", "the key one is there"]]
    for lines in items:
        draw_x(d, x + 16, y + 24)
        multiline(d, x + 58, y, lines, font(38), GRAY, 48)
        y += 48 * len(lines) + 30

    y += 14
    multiline(d, x, y, ["Froth charts the whole field", "before you write a single line."],
              font(44, "semibold"), TEAL, 58)
    wordmark(d)
    img.save(OUT / "slide_1.png")


# ---------------------------------------------------------------- slide 2
def slide_2() -> None:
    img, d = new_slide()
    x0 = FRAME_MARGIN + PAD
    d.text((x0, FRAME_MARGIN + PAD), "From 500 papers to one map",
           font=font(58, "bold"), fill=WHITE)

    # flotation cell on the left
    cx0, cy0, cx1, cy1 = x0, 320, x0 + 300, 810
    d.rounded_rectangle([cx0, cy0, cx1, cy1], radius=18, outline=BORDER, width=3)
    # Feed: a dense pile of papers at the bottom, like ore entering the cell.
    for i in range(6):
        paper_icon(d, cx0 + 18 + i * 46, cy1 - 42, 20, 26)
    for i in range(5):
        paper_icon(d, cx0 + 40 + i * 46, cy1 - 74, 20, 26)
    for i in range(6):
        paper_icon(d, cx0 + 18 + i * 46, cy1 - 106, 20, 26)
    rng = [(70, 620, 21, INDIGO), (150, 660, 16, TEAL), (225, 610, 24, VIOLET),
           (105, 520, 18, BLUE), (195, 500, 15, INDIGO), (60, 430, 16, TEAL),
           (240, 420, 20, VIOLET), (150, 380, 17, BLUE)]
    bubbles(img, [(cx0 + bx, by, r, c, 215) for bx, by, r, c in rng])
    d = ImageDraw.Draw(img)
    clusters = [(cx0 + 70, 355, INDIGO), (cx0 + 160, 340, TEAL), (cx0 + 245, 360, VIOLET)]
    bubbles(img, [(x, y, 34, c, 245) for x, y, c in clusters])
    d = ImageDraw.Draw(img)
    for x, y, _ in clusters:
        paper_icon(d, x - 10, y - 13, 20, 26)

    # steps on the right
    sx = cx1 + 56
    y = 300
    steps = [("1. Harvest", ["Papers collected from open", "science databases"]),
             ("2. Understand", ["Every abstract becomes coordinates:", "similar meaning, similar spot"]),
             ("3. Cluster", ["Papers group into named subtopics,", "like bubbles in froth"]),
             ("4. Float", ["The relevant literature", "rises to the top"])]
    for title, body in steps:
        d.text((sx, y), title, font=font(33, "semibold"), fill=WHITE)
        y += 44
        y = multiline(d, sx, y, body, font(28), GRAY, 35) + 16

    multiline(d, x0, 858, ["In flotation, value rides bubbles.",
                           "In Froth, relevant papers do."],
              font(38, "semibold"), TEAL, 50)
    wordmark(d)
    img.save(OUT / "slide_2.png")


# ---------------------------------------------------------------- slide 3
def slide_3() -> None:
    img, d = new_slide()
    d.text((SIZE // 2, FRAME_MARGIN + PAD - 6), "Why another literature tool?",
           font=font(54, "bold"), fill=WHITE, anchor="ma")

    # Honest matrix (Batman's spec): competitors keep the checks they earn;
    # Froth simply earns more of them.
    rows = [(["Interactive map of", "a topic's papers"], [1, 1, 1, 0]),
            (["Free to use,", "no premium wall"], [1, 0, 1, 0]),
            (["Writes a literature", "review draft"], [1, 0, 0, 1]),
            (["Maps papers by", "MEANING, not citations"], [1, 0, 0, 0]),
            (["Every cited sentence is", "real (nothing invented)"], [1, 0, 0, 0]),
            (["Runs 100% on your PC,", "open source (MIT)"], [1, 0, 0, 0])]
    cols = ["Froth", "Connected\nPapers", "Research-\nRabbit", "Elicit"]

    left = FRAME_MARGIN + PAD - 20
    right = SIZE - FRAME_MARGIN - PAD + 20
    feat_w = 330
    col_w = (right - left - feat_w) // 4
    top = 330
    row_h = 96

    # Froth column highlight
    hx0 = left + feat_w
    d.rounded_rectangle([hx0 + 10, top - 92, hx0 + col_w - 10, top + row_h * 6 + 6],
                        radius=14, fill="#232327")
    for i, name in enumerate(cols):
        cx = left + feat_w + col_w * i + col_w // 2
        parts = name.split("\n")
        y0 = top - 82 + (14 if len(parts) == 1 else 0)
        for j, part in enumerate(parts):
            d.text((cx, y0 + j * 30), part, font=font(23, "semibold"),
                   fill=WHITE if i == 0 else GRAY, anchor="ma")
    for r, (lines, marks) in enumerate(rows):
        y = top + r * row_h
        if r:
            d.line([left, y, right, y], fill="#27272a", width=2)
        multiline(d, left + 4, y + row_h // 2 - (18 * len(lines)),
                  lines, font(27), WHITE, 36)
        for c, has_it in enumerate(marks):
            cx = left + feat_w + col_w * c + col_w // 2
            cy = y + row_h // 2
            if has_it:
                draw_check(d, cx, cy)
            else:
                draw_x(d, cx, cy, 11, 5)
    wordmark(d)
    img.save(OUT / "slide_3.png")


# ---------------------------------------------------------------- slide 4
def slide_4() -> None:
    img, d = new_slide()
    x0 = FRAME_MARGIN + PAD
    d.text((SIZE // 2, FRAME_MARGIN + PAD - 8), "The brain we borrowed: SPECTER",
           font=font(52, "bold"), fill=WHITE, anchor="ma")

    # doc -> network -> scatter
    cy = 350
    paper_icon(d, x0 + 30, cy - 45, 64, 84, "#e4e4e7")
    d.line([x0 + 110, cy, x0 + 170, cy], fill=BORDER, width=4)
    nx = x0 + 300
    nodes = [(nx - 90, cy - 70), (nx - 90, cy), (nx - 90, cy + 70),
             (nx, cy - 40), (nx, cy + 40), (nx + 90, cy)]
    for a in nodes[:3]:
        for b in nodes[3:5]:
            d.line([a, b], fill=INDIGO, width=3)
    for b in nodes[3:5]:
        d.line([b, nodes[5]], fill=INDIGO, width=3)
    for x, y in nodes:
        d.ellipse([x - 14, y - 14, x + 14, y + 14], outline=INDIGO, width=4, fill=BG_IN)
    d.line([nx + 110, cy, nx + 170, cy], fill=BORDER, width=4)

    import random
    random.seed(7)
    for gx, gy, color in [(x0 + 620, cy - 80, TEAL), (x0 + 760, cy - 30, VIOLET),
                          (x0 + 660, cy + 80, BLUE)]:
        for _ in range(9):
            px = gx + random.randint(-46, 46)
            py = gy + random.randint(-34, 34)
            d.ellipse([px - 7, py - 7, px + 7, py + 7], fill=color)
    gx, gy = x0 + 634, cy - 66
    d.ellipse([gx - 11, gy - 11, gx + 11, gy + 11], fill=WHITE, outline=TEAL, width=4)

    y = 560
    y = multiline(d, x0, y, ["A language model pre-trained on millions",
                             "of scientific papers"], font(40, "semibold"), WHITE, 52)
    y = multiline(d, x0, y + 6, ["By the Allen Institute for AI (Cohan et al., 2020)"],
                  font(30), GRAY, 40) + 18
    y = multiline(d, x0, y, ["Its trick: papers that cite each other were",
                             "taught to land close together on the map"],
                  font(34), WHITE, 46) + 24
    multiline(d, x0, y, ["Like XRD tells you the mineral phase,",
                         "SPECTER tells you what a paper is about."],
              font(36, "semibold"), TEAL, 48)
    wordmark(d)
    img.save(OUT / "slide_4.png")


# ---------------------------------------------------------------- slide 5
def slide_5() -> None:
    img, d = new_slide()
    x0 = FRAME_MARGIN + PAD
    d.text((SIZE // 2, FRAME_MARGIN + PAD - 8), "Fine-tuning: teaching the brain",
           font=font(52, "bold"), fill=WHITE, anchor="ma")
    d.text((SIZE // 2, FRAME_MARGIN + PAD + 58), "OUR dialect",
           font=font(52, "bold"), fill=WHITE, anchor="ma")

    import random
    random.seed(11)
    cy = 400
    for label, gx, mixed in [("generic", x0 + 160, True),
                             ("fine-tuned", x0 + 640, False)]:
        d.rounded_rectangle([gx - 130, cy - 120, gx + 130, cy + 120], radius=16,
                            outline=BORDER, width=3)
        d.text((gx, cy + 140), label, font=font(30, "semibold"), fill=GRAY, anchor="ma")
        colors = [TEAL, VIOLET, BLUE]
        if mixed:
            for _ in range(27):
                px = gx + random.randint(-112, 112)
                py = cy + random.randint(-102, 102)
                d.ellipse([px - 7, py - 7, px + 7, py + 7],
                          fill=random.choice(colors))
        else:
            for (ox, oy), color in zip([(-62, -48), (58, -34), (-6, 62)], colors):
                for _ in range(9):
                    px = gx + ox + random.randint(-30, 30)
                    py = cy + oy + random.randint(-26, 26)
                    d.ellipse([px - 7, py - 7, px + 7, py + 7], fill=color)
    ax = x0 + 355
    d.line([ax, cy, ax + 90, cy], fill=WHITE, width=5)
    d.polygon([(ax + 90, cy - 12), (ax + 90, cy + 12), (ax + 112, cy)], fill=WHITE)

    y = 600
    y = multiline(d, x0, y, ["We re-trained a copy of SPECTER on 1,290",
                             "mineral-processing papers"],
                  font(37, "semibold"), WHITE, 46)
    y = multiline(d, x0, y + 2, ["83 seconds on a laptop GPU, no labels needed"],
                  font(29), GRAY, 36) + 12
    y = multiline(d, x0, y, ["Result: sharper separation of OUR topics, like",
                             "fines flotation vs collector chemistry"],
                  font(32), WHITE, 40) + 14
    multiline(d, x0, y, ["In a blind test, the author picked the",
                         "fine-tuned model, not knowing which was which."],
              font(32, "semibold"), TEAL, 40)
    wordmark(d)
    img.save(OUT / "slide_5.png")


# ---------------------------------------------------------------- slide 6
def slide_6() -> None:
    img, d = new_slide()
    xs = FRAME_MARGIN + 40
    bubbles(img, [(xs, 220, 18, INDIGO, 160), (xs + 26, 320, 10, TEAL, 150),
                  (xs - 4, 430, 13, VIOLET, 140), (xs + 18, 560, 8, TEAL, 150),
                  (xs + 4, 690, 15, INDIGO, 120), (xs + 22, 800, 7, VIOLET, 140)])
    d = ImageDraw.Draw(img)
    x = FRAME_MARGIN + PAD + 40
    y = FRAME_MARGIN + PAD + 6
    y = multiline(d, x, y, ["Free to run.", "Private by design."],
                  font(72, "bold"), WHITE, 90) + 44

    items = [["OpenAlex: open catalog of 250M papers, free"],
             ["ScienceDirect / Scopus: free API key", "with your university account"],
             ["Semantic Scholar and Crossref: free"],
             ["AI polish runs on YOUR graphics card;", "nothing leaves your machine"],
             ["Open source under the MIT license: free for", "anyone to use, modify and share"]]
    for lines in items:
        draw_check(d, x + 14, y + 22, 12, 5)
        multiline(d, x + 52, y, lines, font(33), "#e4e4e7", 43)
        y += 43 * len(lines) + 26

    d.text((x, y + 16), "github.com/kmortizva-data/froth",
           font=font(43, "bold"), fill=WHITE)
    wordmark(d)
    img.save(OUT / "slide_6.png")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for fn in (slide_1, slide_2, slide_3, slide_4, slide_5, slide_6):
        fn()
        print("rendered", fn.__name__)
    print(f"\nDone -> {OUT}")
