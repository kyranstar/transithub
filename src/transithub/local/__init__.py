"""Neighborhood content: what's on near home today.

Two free, keyless NYC Open Data feeds (Socrata) power this:

- Farmers markets — "DOHMH Farmers Markets" (resource 8vwk-6iz2 on
  data.cityofnewyork.us): name, lat/lon, day(s) of operation, hours, and whether
  it runs year-round. `markets.py` picks the single nearest market that is open
  *today*.
- Free outdoor events — the "NYC Parks Events Listing" family (Event Listing
  fudw-fgrp + Event Locations cpcm-i88g + Event Categories xtsw-fqvh, joined by
  event_id): title, start/end time, lat/lon, free flag, and categories.
  `events.py` keeps the free, outdoor, general-audience ones happening today or
  tomorrow near home.

A background poller fills `LocalData` (the same snapshot pattern as the weather
holder); scene sources read it off `ctx.local`. Everything degrades to "show
nothing" on bad or missing data — never a crash, never a guess we can't stand
behind."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .events import Event, EventsClient
from .markets import Market, MarketsClient

__all__ = [
    "LocalData", "LocalHolder",
    "Market", "MarketsClient", "Event", "EventsClient",
]


@dataclass(frozen=True)
class LocalData:
    """Latest neighborhood snapshot handed to sources via ``ctx.local``.

    ``market`` is the single best market open today (or None). ``events`` is a
    short, already-filtered list of qualifying happenings (possibly empty)."""
    market: Optional[Market] = None
    events: List[Event] = field(default_factory=list)


class LocalHolder:
    """Thread-safe latest-snapshot holder a poller updates and the Director reads.

    Mirrors the weather holder: ``poll()`` refetches both feeds and never raises
    (a failed fetch just yields fewer items). ``current`` is the last good (or
    empty) snapshot."""

    def __init__(self, markets: Optional[MarketsClient] = None,
                 events: Optional[EventsClient] = None):
        self._markets = markets
        self._events = events
        self._data = LocalData()

    @property
    def current(self) -> LocalData:
        return self._data

    def poll(self) -> LocalData:
        market = None
        events: List[Event] = []
        if self._markets is not None:
            try:
                market = self._markets.best()
            except Exception:
                market = None
        if self._events is not None:
            try:
                events = self._events.upcoming()
            except Exception:
                events = []
        self._data = LocalData(market=market, events=events)
        return self._data
