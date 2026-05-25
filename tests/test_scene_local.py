"""Render + fit tests for the neighborhood scenes and their sources.

No network: scenes are built from plain dataclasses, sources from a Context whose
``local`` snapshot we set directly. Every text line must fit the 64px panel."""
from __future__ import annotations

from datetime import datetime

from transithub.display import scenery as S
from transithub.display.director import Context
from transithub.display.scenes.local import (MarketScene, EventScene,
                                              MarketSource, EventSource)
from transithub.local import LocalData
from transithub.local.markets import Market
from transithub.local.events import Event
from transithub.profile import Profile


def _market():
    return Market(name="MARIA HERNANDEZ", close_label="UNTIL 3", dist_km=0.55)


def _event(**kw):
    base = dict(label="BACK TO THE BLOCK", kind="CONCERT", when_label="5 PM",
                venue="MARIA HERNANDEZ", dist_km=0.55, start=datetime(2026, 5, 25, 17, 0))
    base.update(kw)
    return Event(**base)


def _ctx(local=None, profile=Profile.DAY):
    return Context(now=datetime(2026, 5, 25, 12, 0), mono_ms=0, profile=profile, local=local)


# --- MarketScene -----------------------------------------------------------
def test_market_scene_size_mode_duration():
    s = MarketScene(_market())
    assert s.duration_ms == 8000
    img = s.render(0)
    assert img.size == (64, 32) and img.mode == "RGB"
    assert s.render(4000).size == (64, 32)


def test_market_scene_lines_fit():
    for line in MarketScene(_market()).lines():
        assert S.text_width(line) <= 64, f"{line!r} overflows"


def test_market_scene_long_name_truncated_to_fit():
    s = MarketScene(Market(name="GRAND ARMY PLAZA SUNSET", close_label="UNTIL 6", dist_km=1.0))
    for line in s.lines():
        assert S.text_width(line) <= 64


def test_market_scene_draws_something():
    img = MarketScene(_market()).render(1000)
    assert any(img.getpixel((x, y)) != (0, 0, 0) for x in range(64) for y in range(32))


# --- EventScene ------------------------------------------------------------
def test_event_scene_size_mode_duration():
    s = EventScene(_event())
    assert s.duration_ms == 8000
    img = s.render(0)
    assert img.size == (64, 32) and img.mode == "RGB"


def test_event_scene_lines_fit():
    for line in EventScene(_event()).lines():
        assert S.text_width(line) <= 64, f"{line!r} overflows"


def test_event_scene_long_venue_truncated_to_fit():
    s = EventScene(_event(kind="PARK MOVIE", venue="HERBERT VON KING CULTURAL", when_label="8 PM"))
    for line in s.lines():
        assert S.text_width(line) <= 64


def test_event_scene_shows_type_time_place():
    lines = EventScene(_event()).lines()
    joined = " ".join(lines)
    assert "CONCERT" in joined and "5 PM" in joined and "HERNANDEZ" in joined


# --- MarketSource ----------------------------------------------------------
def test_market_source_none_without_data():
    assert MarketSource().poll(_ctx(local=None)) is None
    assert MarketSource().poll(_ctx(local=LocalData(market=None))) is None


def test_market_source_returns_scene():
    scene = MarketSource().poll(_ctx(local=LocalData(market=_market())))
    assert isinstance(scene, MarketScene)


# --- EventSource (cycles across plays) -------------------------------------
def test_event_source_none_without_data():
    assert EventSource().poll(_ctx(local=None)) is None
    assert EventSource().poll(_ctx(local=LocalData(events=[]))) is None


def test_event_source_cycles_through_events():
    e1 = _event(label="A", venue="ALPHA")
    e2 = _event(label="B", venue="BETA")
    src = EventSource()
    local = LocalData(events=[e1, e2])
    first = src.poll(_ctx(local=local))
    second = src.poll(_ctx(local=local))
    third = src.poll(_ctx(local=local))
    assert first.event.label == "A"
    assert second.event.label == "B"
    assert third.event.label == "A"      # wraps around
