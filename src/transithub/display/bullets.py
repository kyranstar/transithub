from functools import lru_cache
from importlib.resources import files
from typing import Tuple

from PIL import Image, ImageDraw

from .fonts import BitmapFont

# Official MTA line/group colors (R, G, B)
LINE_COLORS = {
    "1": (0xEE, 0x35, 0x2E), "2": (0xEE, 0x35, 0x2E), "3": (0xEE, 0x35, 0x2E),
    "4": (0x00, 0x93, 0x3C), "5": (0x00, 0x93, 0x3C), "6": (0x00, 0x93, 0x3C),
    "7": (0xB9, 0x33, 0xAD),
    "A": (0x00, 0x39, 0xA6), "C": (0x00, 0x39, 0xA6), "E": (0x00, 0x39, 0xA6),
    "B": (0xFF, 0x63, 0x19), "D": (0xFF, 0x63, 0x19),
    "F": (0xFF, 0x63, 0x19), "M": (0xFF, 0x63, 0x19),
    "G": (0x6C, 0xBE, 0x45),
    "J": (0x99, 0x66, 0x33), "Z": (0x99, 0x66, 0x33),
    "L": (0x66, 0x68, 0x6B),   # MTA gray, darkened well below the official #A7A9AC for contrast
    "N": (0xFC, 0xCC, 0x0A), "Q": (0xFC, 0xCC, 0x0A),
    "R": (0xFC, 0xCC, 0x0A), "W": (0xFC, 0xCC, 0x0A),
    "S": (0x80, 0x80, 0x80),
}
_DEFAULT = (0x80, 0x80, 0x80)
_WHITE = (255, 255, 255)


def line_color(line: str) -> Tuple[int, int, int]:
    return LINE_COLORS.get(line.upper(), _DEFAULT)


@lru_cache(maxsize=None)
def _font() -> BitmapFont:
    path = files("transithub.display").joinpath("fonts/spleen-5x8.bdf")
    return BitmapFont.load(str(path))


@lru_cache(maxsize=None)
def make_bullet(line: str, diameter: int) -> Image.Image:
    img = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([0, 0, diameter - 1, diameter - 1], fill=line_color(line) + (255,))
    font = _font()
    label = line.upper()[:1]
    # Bold + fuller: dilate each glyph pixel into a 2x2 block for thicker strokes,
    # recenter by the dilated bounding box, and clip to the filled disc.
    bold = set()
    for px, py in font.iter_pixels(0, 0, label):
        for dx in (0, 1):
            for dy in (0, 1):
                bold.add((px + dx, py + dy))
    if bold:
        xs = [p[0] for p in bold]
        ys = [p[1] for p in bold]
        ox = (diameter - (max(xs) - min(xs) + 1)) // 2 - min(xs)
        oy = (diameter - (max(ys) - min(ys) + 1)) // 2 - min(ys)
        c = (diameter - 1) / 2.0
        rr = c * c
        for px, py in bold:
            X, Y = px + ox, py + oy
            if 0 <= X < diameter and 0 <= Y < diameter and (X - c) ** 2 + (Y - c) ** 2 <= rr:
                img.putpixel((X, Y), _WHITE + (255,))
    return img
