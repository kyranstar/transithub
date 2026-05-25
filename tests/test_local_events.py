"""Offline tests for the events client (NYC Parks Events Listing family).

The injected fetcher serves the three trimmed real tables from
tests/fixtures/events_sample.json (listing / locations / categories), keyed by
which resource the URL targets. `now` is pinned to a fixture date so the
today/tomorrow window is deterministic."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from transithub.local.events import (EventsClient, is_outdoor,
                                      is_kids_only, when_label, kind_label)

FIX = Path(__file__).parent / "fixtures"
SAMPLE = json.loads((FIX / "events_sample.json").read_text())

HOME = (40.70, -73.92)

# Fixture events are dated 2016-07-14 (a Thursday) and 2016-07-15.
TODAY = datetime(2016, 7, 14, 9, 0)


def _fetch(url: str):
    if "fudw-fgrp" in url:
        return SAMPLE["listing"]
    if "cpcm-i88g" in url:
        return SAMPLE["locations"]
    if "xtsw-fqvh" in url:
        return SAMPLE["categories"]
    raise AssertionError(f"unexpected url {url}")


def _client(now=TODAY, **kw):
    return EventsClient(HOME[0], HOME[1], fetcher=_fetch, now=lambda: now, **kw)


def _labels(events):
    return {e.label for e in events}


# --- helpers ---------------------------------------------------------------
def test_when_label_formats_evening_and_noon():
    assert when_label("19:00") == "7 PM"
    assert when_label("20:30") == "8:30 PM"
    assert when_label("12:00") == "NOON"
    assert when_label("09:00") == "9 AM"


def test_is_kids_only():
    # Topic tags (Film) do NOT rescue a "Best for Kids" event -> a kids movie stays out.
    assert is_kids_only({"Best for Kids", "Film"}) is True
    assert is_kids_only({"Best for Kids"}) is True              # children audience
    assert is_kids_only({"CityParks Kids Arts"}) is True        # kids program series
    # An explicit adult tag rescues a family event as general-audience.
    assert is_kids_only({"Best for Kids", "City Parks Foundation Adults"}) is False
    assert is_kids_only({"Concerts", "Festivals"}) is False     # no kids tag at all


def test_kind_label():
    assert kind_label({"Film", "Best for Kids"}) == "PARK MOVIE"
    assert kind_label({"Concerts"}) == "CONCERT"
    assert kind_label({"Festivals", "Art"}) == "FESTIVAL"   # festivals checked first
    assert kind_label(set(), "Summer Concert Series") == "CONCERT"   # title fallback
    assert kind_label(set()) == "PARK EVENT"                # generic fallback


def test_is_outdoor():
    assert is_outdoor({"Concerts", "Festivals"}, "Maria Hernandez Park") is True
    assert is_outdoor({"Concerts"}, "Metropolitan Recreation Center") is False  # rec center
    assert is_outdoor({"Historic House Trust Sites"}, "Old Stone House") is False
    assert is_outdoor({"Film"}, "McCarren Park") is True


# --- filtering -------------------------------------------------------------
def test_keeps_free_outdoor_general_today():
    # 125901 "Back to the Block" @ Maria Hernandez Park: free, outdoor, general,
    # today -> the headline qualifier.
    events = _client().upcoming()
    assert "BACK TO THE BLOCK" in " ".join(_labels(events)).upper() or any(
        "BLOCK" in e.label.upper() for e in events)
    block = next(e for e in events if "BLOCK" in e.label.upper())
    assert block.when_label == "5 PM"
    assert "HERNANDEZ" in block.venue.upper()
    assert block.kind == "CONCERT"          # Concerts category -> short type headline
    assert block.dist_km < 0.7


def test_excludes_paid():
    # 100578 fundraising picnic is cost_free=0 -> never appears.
    assert not any("PICNIC" in e.label.upper() for e in _client().upcoming())


def test_excludes_kids_only_movies():
    # The two "Movies in the Parks" rows are 'Best for Kids' with no general cat.
    assert not any("MOVIES" in e.label.upper() or "KARATE" in e.label.upper()
                   or "FROZEN" in e.label.upper() for e in _client().upcoming())


def test_excludes_indoor_concert():
    # 178718 concert is at a Historic House (indoor) -> excluded though free+today.
    assert not any("SHARON" in e.label.upper() for e in _client().upcoming())


def test_excludes_far_event():
    # 100074 Pooch Parade is free+outdoor+general but on Staten Island (~28 km).
    assert not any("POOCH" in e.label.upper() for e in _client().upcoming())


def test_tomorrow_included_today_plus_one():
    # 116681 Karate Kid is dated 2016-07-15 (tomorrow from TODAY) but it's kids-only,
    # so use a date check that doesn't depend on it: nothing dated 2016-07-13 leaks in.
    # Pin now to 2016-07-13 -> the 07-14 block party is "tomorrow" and still kept.
    events = _client(now=datetime(2016, 7, 13, 9, 0)).upcoming()
    assert any("BLOCK" in e.label.upper() for e in events)


def test_excludes_past_and_far_future():
    # Pin now to 2016-07-20: every fixture event is in the past -> empty.
    assert _client(now=datetime(2016, 7, 20, 9, 0)).upcoming() == []


def test_sorted_soonest_first():
    events = _client().upcoming()
    starts = [e.start for e in events]
    assert starts == sorted(starts)


# --- robustness ------------------------------------------------------------
def test_empty_feeds_return_empty():
    c = EventsClient(HOME[0], HOME[1], fetcher=lambda url: [], now=lambda: TODAY)
    assert c.upcoming() == []


def test_fetch_failure_returns_empty():
    def boom(url):
        raise RuntimeError("offline")
    c = EventsClient(HOME[0], HOME[1], fetcher=boom, now=lambda: TODAY)
    assert c.upcoming() == []


def test_missing_location_is_skipped():
    # A listing row with no matching location can't be distance-filtered -> dropped.
    def fetch(url):
        if "fudw-fgrp" in url:
            return [{"event_id": "999", "title": "Ghost Event",
                     "date": "2016-07-14T00:00:00.000", "start_time": "18:00",
                     "end_time": "20:00", "cost_free": "1"}]
        if "cpcm-i88g" in url:
            return []
        return [{"event_id": "999", "name": "Festivals"}]
    c = EventsClient(HOME[0], HOME[1], fetcher=fetch, now=lambda: TODAY)
    assert c.upcoming() == []
