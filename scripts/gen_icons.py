#!/usr/bin/env python3
"""Draw the deck's line icons (no SVG rasterizer needed) into inputs/icons/*.png.

  ./jev/bin/python scripts/gen_icons.py
Monochrome teal line icons on a transparent 256x256 canvas, drawn with Pillow.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from zeroops import paths  # noqa: E402

S, MG, W = 256, 46, 15
TEAL = (0, 127, 130, 255)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

ICONS: dict[str, object] = {}


def icon(fn):
    ICONS[fn.__name__] = fn
    return fn


def canvas():
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def glyph(d, ch, size=170):
    try:
        f = ImageFont.truetype(FONT, size)
    except Exception:
        f = ImageFont.load_default()
    box = d.textbbox((0, 0), ch, font=f)
    d.text(((S - (box[2] - box[0])) / 2 - box[0], (S - (box[3] - box[1])) / 2 - box[1]), ch, font=f, fill=TEAL)


@icon
def network():
    im, d = canvas()
    pts = [(S // 2, 58), (64, 198), (192, 198)]
    for x, y in pts:
        d.ellipse([x - 25, y - 25, x + 25, y + 25], outline=TEAL, width=W)
    for a, b in ((0, 1), (1, 2), (2, 0)):
        d.line([pts[a], pts[b]], fill=TEAL, width=W)
    return im


@icon
def flow():
    im, d = canvas()
    for i, x in enumerate((18, 96, 174)):
        d.rounded_rectangle([x, 100, x + 60, 156], radius=12, outline=TEAL, width=W)
        if i < 2:
            d.line([x + 66, 128, x + 96, 128], fill=TEAL, width=W)
            d.polygon([(x + 96, 118), (x + 110, 128), (x + 96, 138)], fill=TEAL)
    return im


@icon
def target():
    im, d = canvas()
    for r in (96, 62, 28):
        d.ellipse([S // 2 - r, S // 2 - r, S // 2 + r, S // 2 + r], outline=TEAL, width=W)
    d.ellipse([S // 2 - 8, S // 2 - 8, S // 2 + 8, S // 2 + 8], fill=TEAL)
    return im


@icon
def alert():
    im, d = canvas()
    d.polygon([(128, 34), (232, 214), (24, 214)], outline=TEAL, width=W)
    d.line([128, 104, 128, 162], fill=TEAL, width=W)
    d.ellipse([120, 182, 136, 198], fill=TEAL)
    return im


@icon
def chart():
    im, d = canvas()
    d.line([40, 216, 224, 216], fill=TEAL, width=W)
    for x, h in ((58, 60), (110, 110), (162, 168)):
        d.rounded_rectangle([x, 216 - h, x + 30, 216], radius=8, fill=TEAL)
    return im


@icon
def link():
    im, d = canvas()
    d.rounded_rectangle([30, 96, 140, 160], radius=32, outline=TEAL, width=W)
    d.rounded_rectangle([116, 96, 226, 160], radius=32, outline=TEAL, width=W)
    return im


@icon
def gauge():
    im, d = canvas()
    d.arc([40, 60, 216, 236], start=180, end=360, fill=TEAL, width=W)
    d.line([128, 158, 196, 108], fill=TEAL, width=W)
    d.ellipse([116, 146, 140, 170], fill=TEAL)
    return im


@icon
def path():
    im, d = canvas()
    d.line([36, 208, 96, 160, 150, 196, 214, 96], fill=TEAL, width=W, joint="curve")
    d.polygon([(214, 40), (214, 96), (166, 76)], fill=TEAL)
    return im


@icon
def checklist():
    im, d = canvas()
    for i, y in enumerate((60, 118, 176)):
        d.rounded_rectangle([34, y, 62, y + 28], radius=6, outline=TEAL, width=12)
        d.line([72, y + 14, 218, y + 14], fill=TEAL, width=12)
        d.line([40, y + 14, 48, y + 22, 62, y + 4], fill=TEAL, width=10)
    return im


@icon
def grid():
    im, d = canvas()
    for x in (34, 134):
        for y in (34, 134):
            d.rounded_rectangle([x, y, x + 88, y + 88], radius=12, outline=TEAL, width=W)
    return im


@icon
def shield():
    im, d = canvas()
    d.polygon([(128, 30), (218, 66), (218, 132), (128, 226), (38, 132), (38, 66)], outline=TEAL, width=W)
    d.line([92, 128, 118, 156, 168, 96], fill=TEAL, width=W, joint="curve")
    return im


@icon
def question():
    im, d = canvas()
    d.ellipse([28, 28, 228, 228], outline=TEAL, width=W)
    glyph(d, "?")
    return im


@icon
def scale():
    im, d = canvas()
    d.line([128, 44, 128, 200], fill=TEAL, width=W)
    d.line([50, 78, 206, 78], fill=TEAL, width=W)
    d.line([60, 200, 196, 200], fill=TEAL, width=W)
    d.arc([26, 78, 106, 150], start=0, end=180, fill=TEAL, width=W)
    d.arc([150, 78, 230, 150], start=0, end=180, fill=TEAL, width=W)
    return im


@icon
def info():
    im, d = canvas()
    d.ellipse([28, 28, 228, 228], outline=TEAL, width=W)
    glyph(d, "i")
    return im


@icon
def book():
    im, d = canvas()
    d.rounded_rectangle([30, 56, 226, 200], radius=14, outline=TEAL, width=W)
    d.line([128, 56, 128, 200], fill=TEAL, width=W)
    return im


@icon
def play():
    im, d = canvas()
    d.ellipse([28, 28, 228, 228], outline=TEAL, width=W)
    d.polygon([(104, 82), (104, 174), (180, 128)], fill=TEAL)
    return im


@icon
def spark():
    im, d = canvas()
    d.polygon([(128, 24), (152, 104), (232, 128), (152, 152), (128, 232), (104, 152), (24, 128), (104, 104)], fill=TEAL)
    return im


@icon
def person():
    im, d = canvas()
    d.ellipse([86, 30, 170, 114], outline=TEAL, width=W)
    d.arc([46, 140, 210, 304], start=180, end=360, fill=TEAL, width=W)
    d.line([46, 222, 210, 222], fill=TEAL, width=W)
    return im


@icon
def clock():
    im, d = canvas()
    d.ellipse([28, 28, 228, 228], outline=TEAL, width=W)
    d.line([128, 128, 128, 68], fill=TEAL, width=W)
    d.line([128, 128, 172, 156], fill=TEAL, width=W)
    d.ellipse([118, 118, 138, 138], fill=TEAL)
    return im


@icon
def bell():
    im, d = canvas()
    d.arc([66, 40, 190, 164], start=180, end=360, fill=TEAL, width=W)
    d.line([66, 102, 58, 180], fill=TEAL, width=W)
    d.line([190, 102, 198, 180], fill=TEAL, width=W)
    d.line([34, 184, 222, 184], fill=TEAL, width=W)
    d.ellipse([110, 200, 146, 236], fill=TEAL)
    return im


@icon
def search():
    im, d = canvas()
    d.ellipse([36, 36, 166, 166], outline=TEAL, width=W)
    d.line([150, 150, 220, 220], fill=TEAL, width=W + 8)
    return im


@icon
def fork():
    im, d = canvas()
    d.line([30, 128, 110, 128], fill=TEAL, width=W)
    d.line([110, 128, 190, 62], fill=TEAL, width=W)
    d.line([110, 128, 190, 194], fill=TEAL, width=W)
    d.ellipse([94, 112, 126, 144], fill=TEAL)
    d.polygon([(178, 42), (224, 40), (206, 82)], fill=TEAL)
    d.polygon([(178, 214), (224, 216), (206, 174)], fill=TEAL)
    return im


def main() -> int:
    paths.ICONS.mkdir(parents=True, exist_ok=True)
    for name, fn in ICONS.items():
        fn().save(paths.ICONS / f"{name}.png")
    print(f"wrote {len(ICONS)} icons to {paths.rel(paths.ICONS)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
