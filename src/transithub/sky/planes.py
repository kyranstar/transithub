"""Nearest airborne aircraft overhead, from keyless community ADS-B feeds.

We query a community ADS-B aggregator for a small radius around the configured
spot and pick the closest airborne craft above a sensible altitude floor. Three
keyless feeds are tried in order so a single flaky host never blanks the sky:

    adsb.fi  (primary)  -> {"aircraft": [...]}
    adsb.lol (fallback) -> {"ac": [...]}
    airplanes.live      -> {"ac": [...]}

Each aircraft row carries the callsign, barometric altitude, ground track and
position. Unlike OpenSky's anonymous tier these feeds don't include the flight's
origin/destination, so we look the route up separately from hexdb.io (also
keyless) and format it as IATA codes (e.g. ``"JFK > LHR"``). Every fetch degrades
to None on any error; a missing route just leaves ``Plane.route`` as None."""
from __future__ import annotations

import json
import math
import urllib.request
from typing import Callable, List, Optional, Tuple

from . import Plane

# Keyless ADS-B feeds, tried in order. Each returns aircraft under a different key.
# ``dist`` is in nautical miles for all three.
ADSB_SOURCES: Tuple[Tuple[str, str], ...] = (
    ("https://opendata.adsb.fi/api/v2/lat/{lat}/lon/{lon}/dist/{nm}", "aircraft"),
    ("https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{nm}", "ac"),
    ("https://api.airplanes.live/v2/point/{lat}/{lon}/{nm}", "ac"),
)

# Keyless route lookup: GET .../route/icao/<callsign> -> {"route": "KJFK-EGLL"}.
ROUTE_URL = "https://hexdb.io/api/v1/route/icao/{callsign}"

DEFAULT_RADIUS_NM = 3              # ~3.5 mi: close enough to genuinely be "above you"
DEFAULT_MIN_ALT_FT = 1000          # ignore aircraft on approach/departure on the deck
# Only count planes low enough to actually hear, so "overhead" tracks what you'd
# notice outside — high cruising traffic (35,000 ft) is constant but inaudible.
DEFAULT_MAX_ALT_FT = 12000
COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")

# A small built-in ICAO -> IATA map for busy airports, so the common routes
# resolve offline without a per-airport network round-trip. Unknown codes fall
# back to the ICAO with a leading "K" stripped (US-style), e.g. KBOS -> BOS.
ICAO_TO_IATA = {
    # New York / busy US hubs
    "KJFK": "JFK", "KLGA": "LGA", "KEWR": "EWR", "KBOS": "BOS", "KDCA": "DCA",
    "KIAD": "IAD", "KPHL": "PHL", "KORD": "ORD", "KMDW": "MDW", "KATL": "ATL",
    "KLAX": "LAX", "KSFO": "SFO", "KSEA": "SEA", "KDFW": "DFW", "KDEN": "DEN",
    "KMIA": "MIA", "KFLL": "FLL", "KMCO": "MCO", "KLAS": "LAS", "KPHX": "PHX",
    "KIAH": "IAH", "KCLT": "CLT", "KDTW": "DTW", "KMSP": "MSP", "KBWI": "BWI",
    "KSLC": "SLC", "KSAN": "SAN", "KTPA": "TPA", "KPDX": "PDX", "KAUS": "AUS",
    # Canada / Mexico
    "CYYZ": "YYZ", "CYUL": "YUL", "CYVR": "YVR", "MMMX": "MEX",
    # Europe
    "EGLL": "LHR", "EGKK": "LGW", "EGGW": "LTN", "EGSS": "STN", "EGLC": "LCY",
    "LFPG": "CDG", "LFPO": "ORY", "EHAM": "AMS", "EDDF": "FRA", "EDDM": "MUC",
    "LEMD": "MAD", "LEBL": "BCN", "LIRF": "FCO", "LIMC": "MXP", "LSZH": "ZRH",
    "EIDW": "DUB", "LPPT": "LIS", "EKCH": "CPH", "ESSA": "ARN", "ENGM": "OSL",
    "LTFM": "IST", "LOWW": "VIE", "EDDB": "BER", "LFLL": "LYS",
    # Middle East / Asia / Pacific
    "OMDB": "DXB", "OTHH": "DOH", "OMAA": "AUH", "VHHH": "HKG", "RJTT": "HND",
    "RJAA": "NRT", "RKSI": "ICN", "ZBAA": "PEK", "ZSPD": "PVG", "WSSS": "SIN",
    "VIDP": "DEL", "VABB": "BOM", "YSSY": "SYD", "YMML": "MEL", "NZAA": "AKL",
    # Latin America
    "SBGR": "GRU", "SAEZ": "EZE", "SKBO": "BOG", "MPTO": "PTY",
}


def _default_fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "transithub"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _heading_to_compass(deg: float) -> str:
    return COMPASS[int((deg % 360) / 45 + 0.5) % 8]


def icao_to_iata(icao: str) -> str:
    """Best-effort IATA code for an ICAO airport code, using a built-in map.

    Falls back to stripping a leading "K" for US-style four-letter codes
    (KBOS -> BOS); other unknown codes are returned unchanged."""
    code = (icao or "").strip().upper()
    if code in ICAO_TO_IATA:
        return ICAO_TO_IATA[code]
    if len(code) == 4 and code.startswith("K"):
        return code[1:]
    return code


def format_route(route: Optional[str]) -> Optional[str]:
    """Turn a hexdb ``ORIGIN-DEST`` (or multi-leg ``A-B-C``) ICAO route into a
    short ``IATA > IATA`` label (origin and final destination), or None.

    The spleen font has no right-arrow glyph (U+2192), so we use ``>`` — it
    renders and reads clearly at this size."""
    if not route:
        return None
    legs = [seg.strip() for seg in route.split("-") if seg.strip()]
    if len(legs) < 2:
        return None
    origin, dest = icao_to_iata(legs[0]), icao_to_iata(legs[-1])
    if not origin or not dest:
        return None
    return f"{origin} > {dest}"


def adsb_url(template: str, lat: float, lon: float, radius_nm: int) -> str:
    return template.format(lat=round(lat, 5), lon=round(lon, 5), nm=int(radius_nm))


def _aircraft_list(data: dict, key: str) -> list:
    """The aircraft array from a feed response. Tolerates either feed's key."""
    if not isinstance(data, dict):
        return []
    rows = data.get(key)
    if rows is None:                                # accept the other feed's key too
        rows = data.get("aircraft") or data.get("ac")
    return rows if isinstance(rows, list) else []


def _row_to_plane(a: dict, lat: float, lon: float, min_alt_ft: float,
                  max_alt_ft: Optional[float] = None):
    """(slant_m, Plane) for a usable airborne row, else None.

    Skips on-ground craft (``alt_baro == "ground"``), rows missing a position or
    altitude, anything below the floor, and (when ``max_alt_ft`` is set) anything
    above it — the ceiling keeps it to planes low enough to actually hear."""
    try:
        if not isinstance(a, dict):
            return None
        alt = a.get("alt_baro")
        if alt == "ground":                         # explicitly on the deck
            return None
        if not isinstance(alt, (int, float)):       # null / missing / non-numeric
            return None
        alt_ft = float(alt)
        if alt_ft < min_alt_ft:
            return None
        if max_alt_ft is not None and alt_ft > max_alt_ft:
            return None
        plat, plon = a.get("lat"), a.get("lon")
        if not isinstance(plat, (int, float)) or not isinstance(plon, (int, float)):
            return None
        track = a.get("track")
        if not isinstance(track, (int, float)):
            track = a.get("true_heading")
        heading = float(track) if isinstance(track, (int, float)) else 0.0
        callsign = (a.get("flight") or "").strip() or "UNKNOWN"
        # Rank by slant range (true 3D distance), so a low, near plane beats a high
        # one passing overhead — the low one is the one you'd actually hear. Horizontal
        # offset is planar (longitude scaled by latitude); both legs converted to metres
        # (~111,320 m per degree of latitude, 0.3048 m per foot).
        dlat = plat - lat
        dlon = (plon - lon) * math.cos(math.radians(lat))
        horizontal_m = math.hypot(dlat, dlon) * 111_320
        slant_m = math.hypot(horizontal_m, alt_ft * 0.3048)
        plane = Plane(callsign=callsign, alt_ft=int(round(alt_ft)),
                      heading_deg=heading, dir=_heading_to_compass(heading))
        return slant_m, plane
    except (TypeError, ValueError):
        return None


def parse_aircraft(data: dict, lat: float, lon: float, key: str = "aircraft",
                   min_alt_ft: float = DEFAULT_MIN_ALT_FT,
                   max_alt_ft: Optional[float] = None) -> List[Plane]:
    """All usable airborne aircraft in a feed response, nearest first.

    ``max_alt_ft`` (when set) drops anything above the ceiling, so only low,
    audible traffic counts as overhead."""
    found = []
    for a in _aircraft_list(data, key):
        hit = _row_to_plane(a, lat, lon, min_alt_ft, max_alt_ft)
        if hit is not None:
            found.append(hit)
    found.sort(key=lambda dp: dp[0])
    return [p for _d, p in found]


def nearest_plane(data: dict, lat: float, lon: float, key: str = "aircraft",
                  min_alt_ft: float = DEFAULT_MIN_ALT_FT,
                  max_alt_ft: Optional[float] = None) -> Optional[Plane]:
    """The closest airborne aircraft within the altitude band in one response."""
    planes = parse_aircraft(data, lat, lon, key, min_alt_ft, max_alt_ft)
    return planes[0] if planes else None


def lookup_route(callsign: str,
                 fetcher: Callable[[str], dict] = _default_fetch) -> Optional[str]:
    """Formatted ``IATA > IATA`` route for a callsign via hexdb.io, or None.

    Returns None on any error or when no route is on file (hexdb 404s with an
    ``error`` field, which has no usable ``route``)."""
    callsign = (callsign or "").strip()
    if not callsign or callsign == "UNKNOWN":
        return None
    try:
        data = fetcher(ROUTE_URL.format(callsign=callsign))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return format_route(data.get("route"))


def fetch_overhead(lat: float, lon: float, radius_nm: int = DEFAULT_RADIUS_NM,
                   min_alt_ft: float = DEFAULT_MIN_ALT_FT,
                   max_alt_ft: Optional[float] = None,
                   fetcher: Callable[[str], dict] = _default_fetch,
                   route_fetcher: Callable[[str], dict] = _default_fetch) -> Optional[Plane]:
    """Nearest airborne plane over the spot, with its route when known, or None.

    Tries each ADS-B feed in turn (adsb.fi, then adsb.lol, then airplanes.live);
    the first that yields a usable aircraft wins. Any feed error is swallowed and
    the next is tried; if none yield a plane we return None. The route lookup is
    best-effort — a failure there just leaves ``route=None``."""
    plane: Optional[Plane] = None
    for template, key in ADSB_SOURCES:
        try:
            data = fetcher(adsb_url(template, lat, lon, radius_nm))
        except Exception:
            continue
        plane = nearest_plane(data, lat, lon, key, min_alt_ft, max_alt_ft)
        if plane is not None:
            break
    if plane is None:
        return None
    route = lookup_route(plane.callsign, route_fetcher)
    if route is not None:
        plane = Plane(callsign=plane.callsign, alt_ft=plane.alt_ft,
                      heading_deg=plane.heading_deg, dir=plane.dir, route=route)
    return plane
