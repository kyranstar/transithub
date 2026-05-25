"""Render + rotation tests for the birthday scene and its source.

No network: the scene is built from a name + style, the source from parsed config
specs plus a Context whose ``now`` we set directly. Every text line must fit the
64px panel, and the source must rotate through the three styles."""
from __future__ import annotations

from datetime import datetime

from transithub.birthdays import parse_specs
from transithub.display import scenery as S
from transithub.display.director import Context
from transithub.display.scenes.birthday import (BirthdayScene, BirthdaySource,
                                                 _STYLES)
from transithub.profile import Profile

YEN = {"name": "Yennifer", "date": "09-17"}
BDAY = datetime(2026, 9, 17, 0, 0)        # midnight on the birthday
NOT_BDAY = datetime(2026, 9, 18, 12, 0)


def _ctx(now=BDAY, profile=Profile.DAY):
    return Context(now=now, mono_ms=0, profile=profile)


# --- BirthdayScene ---------------------------------------------------------
def test_scene_duration_and_styles():
    assert BirthdayScene("Yennifer").duration_ms == 9000
    assert _STYLES == ("confetti", "cake", "fireworks")


def test_scene_renders_each_style():
    for style in _STYLES:
        s = BirthdayScene("Yennifer", style)
        for t in (0, 300, 4000):
            img = s.render(t)
            assert img.size == (64, 32) and img.mode == "RGB"


def test_scene_draws_something():
    for style in _STYLES:
        img = BirthdayScene("Yennifer", style).render(2000)
        assert any(img.getpixel((x, y)) != (0, 0, 0)
                   for x in range(64) for y in range(32)), f"{style} drew nothing"


def test_scene_lines_fit_panel():
    for line in BirthdayScene("Yennifer").lines():
        assert S.text_width(line) <= 64, f"{line!r} overflows"


def test_scene_long_name_truncated():
    for line in BirthdayScene("BARTHOLOMEW MAXIMILIANO").lines():
        assert S.text_width(line) <= 64


def test_scene_shows_header_and_name():
    lines = BirthdayScene("Yennifer").lines()
    assert lines[0] == "HAPPY" and lines[1] == "BIRTHDAY"
    assert "YENNIFER" in lines[2]


def test_scene_unknown_style_falls_back_to_confetti():
    assert BirthdayScene("Yennifer", "sparkles").style == "confetti"


# --- BirthdaySource --------------------------------------------------------
def test_source_returns_scene_on_birthday():
    src = BirthdaySource(parse_specs([YEN]))
    scene = src.poll(_ctx(now=BDAY))
    assert isinstance(scene, BirthdayScene) and scene.name == "Yennifer"


def test_source_none_when_not_birthday():
    assert BirthdaySource(parse_specs([YEN])).poll(_ctx(now=NOT_BDAY)) is None


def test_source_empty_specs_is_none():
    assert BirthdaySource([]).poll(_ctx()) is None


def test_source_rotates_style_per_appearance():
    src = BirthdaySource(parse_specs([YEN]))
    styles = [src.poll(_ctx(now=BDAY)).style for _ in range(4)]
    assert styles == ["confetti", "cake", "fireworks", "confetti"]
