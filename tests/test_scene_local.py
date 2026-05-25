"""Render + fit tests for the market scene and its source.

No network: the scene is built from a plain ``Market`` dataclass, the source from
parsed config specs plus a Context whose ``now`` we set directly. Every text line
must fit the 64px panel."""
from __future__ import annotations

from datetime import datetime

from transithub.display import scenery as S
from transithub.display.director import Context
from transithub.display.scenes.local import MarketScene, MarketSource
from transithub.local.markets import Market, parse_specs
from transithub.profile import Profile

# Maria Hernandez: every Saturday, in season 2026-05-23 .. 2026-11-22, until 3.
MARIA = {"name": "MARIA HERNANDEZ", "day": "saturday",
         "season": ["2026-05-23", "2026-11-22"], "until": "3"}

SATURDAY = datetime(2026, 5, 30, 12, 0)     # in-season Saturday -> open
FRIDAY = datetime(2026, 5, 29, 12, 0)       # in-season Friday -> closed


def _market():
    return Market(name="MARIA HERNANDEZ", until="3")


def _ctx(now=SATURDAY, profile=Profile.DAY):
    return Context(now=now, mono_ms=0, profile=profile)


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


def test_market_scene_shows_until_label():
    lines = MarketScene(_market()).lines()
    assert "MARKET TODAY" in lines
    assert any("UNTIL 3" in line for line in lines)


def test_market_scene_long_name_truncated_to_fit():
    s = MarketScene(Market(name="GRAND ARMY PLAZA SUNSET GREENMARKET", until="6"))
    for line in s.lines():
        assert S.text_width(line) <= 64


def test_market_scene_draws_something():
    img = MarketScene(_market()).render(1000)
    assert any(img.getpixel((x, y)) != (0, 0, 0) for x in range(64) for y in range(32))


# --- MarketSource ----------------------------------------------------------
def test_market_source_empty_specs_is_none():
    assert MarketSource([]).poll(_ctx()) is None


def test_market_source_returns_scene_when_open_today():
    src = MarketSource(parse_specs([MARIA]))
    scene = src.poll(_ctx(now=SATURDAY))
    assert isinstance(scene, MarketScene)
    assert scene.market.name == "MARIA HERNANDEZ" and scene.market.until == "3"


def test_market_source_none_on_wrong_day():
    src = MarketSource(parse_specs([MARIA]))
    assert src.poll(_ctx(now=FRIDAY)) is None


def test_market_source_none_out_of_season():
    src = MarketSource(parse_specs([MARIA]))
    # A Saturday before the season opens -> nothing on screen.
    assert src.poll(_ctx(now=datetime(2026, 5, 16, 12, 0))) is None
