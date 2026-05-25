"""Nearest farmers market that's open *today*, from NYC Open Data.

Dataset: "DOHMH Farmers Markets" — Socrata resource ``8vwk-6iz2`` on
``data.cityofnewyork.us``. Each row has a name, lat/lon, free-text day(s) of
operation, free-text hours, and an ``open_year_round`` flag. There is no explicit
season window, so we apply one conservative rule (below) and otherwise show
nothing rather than guess.

The free-text schedule fields are messy (separators ``& , ; \\n``, ranges like
``Mon-Sat``, typos like ``Tusday``/``Wedneday``, hours like ``9a.m. - 2 p.m.``
or ``noon - 3 p.m.``). We parse defensively and only surface a market when we can
pin BOTH that today's weekday is in its schedule AND a closing time."""
from __future__ import annotations

import json
import math
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

from ..clock import now as now_eastern
from .events import short_place

RESOURCE = "8vwk-6iz2"
BASE_URL = f"https://data.cityofnewyork.us/resource/{RESOURCE}.json"

# Seasonal (not year-round) outdoor greenmarkets in NYC run, conservatively,
# May through November. With no per-market season dates published, this is the
# one assumption we make; outside it, seasonal markets are treated as closed.
SEASON_MONTHS = frozenset(range(5, 12))   # May (5) .. November (11)

# Map every weekday spelling we expect (incl. common dataset typos) to Mon=0..Sun=6.
_WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1, "tusday": 1,            # 'Tusday' typo
    "wednesday": 2, "wed": 2, "weds": 2, "wedneday": 2,        # 'Wedneday' typo
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}


@dataclass(frozen=True)
class Market:
    """A market that is open today, ready for the screen."""
    name: str          # display name, already shortened/upper-cased for the panel
    close_label: str   # e.g. "UNTIL 6" or "UNTIL 2:30"
    dist_km: float


def _default_fetch(url: str) -> list:
    req = urllib.request.Request(url, headers={"User-Agent": "transithub"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p = math.pi / 180
    a = (0.5 - math.cos((lat2 - lat1) * p) / 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2)
    return 2 * 6371 * math.asin(math.sqrt(a))


def weekdays_of(text: str) -> set:
    """The set of weekday indices (Mon=0..Sun=6) a free-text schedule covers.

    Handles word lists with any of ``& , ; / \\n`` or the word "and" between
    them, simple ranges like ``Mon-Sat``/``Tuesday-Friday``, parentheticals like
    ``(starting 5/5)``, and the dataset's recurring typos. Unknown/``TBD`` -> {}.
    """
    if not text:
        return set()
    low = text.lower()
    # Ranges first: "<day> - <day>" => inclusive span (only when both ends are days).
    out: set = set()
    for a, b in re.findall(r"([a-z]+)\s*-\s*([a-z]+)", low):
        if a in _WEEKDAYS and b in _WEEKDAYS:
            lo, hi = sorted((_WEEKDAYS[a], _WEEKDAYS[b]))
            out.update(range(lo, hi + 1))
    # Then any individual weekday words anywhere in the string.
    for word in re.findall(r"[a-z]+", low):
        if word in _WEEKDAYS:
            out.add(_WEEKDAYS[word])
    return out


# A clock time ("9", "9:30", "9a.m.", "2 p.m.") or the bare word "noon".
_TIME_RE = re.compile(r"(?:(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?))|(noon)", re.I)


def _close_token(segment: str) -> Optional[str]:
    """The closing-time label from one schedule segment, or None.

    A segment like ``9 a.m. - 3 p.m.`` has its close as the last time token. We
    keep "UNTIL 3" for an afternoon close and tack on "AM" when a market closes in
    the morning so it's never ambiguous."""
    matches = list(_TIME_RE.finditer(segment))
    if len(matches) < 2:           # need an open AND a close to trust it
        return None
    h, m, ap, noon = matches[-1].groups()
    if noon:
        return "UNTIL NOON"
    ap = ap.lower().replace(".", "")
    label = h if not m else f"{h}:{m}"
    if ap == "am":                 # morning close is unusual -> mark it
        return f"UNTIL {label}AM"
    return f"UNTIL {label}"


def parse_close_label(hours: str) -> Optional[str]:
    """A single "UNTIL <time>" close label from free-text hours, or None.

    Multi-segment strings (``... (W); ... (SU)``) are split on ``;`` and the
    first parseable segment's close is used; in this dataset the segments share a
    close time, so this stays accurate and we avoid promising a day-specific close
    we can't reliably attribute."""
    if not hours:
        return None
    for segment in re.split(r"[;]", hours):
        label = _close_token(segment)
        if label is not None:
            return label
    return _close_token(hours)


# Drop the operator prefix so the panel shows the *place*: "RiseBoro Farmers
# Markets at Maria Hernandez" -> "HERNANDEZ"; "McCarren Park Greenmarket" ->
# "MCCARREN". `short_place` then abbreviates/fits it to the panel.
_AT_SPLIT = re.compile(r"\s+at\s+", re.I)
_DROP_WORDS = re.compile(r"\b(greenmarket|farmers?|markets?|farmstand)\b", re.I)


def _display_name(name: str) -> str:
    base = _AT_SPLIT.split(name)[-1]          # keep the part after "... at ..."
    base = _DROP_WORDS.sub("", base)
    base = re.sub(r"\s+", " ", base).strip(" -,").strip()
    return short_place(base or name)


class MarketsClient:
    """Finds the single nearest market open today within ``radius_km`` of home.

    Conservative by design: a market is only returned when today's weekday is in
    its parsed schedule, it is in season (year-round, or a seasonal market during
    the May-Nov window), and a closing time parses. Anything we can't pin is
    dropped, so we never invite someone to a market that isn't there."""
    name = "markets"

    def __init__(self, latitude: float, longitude: float, radius_km: float = 4.0,
                 fetcher: Callable[[str], list] = _default_fetch,
                 now: Callable[[], "object"] = now_eastern):
        self.lat = latitude
        self.lon = longitude
        self.radius_km = radius_km
        self._fetch = fetcher
        self._now = now

    def _url(self) -> str:
        # Pull a generous Brooklyn-area page; we filter precisely in Python.
        q = urllib.parse.urlencode({"$limit": 2000, "$order": "year DESC"})
        return f"{BASE_URL}?{q}"

    def _in_season(self, row: dict, month: int) -> bool:
        flag = str(row.get("open_year_round") or "").strip().lower()
        if flag.startswith("yes"):
            return True
        return month in SEASON_MONTHS

    def best(self) -> Optional[Market]:
        try:
            rows = self._fetch(self._url())
        except Exception:
            return None
        if not isinstance(rows, list) or not rows:
            return None

        now = self._now()
        today = now.weekday()
        month = now.month

        # Only consider the most recent year present (the feed lags a season or two).
        years = [str(r.get("year")) for r in rows if r.get("year")]
        latest = max(years, default=None)

        best: Optional[Market] = None
        for row in rows:
            try:
                if latest is not None and str(row.get("year")) != latest:
                    continue
                if today not in weekdays_of(row.get("daysoperation") or ""):
                    continue
                if not self._in_season(row, month):
                    continue
                close = parse_close_label(row.get("hoursoperations") or "")
                if close is None:
                    continue
                lat = float(row["latitude"])
                lon = float(row["longitude"])
            except (KeyError, TypeError, ValueError):
                continue
            dist = _haversine_km(self.lat, self.lon, lat, lon)
            if dist > self.radius_km:
                continue
            if best is None or dist < best.dist_km:
                name = _display_name(str(row.get("marketname") or "").strip())
                best = Market(name=name, close_label=close, dist_km=round(dist, 2))
        return best
