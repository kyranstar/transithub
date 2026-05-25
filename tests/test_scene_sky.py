"""Offline tests for the sky scenes and their sources.

Covers: moon-day detection (the calendar day of full/new in 2026, and that a
mid-cycle day stays quiet); every scene renders the right size/mode/duration and
its text fits 64 px; and every source returns None when its data is absent."""
from datetime import datetime, timedelta

from transithub.display import scenery as S
from transithub.display.director import Context
from transithub.display.scenes.sky import (FullMoonScene, IssPassScene,
                                            IssPassSource, MoonEventSource,
                                            NewMoonScene, PlaneOverheadScene,
                                            PlaneOverheadSource)
from transithub.profile import Profile
from transithub.sky import IssPass, Plane, SkyData


def _label_pixels(text, y, scale=1, cols=64):
    """The (x, y) cells a centered label would light, matching ``_centered``."""
    x0 = (cols - S.text_width(text, scale)) // 2
    return set(S.FONT.iter_pixels(x0, y, text))


def _shows_label(img, text, y, scale=1):
    """True if the rendered frame has a lit (non-black) pixel at most of the
    cells the centered ``text`` would occupy — i.e. that label is on screen."""
    cells = _label_pixels(text, y, scale, img.size[0])
    lit = sum(1 for (x, yy) in cells
              if 0 <= x < img.size[0] and 0 <= yy < img.size[1]
              and img.getpixel((x, yy)) != (0, 0, 0))
    return cells and lit >= 0.8 * len(cells)


# -- a fake weather snapshot whose sunset tracks the day being queried --------
class W:
    """Stand-in weather exposing just the sun times the moon source reads.

    Sunset defaults to a given date; ``for_day`` builds one matching a date so a
    test can say "after sunset on this night"."""
    def __init__(self, sunset=datetime(2026, 5, 31, 20, 19)):
        self.sunset = sunset

    @classmethod
    def for_day(cls, d: datetime, hour=20, minute=19):
        return cls(sunset=d.replace(hour=hour, minute=minute, second=0, microsecond=0))


def _ctx(now, weather=None, sky=None, profile=Profile.NIGHT):
    return Context(now=now, mono_ms=0, profile=profile, weather=weather, sky=sky)


# ====================================================================== MOON
FULL_NIGHT = datetime(2026, 5, 31, 21, 30)        # 2026 full moon, after sunset
NEW_NIGHT = datetime(2026, 5, 16, 21, 30)         # 2026 new moon, after sunset


def test_moon_source_fires_on_full_moon_night():
    src = MoonEventSource(cols=64, rows=32)
    scene = src.poll(_ctx(FULL_NIGHT, weather=W.for_day(FULL_NIGHT)))
    assert isinstance(scene, FullMoonScene)


def test_moon_source_fires_on_new_moon_night():
    src = MoonEventSource(cols=64, rows=32)
    scene = src.poll(_ctx(NEW_NIGHT, weather=W.for_day(NEW_NIGHT)))
    assert isinstance(scene, NewMoonScene)


def test_moon_source_quiet_on_midcycle_day():
    src = MoonEventSource(cols=64, rows=32)
    # ~first quarter, far from both full and new -> nothing.
    mid = datetime(2026, 5, 24, 22, 0)
    assert src.poll(_ctx(mid, weather=W.for_day(mid))) is None


def test_moon_source_quiet_before_sunset():
    src = MoonEventSource(cols=64, rows=32)
    # Right day (full moon) but the sun is still up -> wait.
    assert src.poll(_ctx(datetime(2026, 5, 31, 14, 0), weather=W.for_day(FULL_NIGHT))) is None


def test_moon_source_fires_only_once_per_night():
    src = MoonEventSource(cols=64, rows=32)
    first = src.poll(_ctx(FULL_NIGHT, weather=W.for_day(FULL_NIGHT)))
    second = src.poll(_ctx(datetime(2026, 5, 31, 22, 0), weather=W.for_day(FULL_NIGHT)))
    assert first is not None and second is None


def test_moon_source_falls_back_to_default_sunset_without_weather():
    src = MoonEventSource(cols=64, rows=32)
    # No weather: after the ~20:00 fallback on the full-moon day it still fires.
    assert isinstance(src.poll(_ctx(datetime(2026, 5, 31, 21, 0))), FullMoonScene)
    # ...but not in the afternoon.
    src2 = MoonEventSource(cols=64, rows=32)
    assert src2.poll(_ctx(datetime(2026, 5, 31, 13, 0))) is None


# ============================================================ MOON SCENES
def test_full_moon_scene_shape_and_text():
    s = FullMoonScene(cols=64, rows=32)
    assert s.duration_ms and s.duration_ms > 0
    img = s.render(s.duration_ms // 2)
    assert img.size == (64, 32) and img.mode == "RGB"
    assert S.text_width("FULL MOON") <= 64
    # something bright (the moon) is drawn
    assert any(sum(img.getpixel((x, y))) > 400 for x in range(64) for y in range(32))


def test_new_moon_scene_shape_and_text():
    s = NewMoonScene(cols=64, rows=32)
    assert s.duration_ms and s.duration_ms > 0
    img = s.render(100)
    assert img.size == (64, 32) and img.mode == "RGB"
    assert S.text_width("NEW MOON") <= 64


# ============================================================== ISS SCENE
def _pass(start, **kw):
    base = dict(start=start, peak=start + timedelta(minutes=3),
                end=start + timedelta(minutes=6), max_el_deg=55.0,
                rise_dir="NW", visible=True)
    base.update(kw)
    return IssPass(**base)


def test_iss_scene_heads_up_shape_and_text():
    when = datetime(2026, 5, 31, 20, 43)
    s = IssPassScene(_pass(when), now=when, mode="heads_up")
    assert s.duration_ms and s.duration_ms > 0
    img = s.render(500)
    assert img.size == (64, 32) and img.mode == "RGB"
    # the three heads-up lines all fit 64 px
    assert S.text_width("ISS PASS") <= 64
    assert S.text_width("LOOK NW") <= 64
    assert S.text_width("8:43 PM") <= 64


def test_iss_scene_heads_up_says_it_is_the_iss():
    # The heads-up must label the event as the ISS, plus the time and direction.
    when = datetime(2026, 5, 31, 20, 43)
    img = IssPassScene(_pass(when), now=when, mode="heads_up").render(500)
    assert _shows_label(img, "ISS PASS", 8)
    assert _shows_label(img, "8:43 PM", 16)
    assert _shows_label(img, "LOOK NW", 32 - 8)


def test_iss_scene_overhead_says_iss_above_you():
    when = datetime(2026, 5, 31, 20, 43)
    s = IssPassScene(_pass(when), now=when, mode="overhead")
    img = s.render(500)
    assert img.size == (64, 32) and img.mode == "RGB"
    assert _shows_label(img, "ISS", 32 - 17)
    assert _shows_label(img, "ABOVE YOU", 32 - 8)


# ============================================================ PLANE SCENE
def test_plane_scene_shape_and_text():
    p = Plane(callsign="UAL415", alt_ft=8175, heading_deg=218.0, dir="SW")
    s = PlaneOverheadScene(p)
    assert s.duration_ms and s.duration_ms > 0
    img = s.render(500)
    assert img.size == (64, 32) and img.mode == "RGB"
    # the busiest line must fit
    assert S.text_width("SW 32000FT") <= 64


def test_plane_scene_reads_as_overhead_with_route():
    # With a route it shows ABOVE YOU + the route (not the bare callsign).
    p = Plane(callsign="BAW178", alt_ft=35000, heading_deg=61.0, dir="NE",
              route="JFK > LHR")
    img = PlaneOverheadScene(p).render(500)
    assert _shows_label(img, "ABOVE YOU", 10)
    assert _shows_label(img, "JFK > LHR", 17)
    assert _shows_label(img, "NE 35000FT", 24)
    for line in ("ABOVE YOU", "JFK > LHR", "NE 35000FT"):
        assert S.text_width(line) <= 64


def test_plane_scene_falls_back_to_callsign_without_route():
    p = Plane(callsign="UAL415", alt_ft=8175, heading_deg=218.0, dir="SW",
              route=None)
    img = PlaneOverheadScene(p).render(500)
    assert _shows_label(img, "ABOVE YOU", 10)
    assert _shows_label(img, "UAL415", 17)
    assert S.text_width("UAL415") <= 64


# ================================================================ SOURCES
def test_iss_source_none_without_sky():
    assert IssPassSource().poll(_ctx(datetime(2026, 5, 31, 20, 43))) is None


def test_iss_source_heads_up_within_window():
    when = datetime(2026, 5, 31, 20, 40)
    sky = SkyData(next_iss_pass=_pass(when + timedelta(minutes=3)))  # starts in 3 min
    scene = IssPassSource().poll(_ctx(when, sky=sky))
    assert isinstance(scene, IssPassScene) and scene.mode == "heads_up"


def test_iss_source_overhead_during_pass():
    start = datetime(2026, 5, 31, 20, 40)
    when = start + timedelta(minutes=2)        # mid-pass
    sky = SkyData(next_iss_pass=_pass(start))
    scene = IssPassSource().poll(_ctx(when, sky=sky))
    assert isinstance(scene, IssPassScene) and scene.mode == "overhead"


def test_iss_source_quiet_when_pass_far_off():
    when = datetime(2026, 5, 31, 20, 0)
    sky = SkyData(next_iss_pass=_pass(when + timedelta(hours=2)))
    assert IssPassSource().poll(_ctx(when, sky=sky)) is None


def test_plane_source_none_without_sky():
    assert PlaneOverheadSource().poll(_ctx(datetime(2026, 5, 31, 12, 0))) is None


def test_plane_source_fires_when_plane_present():
    p = Plane(callsign="UAL415", alt_ft=8175, heading_deg=218.0, dir="SW")
    sky = SkyData(plane_overhead=p)
    scene = PlaneOverheadSource().poll(_ctx(datetime(2026, 5, 31, 12, 0), sky=sky))
    assert isinstance(scene, PlaneOverheadScene)


def test_plane_source_quiet_when_no_plane():
    sky = SkyData(plane_overhead=None)
    assert PlaneOverheadSource().poll(_ctx(datetime(2026, 5, 31, 12, 0), sky=sky)) is None


def test_plane_source_does_not_flag_same_plane_twice():
    now = datetime(2026, 5, 31, 12, 0)
    src = PlaneOverheadSource()
    ual = SkyData(plane_overhead=Plane("UAL415", 8175, 218.0, "SW"))
    dal = SkyData(plane_overhead=Plane("DAL336", 6000, 90.0, "E"))

    assert src.poll(_ctx(now, sky=ual)) is not None      # first sighting -> shown
    assert src.poll(_ctx(now, sky=ual)) is None          # same plane lingering -> skipped
    assert src.poll(_ctx(now, sky=ual)) is None          # still the same -> still skipped
    assert src.poll(_ctx(now, sky=dal)) is not None      # a different aircraft -> shown
    assert src.poll(_ctx(now, sky=SkyData())) is None    # gap (no plane)
    # UAL415 returning later (a genuinely new pass) is allowed again, not stuck.
    assert src.poll(_ctx(now, sky=ual)) is not None
