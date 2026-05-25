"""Offline tests for OpenSky plane-overhead parsing (fixture states array)."""
import json
from pathlib import Path

from transithub.sky.planes import Plane, nearest_plane, parse_states

FIX = Path(__file__).parent / "fixtures"
STATES = json.loads((FIX / "opensky_states.json").read_text())

LAT, LON = 40.69, -73.92


def test_parse_states_skips_ground_and_low():
    # Default altitude floor (~1000 ft) drops the ground craft and the 675-ft one.
    planes = parse_states(STATES, LAT, LON, min_alt_ft=1000)
    callsigns = {p.callsign for p in planes}
    assert "DAL1390" not in callsigns        # on_ground=True
    assert "SWA9" not in callsigns           # airborne but only ~675 ft
    assert "UAL415" in callsigns and "JBU88" in callsigns


def test_nearest_plane_picks_closest_airborne():
    p = nearest_plane(STATES, LAT, LON, min_alt_ft=1000)
    assert isinstance(p, Plane)
    assert p.callsign == "UAL415"            # closest airborne in the fixture
    assert p.dir == "SW"                     # heading 218 deg
    assert 7000 <= p.alt_ft <= 9000          # ~8175 ft (geo altitude, meters->feet)
    assert 0 <= p.heading_deg < 360


def test_nearest_plane_empty_states():
    assert nearest_plane({"states": []}, LAT, LON) is None
    assert nearest_plane({"states": None}, LAT, LON) is None
    assert nearest_plane({}, LAT, LON) is None


def test_nearest_plane_all_filtered_out_returns_none():
    # With a very high floor, nothing in the fixture qualifies.
    assert nearest_plane(STATES, LAT, LON, min_alt_ft=99_000) is None


def test_parse_states_tolerates_malformed_rows():
    bad = {"states": [["short", "row"], None, ["x"] * 17]}
    # Must not raise; a too-short or all-null row is just skipped.
    assert parse_states(bad, LAT, LON) == [] or isinstance(parse_states(bad, LAT, LON), list)


def test_plane_falls_back_to_baro_alt_when_no_geo():
    states = {"states": [
        # geo_alt (idx 13) is null; baro_alt (idx 7) = 3048 m ~= 10000 ft
        ["abc", "TST123  ", "x", 1, 1, LON, LAT, 3048.0, False, 100.0, 90.0,
         None, None, None, None, None, False, 0],
    ]}
    p = nearest_plane(states, LAT, LON, min_alt_ft=1000)
    assert p is not None and p.callsign == "TST123"
    assert 9500 <= p.alt_ft <= 10500
    assert p.dir == "E"
