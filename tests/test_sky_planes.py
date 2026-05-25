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
    p = nearest_plane(ADSB, LAT, LON, min_alt_ft=1000)
    assert isinstance(p, Plane)
    assert p.callsign == "BAW178"            # closest airborne above the floor
    assert p.dir == "NE"                     # track 61 deg
    assert p.alt_ft == 35000                 # alt_baro is feet already
    assert 0 <= p.heading_deg < 360
    assert p.route is None                   # parsing alone does not add a route


def test_nearest_plane_handles_adsb_lol_ac_key():
    # adsb.lol / airplanes.live return the array under "ac" instead of "aircraft".
    data = {"ac": ADSB["aircraft"]}
    p = nearest_plane(data, LAT, LON, key="ac", min_alt_ft=1000)
    assert p is not None and p.callsign == "BAW178"


def test_nearest_plane_empty_and_missing():
    assert nearest_plane({"aircraft": []}, LAT, LON) is None
    assert nearest_plane({"aircraft": None}, LAT, LON) is None
    assert nearest_plane({}, LAT, LON) is None
    assert nearest_plane(None, LAT, LON) is None


def test_nearest_plane_all_filtered_out_returns_none():
    assert nearest_plane(ADSB, LAT, LON, min_alt_ft=99_000) is None


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
    assert p.callsign == "BAW178" and p.route == "JFK > LHR"


def test_fetch_overhead_falls_back_to_second_feed():
    lol = {"ac": ADSB["aircraft"]}            # adsb.lol-shaped payload

    def flaky(url):
        if "adsb.fi" in url:
            raise RuntimeError("adsb.fi down")
        return lol

    p = fetch_overhead(LAT, LON, fetcher=flaky, route_fetcher=lambda url: ROUTE)
    assert p is not None and p.callsign == "BAW178"


def test_fetch_overhead_all_feeds_down_returns_none():
    def boom(url):
        raise RuntimeError("everything down")

    assert fetch_overhead(LAT, LON, fetcher=boom, route_fetcher=lambda u: {}) is None


def test_fetch_overhead_keeps_plane_when_route_unavailable():
    notfound = {"status": "404", "error": "Route not found."}
    p = fetch_overhead(LAT, LON, fetcher=lambda url: ADSB,
                       route_fetcher=lambda url: notfound)
    assert p is not None and p.callsign == "BAW178" and p.route is None
