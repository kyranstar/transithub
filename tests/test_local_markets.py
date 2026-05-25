"""Offline tests for the farmers-markets client (NYC Open Data 8vwk-6iz2).

The injected fetcher returns the trimmed real response in
tests/fixtures/markets_sample.json, so nothing here touches the network. `now`
is pinned to a known weekday/season to make "open today" deterministic."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from transithub.local.markets import MarketsClient, Market, parse_close_label, weekdays_of

FIX = Path(__file__).parent / "fixtures"
SAMPLE = json.loads((FIX / "markets_sample.json").read_text())

HOME = (40.70, -73.92)

# Fixture weekdays (in-season month): a Wednesday and a Saturday in summer.
WED = datetime(2025, 7, 16, 10, 0)     # Hope Ballfield (Wed) is nearest & open
SAT = datetime(2025, 7, 19, 10, 0)     # Maria Hernandez (Sat) is nearest & open
TUE = datetime(2025, 7, 15, 10, 0)     # no market open on Tuesday in the fixture
JAN_WED = datetime(2025, 1, 15, 10, 0)  # winter Wednesday: seasonal markets out of season


def _client(now, **kw):
    return MarketsClient(HOME[0], HOME[1], fetcher=lambda url: SAMPLE["markets"], now=lambda: now, **kw)


# --- weekday parsing -------------------------------------------------------
def test_weekdays_single():
    assert weekdays_of("Wednesday") == {2}
    assert weekdays_of("Saturday") == {5}


def test_weekdays_separators_and_typos():
    assert weekdays_of("Monday & Wedneday") == {0, 2}          # typo 'Wedneday'
    assert weekdays_of("Tuesday\nThursday\nSaturday") == {1, 3, 5}
    assert weekdays_of("Tusday & Saturday") == {1, 5}          # typo 'Tusday'
    assert weekdays_of("Wednesday & Sunday (starting 5/5)") == {2, 6}


def test_weekdays_range():
    assert weekdays_of("Mon-Sat") == {0, 1, 2, 3, 4, 5}
    assert weekdays_of("Tuesday-Friday") == {1, 2, 3, 4}


def test_weekdays_unparseable_is_empty():
    assert weekdays_of("TBD") == set()
    assert weekdays_of("") == set()


# --- close-time parsing ----------------------------------------------------
def test_close_label_basic():
    assert parse_close_label("9 a.m. - 3 p.m.") == "UNTIL 3"
    assert parse_close_label("8 a.m. - 3 p.m.") == "UNTIL 3"


def test_close_label_no_space_and_halfhour():
    assert parse_close_label("9a.m. - 2 p.m.") == "UNTIL 2"
    assert parse_close_label("9 a.m. - 2:30 p.m.") == "UNTIL 2:30"


def test_close_label_noon_and_morning_close():
    assert parse_close_label("noon - 3 p.m.") == "UNTIL 3"
    assert parse_close_label("8 a.m. - 11 a.m.") == "UNTIL 11AM"   # morning close keeps am marker


def test_close_label_multi_segment_takes_a_close():
    # "8 a.m. - 2 p.m. (W); 9 a.m. - 2 p.m. (SU)" both close at 2pm
    assert parse_close_label("8 a.m. - 2 p.m. (W); 9 a.m. - 2 p.m. (SU)") == "UNTIL 2"


def test_close_label_unparseable_is_none():
    assert parse_close_label("hours vary") is None
    assert parse_close_label("") is None


# --- selection: nearest open today ----------------------------------------
def test_picks_nearest_open_today_wed():
    m = _client(WED).best()
    assert isinstance(m, Market)
    assert "HOPE" in m.name or "Hope" in m.name
    assert m.close_label == "UNTIL 3"
    assert m.dist_km < 0.6


def test_picks_nearest_open_today_sat():
    m = _client(SAT).best()
    assert m is not None and "HERNANDEZ" in m.name.upper()
    assert m.dist_km < 0.7


def test_none_when_nothing_open_today():
    assert _client(TUE).best() is None


def test_seasonal_excluded_in_winter_but_year_round_kept():
    # In January, Wednesday: Hope Ballfield is seasonal (out), no year-round Wed market
    # within radius, so nothing qualifies.
    assert _client(JAN_WED).best() is None


def test_year_round_open_in_winter():
    # McCarren (Saturday, year-round) qualifies on a winter Saturday even though
    # seasonal Saturday markets are out of season.
    m = _client(datetime(2025, 1, 18, 10, 0)).best()
    assert m is not None and "MCCARREN" in m.name.upper()


# --- radius + latest-year + robustness ------------------------------------
def test_radius_filters_far_markets():
    # Bay Ridge (Saturday) is ~13 km away; with a tiny radius nothing qualifies Sat
    # except the near Saturday markets — shrink radius below the nearest Sat market.
    assert _client(SAT, radius_km=0.1).best() is None


def test_latest_year_only():
    # The 2024 "Stale Year Market" (Wednesday, on top of home) must be ignored;
    # the Wednesday winner is the 2025 Hope Ballfield, not the stale row.
    m = _client(WED).best()
    assert m is not None and "STALE" not in m.name.upper()


def test_never_crashes_on_garbage():
    bad = [{"marketname": "X", "latitude": "nope", "longitude": None,
            "daysoperation": "Wednesday", "hoursoperations": "9 a.m. - 3 p.m.",
            "open_year_round": "Yes", "year": "2025"},
           {"marketname": "Y"}]  # missing everything
    c = MarketsClient(HOME[0], HOME[1], fetcher=lambda url: bad, now=lambda: WED)
    assert c.best() is None       # the only structured row has an unparseable location


def test_fetch_failure_returns_none():
    def boom(url):
        raise RuntimeError("network down")
    c = MarketsClient(HOME[0], HOME[1], fetcher=boom, now=lambda: WED)
    assert c.best() is None
