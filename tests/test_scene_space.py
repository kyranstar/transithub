from datetime import datetime

from PIL import Image

from transithub.display import scenery as S
from transithub.display.director import Context
from transithub.display.scenes.space import (EarthFromSpaceScene,
                                               EarthFromSpaceSource,
                                               HumansInSpaceScene,
                                               HumansInSpaceSource)
from transithub.profile import Profile
from transithub.space import EarthFrame, HumansInSpace, SpaceData


def _humans():
    return HumansInSpace(total=12, by_craft={"ISS": 9, "Tiangong": 3})


def _earth():
    disc = Image.new("RGB", (64, 32), (0, 0, 0))
    # a lit center block stands in for the Earth disc
    for x in range(20, 44):
        for y in range(6, 26):
            disc.putpixel((x, y), (40, 90, 150))
    return EarthFrame(base_image=disc, caption="EARTH 8:22P",
                      captured=datetime(2026, 5, 22, 20, 22))


def _ctx(space=None):
    return Context(now=datetime(2026, 5, 25, 22, 0), mono_ms=0,
                   profile=Profile.NIGHT, space=space)


# -- HumansInSpaceScene -----------------------------------------------------
def test_humans_scene_size_mode_duration():
    s = HumansInSpaceScene(_humans())
    assert s.duration_ms == 8000
    img = s.render(0)
    assert img.size == (64, 32) and img.mode == "RGB"
    assert s.render(7900).size == (64, 32)


def test_humans_count_beat_lights_pixels():
    s = HumansInSpaceScene(_humans())
    img = s.render(1500)                      # mid beat 1 (past the fade-in)
    assert any(img.getpixel((x, y)) != (0, 0, 0)
               for x in range(64) for y in range(32))


def test_humans_rotates_to_a_distinct_second_beat():
    s = HumansInSpaceScene(_humans())
    beat1 = s.render(2000).tobytes()          # count beat (beat 1)
    beat2 = s.render(6000).tobytes()          # craft beat (beat 2)
    assert beat1 != beat2


def test_humans_single_craft_has_one_beat():
    s = HumansInSpaceScene(HumansInSpace(total=3, by_craft={}))
    assert len(s._beats) == 1                 # no craft data -> count only


def test_craft_lines_fit_panel():
    s = HumansInSpaceScene(_humans())
    for craft in s.h.crafts:
        assert S.text_width(s._craft_line(craft)) <= 64


def test_long_craft_name_still_fits():
    s = HumansInSpaceScene(HumansInSpace(total=4, by_craft={"INTERNATIONALSTATION": 4}))
    line = s._craft_line("INTERNATIONALSTATION")
    assert S.text_width(line) <= 64
    assert line.endswith(" 4")                # the count is never dropped


# -- EarthFromSpaceScene ----------------------------------------------------
def test_earth_scene_size_mode_duration():
    s = EarthFromSpaceScene(_earth())
    assert s.duration_ms == 9000
    img = s.render(2000)
    assert img.size == (64, 32) and img.mode == "RGB"


def test_earth_disc_composited_over_starfield():
    s = EarthFromSpaceScene(_earth())
    img = s.render(2000)                       # past the fade-in
    # center is the lit disc, not pure space
    assert img.getpixel((32, 16)) != (0, 0, 0)


def test_earth_caption_fits():
    assert S.text_width(_earth().caption) <= 64


# -- Sources ----------------------------------------------------------------
def test_humans_source_none_when_space_absent():
    assert HumansInSpaceSource().poll(_ctx(None)) is None
    assert HumansInSpaceSource().poll(_ctx(SpaceData(humans=None))) is None


def test_humans_source_returns_scene_when_present():
    scene = HumansInSpaceSource().poll(_ctx(SpaceData(humans=_humans())))
    assert isinstance(scene, HumansInSpaceScene)


def test_earth_source_none_when_space_absent():
    assert EarthFromSpaceSource().poll(_ctx(None)) is None
    assert EarthFromSpaceSource().poll(_ctx(SpaceData(earth=None))) is None


def test_earth_source_returns_scene_when_present():
    scene = EarthFromSpaceSource().poll(_ctx(SpaceData(earth=_earth())))
    assert isinstance(scene, EarthFromSpaceScene)
