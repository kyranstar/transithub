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


MOON_COLOR = (220, 226, 246)


def moon(img, cx, cy, r, phase):
    """Draw the sunlit part of the moon for `phase` in [0, 1) (0 new, 0.5 full).

    The terminator follows the phase: waxing lights the right limb, waning the
    left (northern hemisphere). The dark part is left as sky, so a new moon shows
    nothing and a crescent is a glowing sliver. A soft halo hugs the lit limb."""
    c = math.cos(2 * math.pi * phase)              # +1 new ... -1 full; scales the terminator
    if (1 - c) / 2 < 0.01:                         # essentially a new moon -> invisible
        return
    w, h = img.size
    px = img.load()
    waxing = phase < 0.5
    lit = set()
    for yy in range(cy - r, cy + r + 1):
        ny = (yy - cy) / r
        if abs(ny) > 1:
            continue
        rx = math.sqrt(1 - ny * ny) * r            # disc half-width at this row
        for xx in range(cx - r, cx + r + 1):
            nx = xx - cx
            if abs(nx) > rx:
                continue
            if (nx >= rx * c) if waxing else (nx <= -rx * c):
                if 0 <= xx < w and 0 <= yy < h:
                    px[xx, yy] = MOON_COLOR
                    lit.add((xx, yy))
    # halo: brighten pixels just outside the disc that border a lit pixel
    for (lx, ly) in lit:
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                xx, yy = lx + dx, ly + dy
                if not (0 <= xx < w and 0 <= yy < h) or (xx, yy) in lit:
                    continue
                d = math.hypot(xx - cx, yy - cy)
                if d > r:
                    a = max(0.0, (1 - (d - r) / 2)) * 0.3
                    if a > 0:
                        px[xx, yy] = lerp(px[xx, yy], MOON_COLOR, a)


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


def fog(img, frame, color=(150, 154, 162)):
    """Slow drifting banks of gray. Two soft sine bands of differing speed cross the
    panel and beat against each other, so the murk shifts and shimmers without ever
    looking like discrete shapes."""
    w, h = img.size
    px = img.load()
    t = frame * 0.06
    for y in range(h):
        ny = y / (h - 1)
        for x in range(w):
            band = (math.sin(x * 0.16 + t + ny * 1.3)
                    + 0.7 * math.sin(x * 0.07 - t * 1.7 + y * 0.25))
            a = 0.18 + 0.32 * (band + 1.7) / 3.4          # gentle, always a little haze
            px[x, y] = lerp(px[x, y], color, max(0.0, min(0.6, a)))


def pulsing_sun(img, cx, cy, r, frame, color=(255, 168, 64)):
    """A hot, swollen sun that breathes. The glow radius and intensity ride a slow
    sine so it throbs like heat-shimmer; a hotter core keeps it reading as the sun."""
    breathe = 0.5 + 0.5 * math.sin(frame * 0.22)
    glow_sun(img, cx, cy, r, color=color, intensity=0.55 + 0.45 * breathe)
    w, h = img.size
    px = img.load()
    core = max(1, r - 2)
    hot = lerp(color, (255, 244, 210), 0.6)
    for yy in range(cy - core, cy + core + 1):
        for xx in range(cx - core, cx + core + 1):
            if 0 <= xx < w and 0 <= yy < h and math.hypot(xx - cx, yy - cy) <= core:
                px[xx, yy] = hot


def gusts(img, frame, color=(214, 224, 236)):
    """Streaks of wind blowing left-to-right. Each is a short comet that wraps the
    panel at its own speed and height, so the air looks like it's really moving."""
    w, h = img.size
    px = img.load()
    # (row, speed, length, phase) — staggered phases so the sky is never empty.
    streaks = ((4, 2.6, 9, 8), (12, 1.9, 5, 30), (20, 3.1, 13, 50), (26, 2.2, 7, 18))
    span = w + 16
    for y0, sp, length, phase in streaks:
        head = (frame * sp + phase) % span - length
        for k in range(length):
            x = int(head - k)
            a = (1 - k / length) * 0.85               # fades toward the tail
            if 0 <= x < w and 0 <= y0 < h:
                px[x, y0] = lerp(px[x, y0], color, a)


def haze(img, frame, color, alpha=0.45):
    """A breathing wash of `color` over the whole frame — for muggy air or a bad-AQI
    sky. The alpha pulses faintly so the murk feels alive instead of a flat filter."""
    w, h = img.size
    px = img.load()
    pulse = alpha * (0.85 + 0.15 * math.sin(frame * 0.12))
    for y in range(h):
        for x in range(w):
            px[x, y] = lerp(px[x, y], color, pulse)


def dim(img, factor=0.6):
    return Image.eval(img, lambda v: int(v * factor))
