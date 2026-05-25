"""Sky-event scenes and their sources: the moon, the ISS overhead, a plane.

One idea per screen, each a brief takeover that gets out of the way:

* ``FullMoonScene`` / ``NewMoonScene`` — a once-a-night salute on the calendar
  day of the full or new moon, after sunset.
* ``IssPassScene`` — a heads-up ("LOOK NW") as a pass approaches, then an
  "ABOVE YOU" arc while the station is up.
* ``PlaneOverheadScene`` — a little airliner gliding across with its callsign,
  heading and altitude (no route — OpenSky doesn't give us one).

All the moon/orbit/plane drawing lives here; only the small shared primitives
(text, stars, gradients, the moon disc) are reused from ``scenery``."""
from __future__ import annotations

import math
from datetime import datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from PIL import Image

from ...sky import IssPass, Plane
from ...weather.model import moon_phase
from .. import scenery as S
from ..director import Context
from .base import Scene

_NY = ZoneInfo("America/New_York")     # ISS times are UTC; the clock is NYC wall-time

OUT = (8, 8, 20)                       # text outline against a night sky
_NIGHT_BG = [(0.0, (4, 6, 22)), (0.6, (10, 12, 34)), (1.0, (20, 20, 48))]
_FULL_FALLBACK_SUNSET = time(20, 0)    # used when no weather is available


def _night_sky(cols: int, rows: int, frame: int, star_count: int = 16,
               seed: int = 11) -> Image.Image:
    img = Image.new("RGB", (cols, rows), (0, 0, 0))
    S.gradient(img, _NIGHT_BG)
    S.stars(img, frame, seed=seed, count=star_count)
    return img


def _centered(img, y, text, color, scale=1):
    w = img.size[0]
    S.draw_text(img, (w - S.text_width(text, scale)) // 2, y, text, color, scale, OUT)


def _twinkle(px, cx, cy, cols, rows, core=(255, 252, 235), arm=(170, 178, 210)):
    """A crisp pinpoint: a bright core with four faint diagonal-free arms."""
    px[cx, cy] = core
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        x, y = cx + dx, cy + dy
        if 0 <= x < cols and 0 <= y < rows:
            px[x, y] = S.lerp(px[x, y], arm, 0.6)


# ============================================================= MOON SCENES
class FullMoonScene(Scene):
    """A bright full moon rising into a starry sky with a soft halo."""
    duration_ms = 9000

    def __init__(self, cols: int = 64, rows: int = 32):
        self.cols, self.rows = cols, rows

    def render(self, elapsed_ms: int) -> Image.Image:
        frame = elapsed_ms // 100
        img = _night_sky(self.cols, self.rows, frame, star_count=18)
        p = min(1.0, elapsed_ms / self.duration_ms)
        cx = self.cols // 2
        cy = int(20 - 8 * p)                       # rises from low to mid-sky
        r = 6
        # outer glow
        S.glow_sun(img, cx, cy, r, color=(232, 236, 252), intensity=0.55)
        S.moon(img, cx, cy, r, 0.5)                # phase 0.5 == fully lit disc
        _centered(img, self.rows - 8, "FULL MOON", (236, 240, 255))
        return img


class NewMoonScene(Scene):
    """A dark, star-filled sky with only a faint outline where the moon hides."""
    duration_ms = 9000

    def __init__(self, cols: int = 64, rows: int = 32):
        self.cols, self.rows = cols, rows

    def render(self, elapsed_ms: int) -> Image.Image:
        frame = elapsed_ms // 100
        img = _night_sky(self.cols, self.rows, frame, star_count=22, seed=4)
        cx, cy, r = self.cols // 2, 11, 6
        px = img.load()
        # faint circular outline (earthshine) — the unlit disc against the stars
        for a in range(0, 360, 12):
            x = int(cx + r * math.cos(math.radians(a)))
            y = int(cy + r * math.sin(math.radians(a)))
            if 0 <= x < self.cols and 0 <= y < self.rows:
                px[x, y] = S.lerp(px[x, y], (60, 64, 92), 0.8)
        _centered(img, self.rows - 8, "NEW MOON", (150, 158, 192))
        return img


# ============================================================== ISS SCENE
class IssPassScene(Scene):
    """A satellite tracing a bright arc across the sky.

    ``heads_up`` shows the time and "LOOK <dir>"; ``overhead`` shows "ABOVE YOU"
    while the station is actually up. The dot rides a shallow arc with a fading
    trail; a faint orbit ring frames it."""
    duration_ms = 8000

    def __init__(self, iss: IssPass, now: datetime, mode: str = "heads_up",
                 cols: int = 64, rows: int = 32):
        self.iss = iss
        self.now = now
        self.mode = mode
        self.cols, self.rows = cols, rows

    def _arc_point(self, t: float):
        """Position along a shallow left-to-right arc, t in [0, 1]."""
        x = 4 + t * (self.cols - 8)
        y = 14 - math.sin(math.pi * t) * 8          # peaks near the top middle
        return x, y

    def render(self, elapsed_ms: int) -> Image.Image:
        frame = elapsed_ms // 100
        img = _night_sky(self.cols, self.rows, frame, star_count=12, seed=21)
        px = img.load()
        # faint orbit ring: a flat ellipse hint framing the arc
        for deg in range(0, 360, 8):
            ex = self.cols / 2 + 24 * math.cos(math.radians(deg))
            ey = 11 + 8 * math.sin(math.radians(deg))
            xi, yi = int(ex), int(ey)
            if 0 <= xi < self.cols and 0 <= yi < self.rows:
                px[xi, yi] = S.lerp(px[xi, yi], (40, 52, 80), 0.5)
        # the satellite + a short fading trail
        head = (frame % 40) / 40.0
        for k in range(7):
            t = head - k * 0.045
            if t < 0:
                continue
            x, y = self._arc_point(t)
            xi, yi = int(x), int(y)
            if 0 <= xi < self.cols and 0 <= yi < self.rows:
                a = (1.0 - k / 7.0)
                px[xi, yi] = S.lerp(px[xi, yi], (255, 250, 220), a)
                if k == 0:                          # crisp bright point with a faint twinkle
                    _twinkle(px, xi, yi, self.cols, self.rows)

        if self.mode == "overhead":
            _centered(img, self.rows - 17, "ISS", (200, 220, 255))
            _centered(img, self.rows - 8, "ABOVE YOU", (255, 250, 230))
        else:
            _centered(img, self.rows - 17, _ny_clock(self.iss.start), (210, 224, 255))
            _centered(img, self.rows - 8, f"LOOK {self.iss.rise_dir}", (255, 250, 230))
        return img


# ============================================================ PLANE SCENE
class PlaneOverheadScene(Scene):
    """A little airliner gliding across, trailing a contrail, with its details."""
    duration_ms = 7000

    def __init__(self, plane: Plane, cols: int = 64, rows: int = 32):
        self.plane = plane
        self.cols, self.rows = cols, rows

    def _draw_plane(self, img, x: int, y: int, color):
        """A tiny 9x5 airliner silhouette anchored at its nose (x, y)."""
        px = img.load()
        body = [(0, 0), (-1, 0), (-2, 0), (-3, 0), (-4, 0), (-5, 0), (-6, 0), (-7, 0),
                (-3, -1), (-3, 1),                  # wings
                (-7, -1), (-7, 1)]                  # tail fin
        for dx, dy in body:
            xi, yi = x + dx, y + dy
            if 0 <= xi < self.cols and 0 <= yi < self.rows:
                px[xi, yi] = color

    def render(self, elapsed_ms: int) -> Image.Image:
        frame = elapsed_ms // 100
        img = Image.new("RGB", (self.cols, self.rows), (0, 0, 0))
        S.gradient(img, [(0.0, (24, 40, 78)), (0.55, (60, 96, 150)), (1.0, (120, 150, 190))])
        px = img.load()
        # the plane crosses left -> right along the top third
        prog = (frame % 50) / 50.0
        nose_x = int(8 + prog * (self.cols))
        y = 7
        # contrail behind the nose
        for k in range(1, 16):
            tx = nose_x - 8 - k
            if 0 <= tx < self.cols:
                a = max(0.0, 0.5 - k * 0.03)
                px[tx, y] = S.lerp(px[tx, y], (235, 240, 250), a)
        self._draw_plane(img, nose_x, y, (245, 248, 255))

        _centered(img, self.rows - 17, self.plane.callsign, (255, 255, 255))
        line = f"{self.plane.dir} {self.plane.alt_ft}FT"
        _centered(img, self.rows - 8, line, (210, 226, 250))
        return img


# ================================================================ SOURCES
class MoonEventSource:
    """Fires once, after sunset, on the calendar day of the full or new moon.

    "Today is the day" when today's noon lunar phase is a strict local minimum of
    the distance to the target (full = 0.5, new = 0.0/1.0) versus yesterday and
    tomorrow, and within a small threshold. After sunset (real, from weather, or
    a ~20:00 fallback) it plays its scene exactly once that night."""
    name = "moon"

    def __init__(self, cols: int = 64, rows: int = 32, threshold: float = 0.06):
        self.cols, self.rows = cols, rows
        self.threshold = threshold
        self._fired: set = set()           # dates already shown

    @staticmethod
    def _dist_full(ph: float) -> float:
        return abs(ph - 0.5)

    @staticmethod
    def _dist_new(ph: float) -> float:
        return min(ph, 1.0 - ph)

    def _is_event_day(self, day: datetime, dist_fn) -> bool:
        noon = day.replace(hour=12, minute=0, second=0, microsecond=0)
        today = dist_fn(moon_phase(noon))
        if today > self.threshold:
            return False
        yesterday = dist_fn(moon_phase(noon - timedelta(days=1)))
        tomorrow = dist_fn(moon_phase(noon + timedelta(days=1)))
        return today < yesterday and today < tomorrow

    def poll(self, ctx: Context) -> Optional[Scene]:
        now = ctx.now
        key = now.date()
        if key in self._fired:
            return None
        # after sunset?
        sunset = getattr(ctx.weather, "sunset", None)
        if isinstance(sunset, datetime):
            if now < sunset:
                return None
        elif now.time() < _FULL_FALLBACK_SUNSET:
            return None

        if self._is_event_day(now, self._dist_full):
            self._fired.add(key)
            return FullMoonScene(self.cols, self.rows)
        if self._is_event_day(now, self._dist_new):
            self._fired.add(key)
            return NewMoonScene(self.cols, self.rows)
        return None


class IssPassSource:
    """Heads-up just before a pass; an "above you" arc during it.

    Reads ``ctx.sky.next_iss_pass``. A heads-up plays when the pass starts within
    ``lead_min`` minutes; the overhead scene plays while now is within the pass."""
    name = "iss"

    def __init__(self, cols: int = 64, rows: int = 32, lead_min: int = 6):
        self.cols, self.rows = cols, rows
        self.lead_min = lead_min

    def poll(self, ctx: Context) -> Optional[Scene]:
        sky = ctx.sky
        if sky is None or getattr(sky, "next_iss_pass", None) is None:
            return None
        p: IssPass = sky.next_iss_pass
        now = ctx.now
        start, end = _as_naive(p.start), _as_naive(p.end)
        if start <= now <= end:
            return IssPassScene(p, now, mode="overhead", cols=self.cols, rows=self.rows)
        if now < start <= now + timedelta(minutes=self.lead_min):
            return IssPassScene(p, now, mode="heads_up", cols=self.cols, rows=self.rows)
        return None


class PlaneOverheadSource:
    """Shows the nearest plane overhead while one is present in ``ctx.sky``."""
    name = "plane"

    def __init__(self, cols: int = 64, rows: int = 32):
        self.cols, self.rows = cols, rows

    def poll(self, ctx: Context) -> Optional[Scene]:
        sky = ctx.sky
        if sky is None or getattr(sky, "plane_overhead", None) is None:
            return None
        return PlaneOverheadScene(sky.plane_overhead, self.cols, self.rows)


def _as_naive(dt: datetime) -> datetime:
    """ISS times are tz-aware UTC; ctx.now is naive NYC wall-clock. Convert to
    naive NYC local time so the two compare correctly regardless of host TZ."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(_NY).replace(tzinfo=None)


def _ny_clock(dt: datetime) -> str:
    """A '%-I:%M %p' label in NYC time (naive datetimes are assumed NYC already)."""
    local = dt.astimezone(_NY) if dt.tzinfo is not None else dt
    return local.strftime("%-I:%M %p")
