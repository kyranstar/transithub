"""The keyless sky client: next ISS pass + nearest plane overhead.

Two independent queries on different cadences (the ISS TLE is good for hours; a
plane is overhead for seconds), so the coordinator polls the two methods at the
intervals advertised by ``POLL_INTERVALS``. Every method degrades to None on a
network or parse error — the display never crashes on a bad sky fetch."""
from __future__ import annotations

import time
from typing import Callable, Optional

from . import IssPass, Plane
from .iss import TLE_URL, next_pass
from .iss import _default_fetch as _default_text_fetch
from .planes import DEFAULT_MAX_ALT_FT, DEFAULT_MIN_ALT_FT, DEFAULT_RADIUS_NM
from .planes import _default_fetch as _default_json_fetch
from .planes import fetch_overhead

# Recommended poll cadences for the coordinator (seconds).
POLL_INTERVALS = {"iss": 300, "plane": 60}

_TLE_TTL_S = 12 * 3600          # a TLE stays accurate for ~half a day
_PASS_LOOKAHEAD_H = 6.0         # search this far ahead for the next pass


class SkyClient:
    """Computes the next ISS pass (locally, from a cached TLE) and the nearest
    plane overhead (from keyless community ADS-B feeds, with a hexdb.io route
    lookup). Fetchers are injectable for offline tests."""

    def __init__(self, lat: float, lon: float,
                 tle_fetcher: Callable[[str], str] = _default_text_fetch,
                 states_fetcher: Callable[[str], dict] = _default_json_fetch,
                 route_fetcher: Callable[[str], dict] = _default_json_fetch,
                 radius_nm: int = DEFAULT_RADIUS_NM,
                 min_alt_ft: float = DEFAULT_MIN_ALT_FT,
                 max_alt_ft: float = DEFAULT_MAX_ALT_FT,
                 clock: Callable[[], float] = time.monotonic):
        self.lat = lat
        self.lon = lon
        self._fetch_tle = tle_fetcher
        self._fetch_states = states_fetcher
        self._fetch_route = route_fetcher
        self.radius_nm = radius_nm
        self.min_alt_ft = min_alt_ft
        self.max_alt_ft = max_alt_ft
        self._clock = clock
        self._tle_text: Optional[str] = None
        self._tle_at: float = -1e18

    # -- TLE caching -------------------------------------------------------
    def _tle(self) -> Optional[str]:
        if self._tle_text is not None and (self._clock() - self._tle_at) < _TLE_TTL_S:
            return self._tle_text
        try:
            text = self._fetch_tle(TLE_URL)
        except Exception:
            return self._tle_text          # keep a stale TLE rather than going blind
        if text and "1 " in text:
            self._tle_text = text
            self._tle_at = self._clock()
        return self._tle_text

    # -- public API --------------------------------------------------------
    def iss_pass(self) -> Optional[IssPass]:
        """Next ISS pass over the spot within the lookahead window, or None."""
        tle = self._tle()
        if not tle:
            return None
        return next_pass(tle, self.lat, self.lon, hours=_PASS_LOOKAHEAD_H)

    def plane_overhead(self) -> Optional[Plane]:
        """Nearest low, audible aircraft within the search radius right now, or None."""
        return fetch_overhead(self.lat, self.lon, self.radius_nm, self.min_alt_ft,
                              max_alt_ft=self.max_alt_ft, fetcher=self._fetch_states,
                              route_fetcher=self._fetch_route)
