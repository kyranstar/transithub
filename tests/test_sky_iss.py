"""Offline tests for ISS pass prediction (SGP4 from a fixture TLE).

We do not hard-assert exact azimuth/elevation (a tiny change in the propagation
math or the fixture epoch would make that brittle); instead we assert the shape:
sane types, ranges, a valid compass point, and a chronologically ordered pass."""
from datetime import datetime, timezone
from pathlib import Path

from transithub.sky.iss import (COMPASS, IssPass, az_to_compass, next_pass,
                                 observer_azel, parse_tle)

FIX = Path(__file__).parent / "fixtures"
TLE_TEXT = (FIX / "iss_tle.txt").read_text()

# A few hours before the epoch's first good pass; well inside TLE validity.
WHEN = datetime(2026, 5, 24, 0, 0, 0, tzinfo=timezone.utc)
LAT, LON = 40.69, -73.92


def test_parse_tle_returns_two_lines():
    name, l1, l2 = parse_tle(TLE_TEXT)
    assert l1.startswith("1 25544") and l2.startswith("2 25544")
    assert "ISS" in name


def test_observer_azel_ranges():
    name, l1, l2 = parse_tle(TLE_TEXT)
    az, el, rng = observer_azel(l1, l2, WHEN, LAT, LON)
    assert 0.0 <= az < 360.0
    assert -90.0 <= el <= 90.0
    # Overhead the slant range is a few hundred km; for a satellite below the
    # horizon (far side of Earth) it grows toward Earth-diameter + orbit (~13000 km).
    assert 200.0 < rng < 13_000.0


def test_observer_azel_close_when_overhead():
    # 02:10 UTC on the TLE day is a high pass (~65 deg); the range must be small.
    name, l1, l2 = parse_tle(TLE_TEXT)
    overhead = datetime(2026, 5, 24, 2, 10, 0, tzinfo=timezone.utc)
    az, el, rng = observer_azel(l1, l2, overhead, LAT, LON)
    assert el > 40.0                     # high in the sky
    assert 200.0 < rng < 1200.0          # near the orbital altitude


def test_az_to_compass_cardinals():
    assert az_to_compass(0) == "N"
    assert az_to_compass(90) == "E"
    assert az_to_compass(180) == "S"
    assert az_to_compass(270) == "W"
    assert az_to_compass(45) == "NE"
    assert az_to_compass(359) == "N"
    assert az_to_compass(360) == "N"      # wraps


def test_next_pass_is_sane():
    p = next_pass(TLE_TEXT, LAT, LON, when=WHEN, hours=24)
    assert isinstance(p, IssPass)
    assert p.start < p.peak                       # rise precedes the high point
    assert p.peak <= p.end                        # peak within the pass
    assert 10.0 <= p.max_el_deg <= 90.0           # cleared the 10-deg horizon mask
    assert p.rise_dir in COMPASS
    assert isinstance(p.visible, bool)
    # tz-aware UTC timestamps come back out
    assert p.start.tzinfo is not None


def test_next_pass_starts_after_when():
    p = next_pass(TLE_TEXT, LAT, LON, when=WHEN, hours=24)
    assert p.start >= WHEN


def test_next_pass_none_when_no_pass_in_short_window():
    # A 1-minute window almost certainly contains no rise above 10 deg.
    p = next_pass(TLE_TEXT, LAT, LON, when=WHEN, hours=0.016)  # ~1 min
    assert p is None


def test_next_pass_handles_garbage_tle():
    assert next_pass("not a tle\nat all\n", LAT, LON, when=WHEN, hours=6) is None


# ============================================================== SkyClient
from transithub.sky import IssPass as _IssPass  # noqa: E402
from transithub.sky import Plane, SkyClient  # noqa: E402


def test_client_caches_tle_across_iss_calls():
    calls = {"n": 0}

    def tle_fetch(url):
        calls["n"] += 1
        return TLE_TEXT

    c = SkyClient(LAT, LON, tle_fetcher=tle_fetch, clock=lambda: 0.0)
    c.iss_pass()
    c.iss_pass()
    assert calls["n"] == 1                       # second call served from cache


def test_client_refetches_tle_after_ttl():
    calls = {"n": 0}
    t = {"now": 0.0}

    def tle_fetch(url):
        calls["n"] += 1
        return TLE_TEXT

    c = SkyClient(LAT, LON, tle_fetcher=tle_fetch, clock=lambda: t["now"])
    c.iss_pass()
    t["now"] = 13 * 3600                          # past the ~12h TTL
    c.iss_pass()
    assert calls["n"] == 2


def test_client_iss_pass_none_on_fetch_error():
    def boom(url):
        raise RuntimeError("network down")

    assert SkyClient(LAT, LON, tle_fetcher=boom).iss_pass() is None


def test_client_plane_uses_injected_states_and_route_fetchers():
    import json as _json
    states = _json.loads((FIX / "adsb_states.json").read_text())
    route = _json.loads((FIX / "hexdb_route.json").read_text())
    c = SkyClient(LAT, LON, states_fetcher=lambda url: states,
                  route_fetcher=lambda url: route)
    p = c.plane_overhead()
    assert isinstance(p, Plane) and p.callsign == "BAW178"
    assert p.route == "JFK > LHR"             # route lookup wired through the client


def test_client_plane_none_on_fetch_error():
    def boom(url):
        raise RuntimeError("network down")

    assert SkyClient(LAT, LON, states_fetcher=boom).plane_overhead() is None
