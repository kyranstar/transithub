"""Neighborhood scene: the farmers market that's open near home today.

One idea on three short lines ("MARKET TODAY / <place> / UNTIL <x>") over a
small striped market awning with produce. Every line is fit-checked against the
64px panel and shortened word-by-word before it can clip. The source is built
from the curated config specs and reads ``ctx.now`` to decide if a market is open
today — there's no background poller."""
from __future__ import annotations

from typing import List, Optional

from PIL import Image

from ...local.markets import Market, MarketSpec, market_today, short_place
from .. import scenery as S
from .base import Scene
from ..director import Context

COLS, ROWS = 64, 32
DURATION_MS = 8000


def _fit(text: str, max_px: int = 62) -> str:
    """Shorten ``text`` so it renders within ``max_px``.

    Drops trailing words first (keeping the leading, usually most-specific ones),
    then hard-trims characters as a last resort. Never returns something that
    clips."""
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


def _centered(img: Image.Image, y: int, text: str, color, outline) -> None:
    S.draw_text(img, (COLS - S.text_width(text)) // 2, y, text, color, outline=outline)


# --------------------------------------------------------------------------
# Market
# --------------------------------------------------------------------------
_M_BG = [(0.0, (18, 34, 22)), (1.0, (10, 20, 16))]   # soft garden-green wash
_M_OUT = (8, 16, 12)
_AWN_A = (210, 78, 64)        # awning stripe A (tomato red)
_AWN_B = (245, 240, 232)      # awning stripe B (cream)
_TYPE = (250, 226, 130)       # "MARKET TODAY" — warm amber
_PLACE = (236, 244, 236)
_TIME = (150, 214, 150)
_PRODUCE = [(236, 96, 72), (250, 196, 70), (140, 206, 110), (228, 130, 60)]


class MarketScene(Scene):
    """"MARKET TODAY / <place> / UNTIL <x>" under a striped stall awning."""
    duration_ms = DURATION_MS

    def __init__(self, market: Market, cols: int = COLS, rows: int = ROWS):
        self.market = market
        self.cols, self.rows = cols, rows

    def lines(self) -> List[str]:
        return ["MARKET TODAY", short_place(self.market.name), _fit(f"UNTIL {self.market.until}")]

    def _awning(self, img: Image.Image, frame: int) -> None:
        px = img.load()
        # A scalloped striped awning across the very top (rows 0-5), a thin shadow
        # line, then a row of produce dots tucked just beneath it (row 7) — the
        # text lines own everything below row 8, so nothing crowds.
        for x in range(self.cols):
            stripe = _AWN_A if (x // 6) % 2 == 0 else _AWN_B
            for y in range(0, 5):
                px[x, y] = stripe
            if (x % 6) in (2, 3):                   # scalloped lower edge
                px[x, 5] = stripe
        for x in range(self.cols):                 # shadow under the awning
            px[x, 6] = (6, 12, 9)
        for i, cx in enumerate(range(6, self.cols - 1, 11)):  # produce on the lip
            color = _PRODUCE[i % len(_PRODUCE)]
            wobble = 1 if (frame + i * 3) % 6 < 3 else 0      # tiny shimmer
            for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
                X, Y = cx + dx, 7 + dy - wobble
                if 0 <= X < self.cols and 0 <= Y < self.rows:
                    px[X, Y] = color

    def render(self, elapsed_ms: int) -> Image.Image:
        frame = elapsed_ms // 100
        img = Image.new("RGB", (self.cols, self.rows), (0, 0, 0))
        S.gradient(img, _M_BG)
        self._awning(img, frame)
        type_l, place_l, time_l = self.lines()
        _centered(img, 8, type_l, _TYPE, _M_OUT)
        _centered(img, 16, place_l, _PLACE, _M_OUT)
        _centered(img, 24, time_l, _TIME, _M_OUT)
        if elapsed_ms < 600:        # gentle fade-in so it arrives calmly
            return Image.blend(Image.new("RGB", (self.cols, self.rows), (0, 0, 0)),
                               img, elapsed_ms / 600)
        return img


# --------------------------------------------------------------------------
# Source
# --------------------------------------------------------------------------
class MarketSource:
    """Shows the configured market open today, decided from ``ctx.now``.

    Holds the parsed config specs; ``poll`` returns a ``MarketScene`` when one of
    them is open today, else None. No network, no holder — just the specs and the
    clock."""
    name = "market"

    def __init__(self, specs: List[MarketSpec], cols: int = COLS, rows: int = ROWS):
        self.specs = list(specs)
        self.cols, self.rows = cols, rows

    def poll(self, ctx: Context) -> Optional[Scene]:
        market = market_today(self.specs, ctx.now)
        if market is None:
            return None
        return MarketScene(market, self.cols, self.rows)
