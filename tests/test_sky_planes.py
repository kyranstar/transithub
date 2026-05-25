"""Offline tests for keyless ADS-B plane-overhead parsing + route lookup.

Uses captured fixtures (a real adsb.fi-shaped response and a real hexdb route
response), so nothing here touches the network."""
import json
from pathlib import Path

from transithub.sky.planes import (Plane, fetch_overhead, format_route,
                                    icao_to_iata, lookup_route, nearest_plane,
                                    parse_aircraft)

FIX = Path(__file__).parent / "fixtures"
ADSB = json.loads((FIX / "adsb_states.json").read_text())
ROUTE = json.loads((FIX / "hexdb_route.json").read_text())

LAT, LON = 40.69, -73.92


# -------------------------------------------------------- aircraft parsing
def test_parse_skips_ground_low_and_null_alt():
    # Floor ~1000 ft drops the ground craft, the 350-ft one, and the null-alt one.
    planes = parse_aircraft(ADSB, LAT, LON, min_alt_ft=1000)
    callsigns = {p.callsign for p in planes}
    assert "JBU1727" not in callsigns        # alt_baro == "ground"
    assert "UAL1624" not in callsigns        # airborne but only 350 ft
    assert "NKS221" not in callsigns         # alt_baro is null
    assert {"BAW178", "UAL415", "DAL336"} <= callsigns


def test_nearest_plane_picks_closest_airborne():
    # Slant-range ranking: the 8,175 ft UAL415 (the audible one) beats the
    # 35,000 ft BAW178 that is nearer in horizontal distance but inaudible overhead.
    p = nearest_plane(ADSB, LAT, LON, min_alt_ft=1000)
    assert isinstance(p, Plane)
    assert p.callsign == "UAL415"            # smallest slant range above the floor
    assert p.dir == "SW"                     # track 218 deg
    assert p.alt_ft == 8175                  # alt_baro is feet already
    assert 0 <= p.heading_deg < 360
    assert p.route is None                   # parsing alone does not add a route


def test_nearest_plane_ranks_by_slant_not_horizontal():
    # A high jet nearly overhead vs a low plane slightly off-axis. Horizontal
    # distance favors the high one; slant range (and audibility) favors the low one.
    data = {"aircraft": [
        {"flight": "HIGH1", "alt_baro": 35000, "track": 90.0,
         "lat": LAT + 0.002, "lon": LON},   # ~0.2 km horizontally, but 35,000 ft up
        {"flight": "LOW1", "alt_baro": 2000, "track": 90.0,
         "lat": LAT + 0.02, "lon": LON},    # ~2.2 km horizontally, but only 2,000 ft up
    ]}
    p = nearest_plane(data, LAT, LON, min_alt_ft=1000)
    assert p is not None and p.callsign == "LOW1"


def test_nearest_plane_handles_adsb_lol_ac_key():
    # adsb.lol / airplanes.live return the array under "ac" instead of "aircraft".
    data = {"ac": ADSB["aircraft"]}
    p = nearest_plane(data, LAT, LON, key="ac", min_alt_ft=1000)
    assert p is not None and p.callsign == "UAL415"


def test_nearest_plane_empty_and_missing():
    assert nearest_plane({"aircraft": []}, LAT, LON) is None
    assert nearest_plane({"aircraft": None}, LAT, LON) is None
    assert nearest_plane({}, LAT, LON) is None
    assert nearest_plane(None, LAT, LON) is None


def test_nearest_plane_all_filtered_out_returns_none():
    assert nearest_plane(ADSB, LAT, LON, min_alt_ft=99_000) is None


def test_max_altitude_keeps_only_audible_traffic():
    # With an audibility ceiling, the high cruisers (BAW178 35000, DAL336 18500) drop
    # and the low climbing/descending plane (UAL415 8175) becomes the one overhead —
    # so the scene tracks a plane you could actually hear, not a jet at cruise.
    p = nearest_plane(ADSB, LAT, LON, min_alt_ft=1000, max_alt_ft=10000)
    assert p is not None and p.callsign == "UAL415" and p.alt_ft == 8175
    cs = {x.callsign for x in parse_aircraft(ADSB, LAT, LON, min_alt_ft=1000,
                                             max_alt_ft=10000)}
    assert "BAW178" not in cs and "DAL336" not in cs


def test_parse_tolerates_malformed_rows():
    bad = {"aircraft": [None, 5, "x", {"alt_baro": "ground"}, {"alt_baro": 9000}]}
    # Must not raise; rows without a usable position are skipped.
    out = parse_aircraft(bad, LAT, LON)
    assert isinstance(out, list) and out == []


def test_parse_uses_true_heading_when_track_missing():
    data = {"aircraft": [
        {"flight": "TST123  ", "alt_baro": 10000, "true_heading": 90.0,
         "lat": LAT, "lon": LON},
    ]}
    p = nearest_plane(data, LAT, LON, min_alt_ft=1000)
    assert p is not None and p.callsign == "TST123"
    assert p.dir == "E"                       # 90 deg from true_heading fallback


# ------------------------------------------------------------ ICAO -> IATA
def test_icao_to_iata_uses_builtin_map():
    assert icao_to_iata("KJFK") == "JFK"
    assert icao_to_iata("EGLL") == "LHR"      # non-US needs the map
    assert icao_to_iata("OMDB") == "DXB"


def test_icao_to_iata_strips_leading_k_for_unknown_us():
    assert icao_to_iata("KXYZ") == "XYZ"      # unknown US-style 4-letter
    assert icao_to_iata("ZZZZ") == "ZZZZ"     # unknown non-US: returned as-is


# ------------------------------------------------------------- route join
def test_format_route_two_legs():
    assert format_route("KJFK-EGLL") == "JFK > LHR"


def test_format_route_multileg_uses_origin_and_final_dest():
    assert format_route("KLAX-KDFW-KLAX") == "LAX > LAX"


def test_format_route_bad_inputs():
    assert format_route(None) is None
    assert format_route("") is None
    assert format_route("KJFK") is None       # need at least origin + dest


def test_lookup_route_from_fixture():
    assert lookup_route("BAW178", fetcher=lambda url: ROUTE) == "JFK > LHR"


def test_lookup_route_handles_404_and_errors():
    notfound = {"status": "404", "error": "Route not found."}
    assert lookup_route("XXX1", fetcher=lambda url: notfound) is None

    def boom(url):
        raise RuntimeError("hexdb down")

    assert lookup_route("BAW178", fetcher=boom) is None
    assert lookup_route("", fetcher=lambda url: ROUTE) is None
    assert lookup_route("UNKNOWN", fetcher=lambda url: ROUTE) is None


# ----------------------------------------------------- fetch_overhead glue
def test_fetch_overhead_primary_with_route():
    p = fetch_overhead(LAT, LON, fetcher=lambda url: ADSB,
                       route_fetcher=lambda url: ROUTE)
    assert isinstance(p, Plane)
    assert p.callsign == "UAL415" and p.route == "JFK > LHR"


def test_fetch_overhead_falls_back_to_second_feed():
    lol = {"ac": ADSB["aircraft"]}            # adsb.lol-shaped payload

    def flaky(url):
        if "adsb.fi" in url:
            raise RuntimeError("adsb.fi down")
        return lol

    p = fetch_overhead(LAT, LON, fetcher=flaky, route_fetcher=lambda url: ROUTE)
    assert p is not None and p.callsign == "UAL415"


def test_fetch_overhead_all_feeds_down_returns_none():
    def boom(url):
        raise RuntimeError("everything down")

    assert fetch_overhead(LAT, LON, fetcher=boom, route_fetcher=lambda u: {}) is None


def test_fetch_overhead_keeps_plane_when_route_unavailable():
    notfound = {"status": "404", "error": "Route not found."}
    p = fetch_overhead(LAT, LON, fetcher=lambda url: ADSB,
                       route_fetcher=lambda url: notfound)
    assert p is not None and p.callsign == "UAL415" and p.route is None
