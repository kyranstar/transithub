"""Neighborhood scenes: a farmers market open today, and a free outdoor event.

Both keep to one idea on three short lines (type / place / time, or type / time /
place) over a small, tasteful motif drawn here — a striped market awning with
produce, and a film frame for events. Every line is fit-checked against the 64px
panel and shortened word-by-word before it can clip. The sources read the latest
``ctx.local`` snapshot; the event source cycles through the day's list across
plays so a glance isn't always the same one."""
from __future__ import annotations

from typing import List, Optional

from PIL import Image

from ...local.events import Event, short_place
from ...local.markets import Market
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
    """"MARKET TODAY / <place> / <until>" under a striped stall awning."""
    duration_ms = DURATION_MS

    def __init__(self, market: Market, cols: int = COLS, rows: int = ROWS):
        self.market = market
        self.cols, self.rows = cols, rows

    def lines(self) -> List[str]:
        return ["MARKET TODAY", short_place(self.market.name), _fit(self.market.close_label)]

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
# Event
# --------------------------------------------------------------------------
_E_BG = [(0.0, (26, 22, 52)), (1.0, (12, 12, 30))]    # dusk-violet wash
_E_OUT = (8, 8, 20)
_E_TYPE = (140, 210, 255)      # type headline — cool blue
_E_TIME = (255, 232, 150)      # time — warm
_E_PLACE = (230, 226, 248)
_REEL = (235, 238, 250)
_SPROCKET = (250, 220, 120)


class EventScene(Scene):
    """"<type> / <time> / <place>" beside a little film-strip motif."""
    duration_ms = DURATION_MS

    def __init__(self, event: Event, cols: int = COLS, rows: int = ROWS):
        self.event = event
        self.cols, self.rows = cols, rows

    def lines(self) -> List[str]:
        return [_fit(self.event.kind), _fit(self.event.when_label), short_place(self.event.venue)]

    def _film_strip(self, img: Image.Image, frame: int) -> None:
        # A film strip running across the top: two black bands with scrolling
        # sprocket holes and a couple of bright "frames" — reads as movie/show.
        px = img.load()
        top, h = 0, 6
        for x in range(self.cols):
            for y in range(top, top + h):
                px[x, y] = (10, 10, 16)
        for x in range((frame) % 4, self.cols, 4):    # scrolling sprockets
            for y in (top + 1, top + h - 2):
                if 0 <= x < self.cols:
                    px[x, y] = _SPROCKET
        for fx in range(2, self.cols - 4, 14):         # little lit frames
            for x in range(fx, min(fx + 8, self.cols)):
                px[x, top + 2] = _REEL
                px[x, top + 3] = _REEL
        for x in range(self.cols):                     # shadow under the strip
            if top + h < self.rows:
                px[x, top + h] = (6, 6, 14)

    def render(self, elapsed_ms: int) -> Image.Image:
        frame = elapsed_ms // 100
        img = Image.new("RGB", (self.cols, self.rows), (0, 0, 0))
        S.gradient(img, _E_BG)
        self._film_strip(img, frame)
        type_l, time_l, place_l = self.lines()
        _centered(img, 8, type_l, _E_TYPE, _E_OUT)
        _centered(img, 16, time_l, _E_TIME, _E_OUT)
        _centered(img, 24, place_l, _E_PLACE, _E_OUT)
        if elapsed_ms < 600:
            return Image.blend(Image.new("RGB", (self.cols, self.rows), (0, 0, 0)),
                               img, elapsed_ms / 600)
        return img


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------
class MarketSource:
    """Shows the single nearest market open today, from ``ctx.local.market``."""
    name = "market"

    def __init__(self, cols: int = COLS, rows: int = ROWS):
        self.cols, self.rows = cols, rows

    def poll(self, ctx: Context) -> Optional[Scene]:
        local = getattr(ctx, "local", None)
        market = getattr(local, "market", None) if local else None
        if market is None:
            return None
        return MarketScene(market, self.cols, self.rows)


class EventSource:
    """Cycles through today's qualifying events across plays (from ``ctx.local``)."""
    name = "events"

    def __init__(self, cols: int = COLS, rows: int = ROWS):
        self.cols, self.rows = cols, rows
        self._i = 0

    def poll(self, ctx: Context) -> Optional[Scene]:
        local = getattr(ctx, "local", None)
        events = list(getattr(local, "events", []) or []) if local else []
        if not events:
            return None
        event = events[self._i % len(events)]
        self._i += 1
        return EventScene(event, self.cols, self.rows)
