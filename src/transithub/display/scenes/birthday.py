"""Birthday takeover: HAPPY BIRTHDAY + a name, on someone's birthday.

One celebrant per day (the first configured). A fullscreen takeover that rotates
through three animations on each appearance — confetti & balloons, a candlelit
cake, and fireworks. Config-driven and clockwork only: the source reads
``ctx.now`` against the parsed birthday specs; there's no background poller. Text
is drawn over the animated background with an outline so it stays legible."""
from __future__ import annotations

import math
from typing import List, Optional

from PIL import Image

from ...birthdays import birthday_today
from .. import scenery as S
from ..director import Context
from .base import Scene

COLS, ROWS = 64, 32
DURATION_MS = 9000
_STYLES = ("confetti", "cake", "fireworks")

_OUT = (8, 6, 18)                 # dark outline so text reads over the motion
_HDR = (255, 236, 140)            # warm "HAPPY BIRTHDAY"
_NAME = (255, 255, 255)
_PARTY = ((255, 240, 130), (140, 220, 250), (250, 140, 170), (150, 240, 160))

_CONFETTI_BG = [(0.0, (54, 22, 74)), (0.55, (122, 50, 96)), (1.0, (198, 92, 68))]
_CAKE_BG = [(0.0, (32, 22, 56)), (1.0, (16, 12, 34))]
_FW_BG = [(0.0, (6, 8, 26)), (1.0, (14, 14, 40))]
_FW_COLORS = ((255, 210, 120), (140, 220, 255), (250, 150, 190), (170, 245, 170))


def _fit(text: str, max_px: int = 62) -> str:
    """Shorten ``text`` so it renders within ``max_px`` — drop trailing words
    first, then hard-trim characters as a last resort. Never clips."""
    if S.text_width(text) <= max_px:
        return text
    words = text.split()
    while len(words) > 1:
        words.pop()
        candidate = " ".join(words)
        if S.text_width(candidate) <= max_px:
            return candidate
    out = words[0] if words else text
    while out and S.text_width(out) > max_px:
        out = out[:-1]
    return out


def _centered(img: Image.Image, y: int, text: str, color) -> None:
    S.draw_text(img, (COLS - S.text_width(text)) // 2, y, text, color, outline=_OUT)


class BirthdayScene(Scene):
    """"HAPPY / BIRTHDAY / <name>" over a rotating party animation."""
    duration_ms = DURATION_MS

    def __init__(self, name: str, style: str = "confetti", cols: int = COLS, rows: int = ROWS):
        self.name = name
        self.style = style if style in _STYLES else "confetti"
        self.cols, self.rows = cols, rows

    def lines(self) -> List[str]:
        return ["HAPPY", "BIRTHDAY", _fit((self.name or "").upper())]

    # -- animated backgrounds ---------------------------------------------
    def _bg_confetti(self, img: Image.Image, frame: int) -> None:
        S.gradient(img, _CONFETTI_BG)
        px = img.load()
        for i in range(22):                            # confetti drifting down
            y = (i * 5 + frame) % self.rows
            x = (i * 13 + y // 3) % self.cols
            px[x, y] = _PARTY[i % len(_PARTY)]
        for b in range(3):                             # balloons rising from below
            bx = 10 + b * 22
            by = (self.rows + 2) - ((frame + b * 13) % (self.rows + 6))
            color = _PARTY[(b + 1) % len(_PARTY)]
            for dx, dy in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)):
                X, Y = bx + dx, by + dy
                if 0 <= X < self.cols and 0 <= Y < self.rows:
                    px[X, Y] = color
            for k in (2, 3, 4):                         # string
                Y = by + k
                if 0 <= bx < self.cols and 0 <= Y < self.rows:
                    px[bx, Y] = (210, 210, 220)

    def _bg_cake(self, img: Image.Image, frame: int) -> None:
        S.gradient(img, _CAKE_BG)
        px = img.load()
        base_top = self.rows - 9                         # cake body fills the bottom 9 rows
        for x in range(5, self.cols - 5):
            for y in range(base_top, self.rows):
                px[x, y] = (198, 122, 86)
            px[x, base_top] = (250, 240, 246)            # icing along the top edge
            if (x % 6) in (2, 3):                         # little icing drips
                px[x, base_top + 1] = (250, 240, 246)
        # candles stand in the gap above the cake; flames flicker over them — clear
        # of the header above and the name iced onto the cake below.
        for j, cx in enumerate(range(11, self.cols - 8, 12)):
            for y in range(base_top - 4, base_top):
                px[cx, y] = (244, 238, 250)
            fy = base_top - 6 - (1 if ((frame + j * 2) % 6) < 3 else 0)
            for fyy, col in ((fy, (255, 244, 186)), (fy + 1, (255, 184, 80))):
                if 0 <= fyy < self.rows:
                    px[cx, fyy] = col

    def _bg_fireworks(self, img: Image.Image, frame: int) -> None:
        S.gradient(img, _FW_BG)
        S.stars(img, frame, seed=29, count=8)
        px = img.load()
        # several bursts on staggered cycles, ringing the text; each blooms outward
        # (12 two-pixel spokes) and fades, so something is always going off.
        for j, (cx, cy) in enumerate(((12, 7), (52, 6), (20, 27), (45, 26), (32, 15))):
            phase = (frame + j * 5) % 16
            if phase >= 11:                              # dark gap between bursts
                continue
            r = phase // 2 + 1                           # radius grows 1..6
            fade = max(0.25, 1.0 - phase / 11)
            base = _FW_COLORS[j % len(_FW_COLORS)]
            color = tuple(int(v * fade) for v in base)
            for ang in range(0, 360, 30):                # 12 spokes, 2px thick
                for rr in (r, r - 1):
                    if rr < 1:
                        continue
                    x = int(cx + rr * math.cos(math.radians(ang)))
                    y = int(cy + rr * math.sin(math.radians(ang)))
                    if 0 <= x < self.cols and 0 <= y < self.rows:
                        px[x, y] = color
            if 0 <= cx < self.cols and 0 <= cy < self.rows:
                px[cx, cy] = (255, 255, 255)             # bright core

    def render(self, elapsed_ms: int) -> Image.Image:
        frame = elapsed_ms // 100
        img = Image.new("RGB", (self.cols, self.rows), (0, 0, 0))
        bg = {"cake": self._bg_cake, "fireworks": self._bg_fireworks}.get(
            self.style, self._bg_confetti)
        bg(img, frame)
        hdr1, hdr2, name = self.lines()
        _centered(img, 1, hdr1, _HDR)
        _centered(img, 9, hdr2, _HDR)
        name_y = 24 if self.style == "cake" else 18    # cake: name iced onto the cake
        _centered(img, name_y, name, _NAME)
        if elapsed_ms < 600:        # gentle fade-in so it arrives calmly
            return Image.blend(Image.new("RGB", (self.cols, self.rows), (0, 0, 0)),
                               img, elapsed_ms / 600)
        return img


class BirthdaySource:
    """Shows the configured birthday for today, decided from ``ctx.now``.

    Holds the parsed specs and an index that advances each appearance, so
    consecutive takeovers rotate confetti -> cake -> fireworks. No network, no
    holder — just the specs and the clock."""
    name = "birthday"

    def __init__(self, specs, cols: int = COLS, rows: int = ROWS):
        self.specs = list(specs)
        self.cols, self.rows = cols, rows
        self._i = 0

    def poll(self, ctx: Context) -> Optional[Scene]:
        who = birthday_today(self.specs, ctx.now)
        if who is None:
            return None
        style = _STYLES[self._i % len(_STYLES)]
        self._i += 1
        return BirthdayScene(who, style, self.cols, self.rows)
