"""Quiet until something is actually wrong.

Pollers report each success/failure here; `warnings()` stays empty while data is
fresh and only speaks up for a real problem — every feed failing (Wi-Fi down), or
weather/arrivals gone stale well past their polling interval."""
from __future__ import annotations

import threading
from datetime import datetime
from typing import List, Optional

from .clock import now as now_eastern

# A feed is "stale" once its newest good data is older than this. Generous
# multiples of each poll interval, so a single hiccup never trips a warning.
WEATHER_STALE_S = 1800     # weather polls every ~600s
ARRIVALS_STALE_S = 300     # arrivals poll every ~30s
OFFLINE_AFTER_S = 120      # everything failing this long => treat as offline


class HealthMonitor:
    """Thread-safe record of which feeds are healthy. Written by pollers, read by
    the render loop."""

    def __init__(self, now_fn=now_eastern, weather_stale_s: int = WEATHER_STALE_S,
                 arrivals_stale_s: int = ARRIVALS_STALE_S,
                 offline_after_s: int = OFFLINE_AFTER_S):
        self._now = now_fn
        self._weather_stale = weather_stale_s
        self._arrivals_stale = arrivals_stale_s
        self._offline_after = offline_after_s
        self._lock = threading.Lock()
        self._last_ok: dict[str, datetime] = {}
        self._last_fail: dict[str, datetime] = {}

    def ok(self, feed: str) -> None:
        with self._lock:
            self._last_ok[feed] = self._now()

    def fail(self, feed: str, exc: Optional[Exception] = None) -> None:
        with self._lock:
            self._last_fail[feed] = self._now()

    def _age(self, feed: str, now: datetime) -> Optional[float]:
        ok = self._last_ok.get(feed)
        return None if ok is None else (now - ok).total_seconds()

    def warnings(self) -> List[str]:
        """Zero or more short, glanceable warnings (most severe first)."""
        now = self._now()
        with self._lock:
            feeds = set(self._last_ok) | set(self._last_fail)
            if not feeds:
                return []

            # Offline: nothing has succeeded recently but failures are arriving.
            recent_ok = any(
                (age := self._age(f, now)) is not None and age <= self._offline_after
                for f in feeds
            )
            recent_fail = any(
                (fail := self._last_fail.get(f)) is not None
                and (now - fail).total_seconds() <= self._offline_after
                for f in feeds
            )
            if recent_fail and not recent_ok:
                return ["OFFLINE"]

            out: List[str] = []
            wx = self._age("weather", now)
            if "weather" in feeds and (wx is None or wx > self._weather_stale):
                out.append("WEATHER STALE")
            ar = self._age("arrivals", now)
            if "arrivals" in feeds and (ar is None or ar > self._arrivals_stale):
                out.append("TRAINS STALE")
            return out
