"""Two quiet space interjections, one idea per beat.

`HumansInSpaceScene` rotates between a big "N IN SPACE" count and a per-craft
breakdown, over a starfield with a tiny drifting station. `EarthFromSpaceScene`
floats the graded EPIC disc on a starfield with a slow shimmer and a small
caption. Both reuse the shared `scenery` kit and never crowd the panel.
"""
from __future__ import annotations

import math
from typing import Optional

from PIL import Image

from ...space import EarthFrame, HumansInSpace
from .. import scenery as S
from .base import Scene

OUT = (6, 8, 22)
_SPACE_TOP = (4, 6, 20)
_SPACE_BOT = (10, 10, 30)
_BEAT_MS = 4000          # each idea holds this long before rotating
_DIP_MS = 450


def _space_bg(cols: int, rows: int, frame: int) -> Image.Image:
    img = Image.new("RGB", (cols, rows), (0, 0, 0))
    S.gradient(img, [(0.0, _SPACE_TOP), (1.0, _SPACE_BOT)])
    S.stars(img, frame, seed=21, count=22)          # whole-frame starfield
    S.stars(img, frame + 5, seed=44, count=14)
    return img


def _station(img: Image.Image, cx: int, cy: int, color=(206, 214, 236)) -> None:
    """A tiny space-station glyph: a bright core with two solar-panel wings."""
    w, h = img.size
    px = img.load()

    def put(x, y, c):
        if 0 <= x < w and 0 <= y < h:
            px[x, y] = c

    put(cx, cy, color)
    put(cx, cy - 1, color)
    put(cx, cy + 1, color)
    wing = (96, 132, 196)
    for dx in (-3, -2, 2, 3):                        # two panels either side
        put(cx + dx, cy, wing)
        put(cx + dx, cy - 1, wing)


def _dip(img: Image.Image, within: int, dur: int) -> Image.Image:
    """Fade in/out at the edges of a beat so rotations feel calm, not jumpy."""
    black = Image.new("RGB", img.size, (0, 0, 0))
    if within < _DIP_MS:
        return Image.blend(black, img, within / _DIP_MS)
    if within > dur - _DIP_MS:
        return Image.blend(img, black, (within - (dur - _DIP_MS)) / _DIP_MS)
    return img


class HumansInSpaceScene(Scene):
    duration_ms = 8000

    def __init__(self, humans: HumansInSpace, cols: int = 64, rows: int = 32):
        self.h = humans
        self.cols, self.rows = cols, rows
        # Beat 1: the count. Beat 2: the breakdown (only if we know a craft).
        self._beats = [self._count_beat]
        if humans.by_craft:
            self._beats.append(self._craft_beat)

    def _centered(self, img, y, text, color, scale=1):
        x = (self.cols - S.text_width(text, scale)) // 2
        S.draw_text(img, x, y, text, color, scale, OUT)

    def _count_beat(self, frame: int) -> Image.Image:
        img = _space_bg(self.cols, self.rows, frame)
        # Drift a station across the top so the count has some life behind it.
        sx = (frame * 1) % (self.cols + 8) - 4
        _station(img, sx, 4)
        n = str(self.h.total)
        # Big number, then a small word line — one concept, never four lines.
        self._centered(img, 7, n, (255, 240, 180), scale=2)
        self._centered(img, 24, "IN SPACE", (150, 196, 236))
        return img

    def _craft_line(self, craft: str) -> str:
        """'CRAFT n', shortened to fit 64px. Drop trailing words first (so "Crew
        Dragon 6" becomes "Crew 6", not "Crew Drago 6"), and only hard-trim a single
        long word as a last resort. The count always survives."""
        n = self.h.by_craft[craft]
        if S.text_width(f"{craft} {n}") <= self.cols:
            return f"{craft} {n}"
        words = craft.split()
        while len(words) > 1:
            words.pop()
            cand = f"{' '.join(words)} {n}"
            if S.text_width(cand) <= self.cols:
                return cand
        name = words[0] if words else craft
        while len(name) > 3 and S.text_width(f"{name} {n}") > self.cols:
            name = name[:-1]
        return f"{name} {n}"

    def _craft_beat(self, frame: int) -> Image.Image:
        img = _space_bg(self.cols, self.rows, frame)
        sx = self.cols - 4 - (frame * 1) % (self.cols + 8)
        _station(img, sx, 4)
        # Up to two crafts, each "CRAFT n" on its own centered, fit-checked row.
        lines = [self._craft_line(c) for c in self.h.crafts[:2]]
        ys = [12] if len(lines) == 1 else [8, 19]
        for y, text in zip(ys, lines):
            self._centered(img, y, text, (210, 224, 250))
        return img

    def render(self, elapsed_ms: int) -> Image.Image:
        frame = elapsed_ms // 100
        idx = (elapsed_ms // _BEAT_MS) % len(self._beats)
        within = elapsed_ms % _BEAT_MS
        return _dip(self._beats[idx](frame), within, _BEAT_MS)


class EarthFromSpaceScene(Scene):
    duration_ms = 9000

    def __init__(self, earth: EarthFrame, cols: int = 64, rows: int = 32):
        self.e = earth
        self.cols, self.rows = cols, rows

    def render(self, elapsed_ms: int) -> Image.Image:
        frame = elapsed_ms // 100
        img = _space_bg(self.cols, self.rows, frame)
        # Float the disc: a gentle 1px bob gives a "suspended in space" feel without
        # ever clipping (the disc is ~28px tall on a 32px panel).
        dy = int(round(math.sin(frame * 0.18)))
        disc = self.e.base_image
        if disc.size != (self.cols, self.rows):
            disc = disc.resize((self.cols, self.rows))
        # Composite only the lit disc pixels over the starfield (black = transparent).
        px, dp = img.load(), disc.load()
        for y in range(self.rows):
            sy = y - dy
            if not (0 <= sy < self.rows):
                continue
            for x in range(self.cols):
                c = dp[x, sy]
                if c != (0, 0, 0):
                    px[x, y] = c
        # A faint terminator shimmer: a slow brightening sweep down the disc.
        self._shimmer(img, frame)
        # Small caption at the bottom, outlined for legibility over the disc.
        cap = self.e.caption
        cx = (self.cols - S.text_width(cap)) // 2
        S.draw_text(img, cx, self.rows - 7, cap, (224, 234, 255), outline=OUT)
        # Fade the whole scene in/out at its edges.
        return _dip(img, elapsed_ms, self.duration_ms)

    def _shimmer(self, img: Image.Image, frame: int) -> None:
        w, h = img.size
        px = img.load()
        band = (frame * 0.6) % (h + 8) - 4            # sweeps top to bottom
        for y in range(h):
            d = abs(y - band)
            if d > 2:
                continue
            a = (1 - d / 2) * 0.12
            for x in range(w):
                c = px[x, y]
                if c != (0, 0, 0):                    # only lift the lit disc
                    px[x, y] = S.lerp(c, (255, 255, 255), a)


# --------------------------------------------------------------------------
# Scene sources: read the snapshots off ctx.space, return None when absent.
# --------------------------------------------------------------------------
def _space(ctx):
    return getattr(ctx, "space", None)


class HumansInSpaceSource:
    """Shows the humans-in-space count when we have a fresh snapshot."""
    name = "humans_in_space"

    def __init__(self, cols: int = 64, rows: int = 32):
        self.cols, self.rows = cols, rows

    def poll(self, ctx) -> Optional[Scene]:
        sp = _space(ctx)
        humans = getattr(sp, "humans", None) if sp is not None else None
        if humans is None:
            return None
        return HumansInSpaceScene(humans, self.cols, self.rows)


class EarthFromSpaceSource:
    """Shows the most recent EPIC Earth frame when one is cached."""
    name = "earth_from_space"

    def __init__(self, cols: int = 64, rows: int = 32):
        self.cols, self.rows = cols, rows

    def poll(self, ctx) -> Optional[Scene]:
        sp = _space(ctx)
        earth = getattr(sp, "earth", None) if sp is not None else None
        if earth is None:
            return None
        return EarthFromSpaceScene(earth, self.cols, self.rows)
