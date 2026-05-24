import math
import random
from typing import List, Optional, Tuple

from PIL import Image

from .bullets import _font  # cached spleen 5x8 BitmapFont

FONT = _font()


def lerp(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def text_width(text: str, scale: int = 1) -> int:
    return FONT.text_width(text) * scale


def _plot(px, x, y, w, h, s, color, scale):
    for cx, cy in FONT.iter_pixels(0, 0, s):
        for dx in range(scale):
            for dy in range(scale):
                X, Y = x + cx * scale + dx, y + cy * scale + dy
                if 0 <= X < w and 0 <= Y < h:
                    px[X, Y] = color


def draw_text(img, x, y, text, color, scale=1, outline=None):
    w, h = img.size
    px = img.load()
    if outline:
        for ox, oy in ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)):
            _plot(px, x + ox, y + oy, w, h, text, outline, scale)
    _plot(px, x, y, w, h, text, color, scale)


def degree(img, x, y, color):
    w, h = img.size
    px = img.load()
    for dx, dy in ((1, 0), (0, 1), (2, 1), (1, 2)):
        if 0 <= x + dx < w and 0 <= y + dy < h:
            px[x + dx, y + dy] = color


def gradient(img, stops: List[Tuple[float, tuple]], scale: float = 1.0,
             tint: Optional[tuple] = None, tint_amt: float = 0.0):
    w, h = img.size
    px = img.load()
    for y in range(h):
        fr = y / (h - 1)
        c = stops[-1][1]
        for k in range(len(stops) - 1):
            f0, c0 = stops[k]
            f1, c1 = stops[k + 1]
            if f0 <= fr <= f1:
                c = lerp(c0, c1, (fr - f0) / (f1 - f0))
                break
        c = tuple(int(v * scale) for v in c)
        if tint:
            c = lerp(c, tint, tint_amt)
        for x in range(w):
            px[x, y] = c


def glow_sun(img, cx, cy, r, color=(255, 226, 178), intensity=1.0):
    w, h = img.size
    px = img.load()
    R = r + 5
    for yy in range(cy - R, cy + R + 1):
        for xx in range(cx - R, cx + R + 1):
            if 0 <= xx < w and 0 <= yy < h:
                d = math.hypot(xx - cx, yy - cy)
                a = 1.0 if d <= r else (max(0.0, 1 - (d - r) / 5) * 0.8 if d <= R else 0)
                if a > 0:
                    px[xx, yy] = lerp(px[xx, yy], color, min(1.0, a * intensity))


def moon(img, cx, cy, r):
    glow_sun(img, cx, cy, r, color=(220, 226, 246))


def stars(img, frame, seed=7, count=14):
    w, h = img.size
    px = img.load()
    rnd = random.Random(seed)
    for _ in range(count):
        x, y, ph = rnd.randint(0, w - 1), rnd.randint(0, h // 2), rnd.random() * 6
        b = 0.35 + 0.65 * abs(math.sin(frame * 0.4 + ph))
        px[x, y] = lerp(px[x, y], (235, 240, 255), b)


def cloud(img, cx, cy, width, color=(184, 188, 210), alpha=0.65):
    w, h = img.size
    px = img.load()
    ch = 4.5
    for ex, ey, rx, ry in ((cx, cy, width * 0.5, ch),
                           (cx - width * 0.28, cy + 1, width * 0.3, ch * .85),
                           (cx + width * 0.28, cy + 1, width * 0.32, ch * .85)):
        for yy in range(int(ey - ry), int(ey + ry) + 1):
            for xx in range(int(ex - rx), int(ex + rx) + 1):
                if 0 <= xx < w and 0 <= yy < h and ((xx - ex) / rx) ** 2 + ((yy - ey) / ry) ** 2 <= 1:
                    px[xx, yy] = lerp(px[xx, yy], color, alpha)


def rain(img, frame, seed=3, count=34):
    w, h = img.size
    px = img.load()
    rnd = random.Random(seed)
    for _ in range(count):
        x0, sp, off = rnd.randint(0, w - 1), rnd.uniform(1.6, 2.6), rnd.uniform(0, h)
        y = (off + frame * sp) % (h + 4) - 2
        for k in range(3):
            X, Y = int(x0 - k * 0.4), int(y + k)
            if 0 <= X < w and 0 <= Y < h:
                px[X, Y] = lerp(px[X, Y], (150, 172, 214), 0.9)


def snow(img, frame, seed=5, count=28):
    w, h = img.size
    px = img.load()
    rnd = random.Random(seed)
    for _ in range(count):
        x0, ph, off = rnd.randint(0, w - 1), rnd.random() * 6, rnd.uniform(0, h)
        y = (off + frame * 0.7) % (h + 2) - 1
        x = int(x0 + math.sin(frame * 0.3 + ph))
        if 0 <= x < w and 0 <= int(y) < h:
            px[x, int(y)] = lerp(px[x, int(y)], (236, 242, 255), 0.95)


def dim(img, factor=0.6):
    return Image.eval(img, lambda v: int(v * factor))
