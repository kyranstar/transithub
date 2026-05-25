"""Offline tests for the config-driven birthday logic.

No network: birthdays come from plain config dicts (as parsed from YAML). ``now``
is pinned so "whose birthday is today" is deterministic. Yennifer/09-17 is the
documented placeholder and the backbone case."""
from __future__ import annotations

from datetime import datetime

from transithub.birthdays import BirthdaySpec, birthday_today, parse_specs

YEN = {"name": "Yennifer", "date": "09-17"}


# --- spec parsing ----------------------------------------------------------
def test_parse_basic_mmdd():
    assert parse_specs([YEN]) == [BirthdaySpec(name="Yennifer", month=9, day=17)]


def test_parse_single_digit_month_day():
    specs = parse_specs([{"name": "Sam", "date": "3-4"}])
    assert specs and specs[0].month == 3 and specs[0].day == 4


def test_parse_ignores_leading_year():
    specs = parse_specs([{"name": "Ana", "date": "1990-12-25"}])
    assert specs and (specs[0].month, specs[0].day) == (12, 25)


def test_parse_skips_bad_entries():
    specs = parse_specs([
        {"name": "Good", "date": "09-17"},
        {"name": "No date"},                        # missing date -> skipped
        {"name": "Bad date", "date": "soon"},       # unparseable -> skipped
        {"name": "Out of range", "date": "13-40"},  # invalid month/day -> skipped
        {"date": "01-01"},                          # missing name -> skipped
        "not a dict",                               # wrong type -> skipped
    ])
    assert [s.name for s in specs] == ["Good"]


def test_parse_preserves_order():
    specs = parse_specs([{"name": "A", "date": "01-02"}, {"name": "B", "date": "03-04"}])
    assert [s.name for s in specs] == ["A", "B"]


# --- birthday_today: month+day, any year -----------------------------------
def test_birthday_today_matches_regardless_of_year():
    specs = parse_specs([YEN])
    assert birthday_today(specs, datetime(2026, 9, 17, 0, 0)) == "Yennifer"   # midnight
    assert birthday_today(specs, datetime(2031, 9, 17, 23, 59)) == "Yennifer"  # other year


def test_birthday_today_wrong_day_is_none():
    specs = parse_specs([YEN])
    assert birthday_today(specs, datetime(2026, 9, 16, 12, 0)) is None
    assert birthday_today(specs, datetime(2026, 10, 17, 12, 0)) is None


def test_birthday_today_first_match_wins():
    specs = parse_specs([{"name": "First", "date": "09-17"},
                         {"name": "Second", "date": "09-17"}])
    assert birthday_today(specs, datetime(2026, 9, 17, 8, 0)) == "First"


def test_birthday_today_empty_is_none():
    assert birthday_today([], datetime(2026, 9, 17)) is None


def test_birthday_today_leap_day():
    specs = parse_specs([{"name": "Leap", "date": "02-29"}])
    assert birthday_today(specs, datetime(2024, 2, 29, 12, 0)) == "Leap"   # leap year
    assert birthday_today(specs, datetime(2025, 2, 28, 12, 0)) is None     # non-leap
