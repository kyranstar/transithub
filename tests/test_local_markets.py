"""Offline tests for the config-driven farmers-market logic.

No network, no Socrata: markets come from plain config dicts (as parsed from
YAML). ``now`` is pinned so "open today" — today's weekday in season — is
deterministic. The Maria Hernandez example from the owner is the backbone case:
every Saturday, 2026-05-23 to 2026-11-22, until 3."""
from __future__ import annotations

from datetime import datetime

from transithub.local.markets import Market, market_today, parse_specs

# Maria Hernandez: every Saturday, in season 2026-05-23 .. 2026-11-22, until 3.
MARIA = {"name": "MARIA HERNANDEZ", "day": "saturday",
         "season": ["2026-05-23", "2026-11-22"], "until": "3"}

IN_SEASON_SAT = datetime(2026, 5, 30, 10, 0)    # a Saturday inside the window
IN_SEASON_FRI = datetime(2026, 5, 29, 10, 0)    # a Friday inside the window
BEFORE_SEASON_SAT = datetime(2026, 5, 16, 10, 0)  # Saturday a week before season opens
AFTER_SEASON_SAT = datetime(2026, 11, 28, 10, 0)  # Saturday after season closes


# --- spec parsing ----------------------------------------------------------
def test_parse_basic_entry():
    specs = parse_specs([MARIA])
    assert len(specs) == 1
    s = specs[0]
    assert s.name == "MARIA HERNANDEZ" and s.weekday == 5 and s.until == "3"
    assert (s.season_start, s.season_end) == (
        datetime(2026, 5, 23).date(), datetime(2026, 11, 22).date())


def test_parse_day_case_insensitive():
    specs = parse_specs([{"name": "X", "day": "SaTuRdAy", "until": "2"}])
    assert specs and specs[0].weekday == 5


def test_parse_missing_season_means_always():
    specs = parse_specs([{"name": "X", "day": "tuesday", "until": "2"}])
    assert specs and specs[0].season_start is None and specs[0].season_end is None


def test_parse_skips_bad_entries():
    specs = parse_specs([
        {"name": "Good", "day": "monday", "until": "1"},
        {"name": "No day", "until": "1"},            # missing/unknown day -> skipped
        {"name": "Bad day", "day": "funday", "until": "1"},  # unknown weekday -> skipped
        {"day": "monday", "until": "1"},             # missing name -> skipped
        "not a dict",                                # wrong type -> skipped
    ])
    assert [s.name for s in specs] == ["Good"]


# --- market_today: weekday + season window ---------------------------------
def test_in_season_saturday_shows():
    m = market_today(parse_specs([MARIA]), IN_SEASON_SAT)
    assert isinstance(m, Market)
    assert m.name == "MARIA HERNANDEZ" and m.until == "3"


def test_wrong_day_is_none():
    assert market_today(parse_specs([MARIA]), IN_SEASON_FRI) is None


def test_before_season_is_none():
    assert market_today(parse_specs([MARIA]), BEFORE_SEASON_SAT) is None


def test_after_season_is_none():
    assert market_today(parse_specs([MARIA]), AFTER_SEASON_SAT) is None


def test_season_bounds_inclusive():
    # The exact start and end dates both count as in season.
    start_sat = datetime(2026, 5, 23, 10, 0)        # season_start, a Saturday
    end_sun = datetime(2026, 11, 22, 9, 0)          # season_end (a Sunday)
    assert market_today(parse_specs([MARIA]), start_sat) is not None
    sun_market = {"name": "SUNDAY MKT", "day": "sunday",
                  "season": ["2026-05-24", "2026-11-22"], "until": "2"}
    assert market_today(parse_specs([sun_market]), end_sun) is not None


def test_no_season_spec_always_in_season():
    spec = {"name": "ALL YEAR", "day": "saturday", "until": "4"}
    # A summer Saturday and a deep-winter Saturday both qualify.
    assert market_today(parse_specs([spec]), datetime(2026, 7, 18, 10, 0)) is not None
    assert market_today(parse_specs([spec]), datetime(2026, 1, 17, 10, 0)) is not None


def test_open_ended_season_one_sided():
    # Only an end bound: open before it, closed after it.
    spec = parse_specs([{"name": "TILL FALL", "day": "saturday",
                         "season": [None, "2026-09-26"], "until": "3"}])
    assert market_today(spec, datetime(2026, 6, 6, 10, 0)) is not None     # before end
    assert market_today(spec, datetime(2026, 10, 3, 10, 0)) is None        # after end


# --- multiple specs --------------------------------------------------------
def test_multiple_specs_returns_first_match():
    sat_a = {"name": "FIRST SAT", "day": "saturday",
             "season": ["2026-05-23", "2026-11-22"], "until": "3"}
    sat_b = {"name": "SECOND SAT", "day": "saturday",
             "season": ["2026-05-23", "2026-11-22"], "until": "2"}
    m = market_today(parse_specs([sat_a, sat_b]), IN_SEASON_SAT)
    assert m is not None and m.name == "FIRST SAT"   # first matching spec wins


def test_multiple_specs_picks_the_open_one():
    sun = {"name": "SUNDAY MKT", "day": "sunday", "until": "2"}
    sat = {"name": "SATURDAY MKT", "day": "saturday", "until": "3"}
    m = market_today(parse_specs([sun, sat]), IN_SEASON_SAT)
    assert m is not None and m.name == "SATURDAY MKT"  # only Saturday is open today


def test_empty_specs_is_none():
    assert market_today([], IN_SEASON_SAT) is None
    assert market_today(parse_specs([]), IN_SEASON_SAT) is None


# --- daily close-time gating ----------------------------------------------
def test_closed_after_until_hour_is_none():
    # MARIA runs "until 3" -> open at 2pm, gone by 3pm, not lingering at 8pm.
    specs = parse_specs([MARIA])
    assert market_today(specs, datetime(2026, 5, 30, 14, 0)) is not None   # 2pm: open
    assert market_today(specs, datetime(2026, 5, 30, 15, 0)) is None       # 3pm: closed
    assert market_today(specs, datetime(2026, 5, 30, 20, 0)) is None       # 8pm: closed


def test_close_hour_parsing():
    from transithub.local.markets import _close_hour
    assert _close_hour("3") == 15            # bare number -> afternoon/evening
    assert _close_hour("6") == 18
    assert _close_hour("noon") == 12
    assert _close_hour("11 AM") == 11
    assert _close_hour("") is None           # unreadable -> no daily cutoff


def test_market_without_until_has_no_cutoff():
    # No "until" label -> shows all day on its market day (no close gating).
    specs = parse_specs([{"name": "ALLDAY", "day": "saturday"}])
    assert market_today(specs, datetime(2026, 5, 30, 23, 0)) is not None
