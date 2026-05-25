"""Nearest airborne aircraft overhead, from OpenSky's anonymous API (no key).

We query a small box around the configured spot and pick the closest airborne
craft above a sensible altitude floor. OpenSky's anonymous tier gives position,
altitude, heading and callsign — but NOT the origin/destination route, so we
never claim one. The state-vector layout is OpenSky's documented order; we read
it by index and tolerate short or null-filled rows."""
from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from typing import Callable, List, Optional

from . import Plane

STATES_URL = "https://opensky-network.org/api/states/all"

# OpenSky state-vector indices (https://openskynetwork.github.io/opensky-api/).
_CALLSIGN, _LON, _LAT, _BARO_ALT = 1, 5, 6, 7
_ON_GROUND, _VELOCITY, _TRACK, _GEO_ALT = 8, 9, 10, 13

_M_TO_FT = 3.28084
DEFAULT_BOX_DEG = 0.15             # +/- around the spot (~10 mi N-S, ~8 mi E-W at NYC)
DEFAULT_MIN_ALT_FT = 1000          # ignore aircraft on approach/departure on the deck
COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def _default_fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "transithub"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _heading_to_compass(deg: float) -> str:
    return COMPASS[int((deg % 360) / 45 + 0.5) % 8]


def states_url(lat: float, lon: float, box_deg: float = DEFAULT_BOX_DEG) -> str:
    q = urllib.parse.urlencode({
        "lamin": round(lat - box_deg, 4), "lomin": round(lon - box_deg, 4),
        "lamax": round(lat + box_deg, 4), "lomax": round(lon + box_deg, 4),
    })
    return f"{STATES_URL}?{q}"


def _row_to_plane(s: list, lat: float, lon: float, min_alt_ft: float):
    """(distance_deg, Plane) for a usable airborne row, else None."""
    try:
        if len(s) <= _GEO_ALT:
            return None
        if s[_ON_GROUND]:
            return None
        plon, plat = s[_LON], s[_LAT]
        if plon is None or plat is None:
            return None
        alt_m = s[_GEO_ALT] if s[_GEO_ALT] is not None else s[_BARO_ALT]
        if alt_m is None:
            return None
        alt_ft = alt_m * _M_TO_FT
        if alt_ft < min_alt_ft:
            return None
        heading = s[_TRACK] if s[_TRACK] is not None else 0.0
        callsign = (s[_CALLSIGN] or "").strip() or "UNKNOWN"
        # planar distance in degrees, longitude scaled by latitude
        dlat = plat - lat
        dlon = (plon - lon) * math.cos(math.radians(lat))
        dist = math.hypot(dlat, dlon)
        plane = Plane(callsign=callsign, alt_ft=int(round(alt_ft)),
                      heading_deg=float(heading), dir=_heading_to_compass(heading))
        return dist, plane
    except (TypeError, IndexError, ValueError):
        return None


def parse_states(data: dict, lat: float, lon: float,
                 min_alt_ft: float = DEFAULT_MIN_ALT_FT) -> List[Plane]:
    """All usable airborne aircraft in the response, nearest first."""
    states = (data or {}).get("states") or []
    found = []
    for s in states:
        if not isinstance(s, (list, tuple)):
            continue
        hit = _row_to_plane(s, lat, lon, min_alt_ft)
        if hit is not None:
            found.append(hit)
    found.sort(key=lambda dp: dp[0])
    return [p for _d, p in found]


def nearest_plane(data: dict, lat: float, lon: float,
                  min_alt_ft: float = DEFAULT_MIN_ALT_FT) -> Optional[Plane]:
    """The closest airborne aircraft above the floor, or None."""
    planes = parse_states(data, lat, lon, min_alt_ft)
    return planes[0] if planes else None


def fetch_overhead(lat: float, lon: float, box_deg: float = DEFAULT_BOX_DEG,
                   min_alt_ft: float = DEFAULT_MIN_ALT_FT,
                   fetcher: Callable[[str], dict] = _default_fetch) -> Optional[Plane]:
    """Query OpenSky for the box and return the nearest plane (or None on any error)."""
    try:
        data = fetcher(states_url(lat, lon, box_deg))
    except Exception:
        return None
    return nearest_plane(data, lat, lon, min_alt_ft)
