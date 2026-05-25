"""The curated farmers market that's open *today*, straight from config.

NYC has no keyless, current, coordinate-tagged market feed worth trusting, so
this feature is config-driven instead of networked. The owner lists their
market(s) in YAML with an exact weekday and season window; we surface the one
that's open today and nothing else.

A config entry looks like::

    {"name": "MARIA HERNANDEZ", "day": "saturday",
     "season": ["2026-05-23", "2026-11-22"], "until": "3"}

``season`` is an inclusive ``[start, end]`` ISO-date pair; omit it for a market
that runs year-round. ``day`` is case-insensitive. ``until`` is the bare close
label the panel renders as "UNTIL 3". Parsing is tolerant: a bad/empty entry is
skipped rather than crashing the sign."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional

# Weekday name -> Mon=0..Sun=6 (lower-cased; common short forms accepted too).
_WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2, "weds": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}


@dataclass(frozen=True)
class Market:
    """A market open today, shaped for the screen.

    ``name`` is the display name (fit to the panel by the scene). ``until`` is the
    bare close label, rendered as "UNTIL <until>" (e.g. "3" -> "UNTIL 3")."""
    name: str
    until: str


@dataclass(frozen=True)
class MarketSpec:
    """One parsed config entry: which weekday it runs and its season window.

    ``season_start``/``season_end`` are inclusive bounds, or None for a market
    that's always in season."""
    name: str
    weekday: int                       # Mon=0..Sun=6
    until: str
    season_start: Optional[date] = None
    season_end: Optional[date] = None

    def open_on(self, day: date, weekday: int) -> bool:
        """True when this market runs on ``weekday`` and ``day`` is in season."""
        if weekday != self.weekday:
            return False
        if self.season_start is not None and day < self.season_start:
            return False
        if self.season_end is not None and day > self.season_end:
            return False
        return True


def _parse_date(value) -> Optional[date]:
    """An ISO date from a string/date, or None if it can't be read."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return None


def _parse_season(season) -> tuple[Optional[date], Optional[date]]:
    """An inclusive ``(start, end)`` pair from a config ``season`` value.

    Accepts a ``[start, end]`` pair (either side may be blank/None for open-ended)
    or a missing value (always in season). Unparseable bounds become None."""
    if not season:
        return (None, None)
    if isinstance(season, (list, tuple)):
        start = _parse_date(season[0]) if len(season) >= 1 else None
        end = _parse_date(season[1]) if len(season) >= 2 else None
        return (start, end)
    return (None, None)


def parse_specs(entries) -> List[MarketSpec]:
    """Parse a list of plain config dicts into ``MarketSpec``s.

    Each entry needs a recognizable ``day`` and a ``name``; a ``season`` is
    optional (always in season without one). Entries we can't parse are skipped,
    so one bad line never takes the feature down."""
    specs: List[MarketSpec] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        day = str(entry.get("day", "")).strip().lower()
        weekday = _WEEKDAYS.get(day)
        if weekday is None:
            continue
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        until = str(entry.get("until", "")).strip()
        start, end = _parse_season(entry.get("season"))
        specs.append(MarketSpec(name=name, weekday=weekday, until=until,
                                season_start=start, season_end=end))
    return specs


def market_today(specs: List[MarketSpec], now: datetime) -> Optional[Market]:
    """The configured market open *today*, or None.

    "Today" means ``now``'s weekday matches the spec's day AND ``now.date()`` is
    within ``[season_start, season_end]`` inclusive. If several specs match, the
    first one wins."""
    today = now.date()
    weekday = now.weekday()
    for spec in specs:
        if spec.open_on(today, weekday):
            return Market(name=spec.name, until=spec.until)
    return None


# --- panel-fit place label -------------------------------------------------
# Compact place labels for the 64px panel: drop the bit after ":"/"(",
# abbreviate "Square" -> "SQ", and strip generic suffixes so the distinctive
# name shows. (Lives here because the market scene is the only remaining caller.)
_VENUE_TRIM = re.compile(r"\s*[:(].*$")          # drop "Park: Bandshell" / "(...)"
_VENUE_DROP = re.compile(
    r"\b(park|playground|ballfields?|greenmarket|field|garden|center|plaza)\b", re.I)
_SQUARE = re.compile(r"\bsquare\b", re.I)
_PLACE_MAX_PX = 62               # must fit the 64px panel with a 1px margin


def short_place(name: str) -> str:
    """A panel-ready place label: ``"Tompkins Square Park"`` -> ``"TOMPKINS SQ"``.

    Drops trailing qualifiers (``Park``, ``Playground``, …), abbreviates
    ``Square`` to ``SQ``, and — if still too wide — keeps the single most
    distinctive (last) word so something legible always fits."""
    from ..display import scenery as S          # local import: keep this module UI-free at top level
    base = _VENUE_TRIM.sub("", name or "").strip()
    base = _SQUARE.sub("SQ", base)
    base = _VENUE_DROP.sub("", base)
    base = re.sub(r"\s+", " ", base).strip(" -,").upper() or (name or "").upper()
    if S.text_width(base) <= _PLACE_MAX_PX:
        return base
    words = base.split()
    return words[-1] if words else base          # the namesake word ("HERNANDEZ")
