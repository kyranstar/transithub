"""Next ISS pass over a fixed spot, computed locally from a keyless TLE.

We fetch the station's two-line element set from Celestrak (no key) and propagate
it with SGP4. The standard transform is:

    SGP4 -> TEME position (km)
    rotate by GMST          -> Earth-fixed (ECEF) position
    subtract observer ECEF  -> topocentric vector
    project onto E/N/Up     -> azimuth + elevation

A pass is a stretch where the elevation clears a ~10-deg horizon mask; we sample
minute-by-minute, refine the boundaries to the nearest few seconds, and report
the rise direction, peak elevation, and (best-effort) naked-eye visibility.

Accuracy is a few degrees — plenty for a "look that way" prompt. References:
Vallado, *Fundamentals of Astrodynamics*; the SGP4 library docs; Meeus for the
solar position used in the visibility check."""
from __future__ import annotations

import math
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sgp4.api import Satrec, jday

from . import IssPass

ISS_CATNR = 25544
TLE_URL = f"https://celestrak.org/NORAD/elements/gp.php?CATNR={ISS_CATNR}&FORMAT=TLE"

COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
HORIZON_MASK_DEG = 10.0            # below this the station is lost in clutter/haze

# WGS-84 ellipsoid
_WGS84_A = 6378.137                # equatorial radius, km
_WGS84_F = 1.0 / 298.257223563     # flattening
_WGS84_E2 = _WGS84_F * (2 - _WGS84_F)


def _default_fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "transithub"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


def parse_tle(text: str) -> Tuple[str, str, str]:
    """Split a TLE blob into (name, line1, line2). Tolerates a missing name line."""
    lines = [ln.rstrip() for ln in text.strip().splitlines() if ln.strip()]
    if len(lines) >= 3 and lines[-2].lstrip().startswith("1 ") and lines[-1].lstrip().startswith("2 "):
        return lines[-3].strip(), lines[-2].strip(), lines[-1].strip()
    if len(lines) >= 2 and lines[0].lstrip().startswith("1 "):
        return "ISS", lines[0].strip(), lines[1].strip()
    raise ValueError("not a two-line element set")


def az_to_compass(az_deg: float) -> str:
    """Nearest of the 8 compass points for an azimuth in degrees (0 = N, 90 = E)."""
    return COMPASS[int((az_deg % 360) / 45 + 0.5) % 8]


def _gmst_rad(jd_ut1: float) -> float:
    """Greenwich Mean Sidereal Time (IAU-82), radians."""
    t = (jd_ut1 - 2451545.0) / 36525.0
    g = (280.46061837 + 360.98564736629 * (jd_ut1 - 2451545.0)
         + 0.000387933 * t * t - t * t * t / 38710000.0)
    return math.radians(g % 360.0)


def _observer_ecef(lat_deg: float, lon_deg: float, alt_km: float) -> Tuple[float, float, float]:
    latr, lonr = math.radians(lat_deg), math.radians(lon_deg)
    n = _WGS84_A / math.sqrt(1 - _WGS84_E2 * math.sin(latr) ** 2)
    x = (n + alt_km) * math.cos(latr) * math.cos(lonr)
    y = (n + alt_km) * math.cos(latr) * math.sin(lonr)
    z = (n * (1 - _WGS84_E2) + alt_km) * math.sin(latr)
    return x, y, z


def _teme_to_ecef(r: Tuple[float, float, float], theta: float) -> Tuple[float, float, float]:
    c, s = math.cos(theta), math.sin(theta)
    x, y, z = r
    return c * x + s * y, -s * x + c * y, z


def _azel_from_sat(sat: Satrec, when: datetime, lat: float, lon: float,
                   alt_km: float) -> Optional[Tuple[float, float, float]]:
    when = when.astimezone(timezone.utc)
    jd, fr = jday(when.year, when.month, when.day, when.hour, when.minute,
                  when.second + when.microsecond / 1e6)
    err, r, _v = sat.sgp4(jd, fr)
    if err != 0:
        return None
    theta = _gmst_rad(jd + fr)
    sx, sy, sz = _teme_to_ecef(r, theta)
    ox, oy, oz = _observer_ecef(lat, lon, alt_km)
    rx, ry, rz = sx - ox, sy - oy, sz - oz
    latr, lonr = math.radians(lat), math.radians(lon)
    east = -math.sin(lonr) * rx + math.cos(lonr) * ry
    north = (-math.sin(latr) * math.cos(lonr) * rx
             - math.sin(latr) * math.sin(lonr) * ry + math.cos(latr) * rz)
    up = (math.cos(latr) * math.cos(lonr) * rx
          + math.cos(latr) * math.sin(lonr) * ry + math.sin(latr) * rz)
    rng = math.sqrt(rx * rx + ry * ry + rz * rz)
    el = math.degrees(math.asin(max(-1.0, min(1.0, up / rng))))
    az = math.degrees(math.atan2(east, north)) % 360.0
    return az, el, rng


def observer_azel(line1: str, line2: str, when: datetime, lat: float, lon: float,
                  alt_km: float = 0.01) -> Tuple[float, float, float]:
    """Azimuth, elevation (deg) and slant range (km) of the satellite at `when`.

    `when` may be naive (treated as UTC) or tz-aware. Raises on a propagation
    error — callers that want graceful failure go through `next_pass`."""
    sat = Satrec.twoline2rv(line1, line2)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    res = _azel_from_sat(sat, when, lat, lon, alt_km)
    if res is None:
        raise ValueError("SGP4 propagation error")
    return res


# --- naked-eye visibility (best effort) -------------------------------------
def _sun_ecef_unit(when: datetime) -> Tuple[float, float, float]:
    """Unit vector toward the Sun in ECEF (low-precision Meeus solar position)."""
    when = when.astimezone(timezone.utc)
    jd, fr = jday(when.year, when.month, when.day, when.hour, when.minute,
                  when.second + when.microsecond / 1e6)
    d = (jd + fr) - 2451545.0
    g = math.radians((357.529 + 0.98560028 * d) % 360)
    q = (280.459 + 0.98564736 * d) % 360
    lam = math.radians((q + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) % 360)
    eps = math.radians(23.439 - 0.00000036 * d)
    # equatorial (TEME-ish) unit vector, then rotate to ECEF by GMST
    xe = math.cos(lam)
    ye = math.cos(eps) * math.sin(lam)
    ze = math.sin(eps) * math.sin(lam)
    return _teme_to_ecef((xe, ye, ze), _gmst_rad(jd + fr))


def _is_visible(sat: Satrec, when: datetime, lat: float, lon: float) -> bool:
    """True when the station is sunlit and the observer is in darkness.

    Sunlit: the satellite is not inside Earth's cylindrical shadow. Observer
    dark: the Sun is below the horizon at the ground site."""
    when = when.astimezone(timezone.utc)
    jd, fr = jday(when.year, when.month, when.day, when.hour, when.minute,
                  when.second + when.microsecond / 1e6)
    err, r, _v = sat.sgp4(jd, fr)
    if err != 0:
        return False
    sat_ecef = _teme_to_ecef(r, _gmst_rad(jd + fr))
    sun = _sun_ecef_unit(when)
    # component of the satellite position along the Sun direction
    along = sat_ecef[0] * sun[0] + sat_ecef[1] * sun[1] + sat_ecef[2] * sun[2]
    perp = math.sqrt(max(0.0, sum(c * c for c in sat_ecef) - along * along))
    sunlit = along > 0 or perp > _WGS84_A      # in front of Earth, or outside its shadow tube
    # observer darkness: Sun elevation < -6 deg (civil twilight) at the site
    latr, lonr = math.radians(lat), math.radians(lon)
    up = (math.cos(latr) * math.cos(lonr) * sun[0]
          + math.cos(latr) * math.sin(lonr) * sun[1] + math.sin(latr) * sun[2])
    observer_dark = math.degrees(math.asin(max(-1.0, min(1.0, up)))) < -6.0
    return sunlit and observer_dark


def next_pass(tle_text: str, lat: float, lon: float, when: Optional[datetime] = None,
              hours: float = 6.0, alt_km: float = 0.01,
              step_s: int = 60) -> Optional[IssPass]:
    """The next pass that clears the horizon mask within `hours` of `when`.

    Returns None on a bad TLE, a propagation failure, or simply no pass in the
    window. Never raises on bad input."""
    try:
        _name, l1, l2 = parse_tle(tle_text)
        sat = Satrec.twoline2rv(l1, l2)
    except Exception:
        return None

    start_t = (when or datetime.now(timezone.utc))
    if start_t.tzinfo is None:
        start_t = start_t.replace(tzinfo=timezone.utc)

    horizon = HORIZON_MASK_DEG
    n_steps = max(1, int(hours * 3600 / step_s))
    prev_el = None
    rise_t: Optional[datetime] = None

    for i in range(n_steps + 1):
        t = start_t + timedelta(seconds=i * step_s)
        res = _azel_from_sat(sat, t, lat, lon, alt_km)
        if res is None:
            return None
        _az, el, _rng = res

        if rise_t is None:
            # look for a crossing up through the mask
            if prev_el is not None and prev_el < horizon <= el:
                rise_t = _refine_crossing(sat, t - timedelta(seconds=step_s), t,
                                          lat, lon, alt_km, horizon, rising=True)
            elif i == 0 and el >= horizon:
                rise_t = t                      # already up at the window start
            if rise_t is not None:
                set_t = _scan_to_set(sat, rise_t, lat, lon, alt_km, horizon, hours, step_s)
                return _summarize(sat, rise_t, set_t, lat, lon, alt_km)
        prev_el = el

    return None


def _refine_crossing(sat: Satrec, t0: datetime, t1: datetime, lat: float, lon: float,
                     alt_km: float, horizon: float, rising: bool) -> datetime:
    """Bisection to the ~second where elevation crosses the horizon mask."""
    for _ in range(8):                          # 60 s -> ~0.25 s after 8 halvings
        mid = t0 + (t1 - t0) / 2
        res = _azel_from_sat(sat, mid, lat, lon, alt_km)
        el = res[1] if res else horizon
        above = el >= horizon
        if above == rising:
            t1 = mid
        else:
            t0 = mid
    return t0 + (t1 - t0) / 2


def _scan_to_set(sat: Satrec, rise_t: datetime, lat: float, lon: float, alt_km: float,
                 horizon: float, hours: float, step_s: int) -> datetime:
    t = rise_t
    end_limit = rise_t + timedelta(hours=hours)
    prev = rise_t
    while t < end_limit:
        t = t + timedelta(seconds=step_s)
        res = _azel_from_sat(sat, t, lat, lon, alt_km)
        if res is None or res[1] < horizon:
            return _refine_crossing(sat, prev, t, lat, lon, alt_km, horizon, rising=False)
        prev = t
    return prev


def _summarize(sat: Satrec, rise_t: datetime, set_t: datetime, lat: float, lon: float,
               alt_km: float) -> IssPass:
    # rise azimuth -> compass
    rise = _azel_from_sat(sat, rise_t, lat, lon, alt_km)
    rise_az = rise[0] if rise else 0.0
    # peak elevation by fine sampling across the pass
    peak_t, peak_el = rise_t, -90.0
    span = (set_t - rise_t).total_seconds()
    samples = max(4, int(span / 10))
    for k in range(samples + 1):
        t = rise_t + timedelta(seconds=span * k / samples)
        res = _azel_from_sat(sat, t, lat, lon, alt_km)
        if res and res[1] > peak_el:
            peak_el, peak_t = res[1], t
    visible = _is_visible(sat, peak_t, lat, lon)
    return IssPass(
        start=rise_t.astimezone(timezone.utc),
        peak=peak_t.astimezone(timezone.utc),
        end=set_t.astimezone(timezone.utc),
        max_el_deg=round(peak_el, 1),
        rise_dir=az_to_compass(rise_az),
        visible=visible,
    )
