from datetime import datetime

from PIL import Image

from transithub.display.dimmer import Dimmer
from transithub.display.director import Context
from transithub.profile import Profile


class W:
    sunrise = datetime(2026, 5, 25, 5, 30)
    sunset = datetime(2026, 5, 25, 20, 0)


def test_full_brightness_by_day():
    assert Dimmer().level(datetime(2026, 5, 25, 12, 0), W()) == 1.0


def test_night_holds_floor():
    assert Dimmer(night_floor=0.16).level(datetime(2026, 5, 25, 23, 0), W()) == 0.16


def test_evening_ramps_down_from_sunset():
    d = Dimmer(evening_floor=0.5)
    at_sunset = d.level(datetime(2026, 5, 25, 20, 0), W())
    halfway = d.level(datetime(2026, 5, 25, 20, 45), W())   # ~halfway to 21:30 bedtime
    assert abs(at_sunset - 1.0) < 1e-6
    assert abs(halfway - 0.75) < 1e-6


def test_apply_scales_pixels_at_night():
    img = Image.new("RGB", (2, 2), (200, 200, 200))
    ctx = Context(now=datetime(2026, 5, 25, 23, 0), mono_ms=0,
                  profile=Profile.NIGHT, weather=W())
    assert Dimmer(night_floor=0.5).apply(img, ctx).getpixel((0, 0)) == (100, 100, 100)


def test_apply_is_noop_by_day():
    img = Image.new("RGB", (2, 2), (200, 200, 200))
    ctx = Context(now=datetime(2026, 5, 25, 12, 0), mono_ms=0,
                  profile=Profile.DAY, weather=W())
    assert Dimmer().apply(img, ctx).getpixel((0, 0)) == (200, 200, 200)


def test_dawn_ramps_up_smoothly():
    d = Dimmer(night_floor=0.16)               # sunrise 5:30 -> ramp over [5:00, 5:30]
    assert d.level(datetime(2026, 5, 25, 4, 55), W()) == 0.16        # before the ramp
    assert 0.16 < d.level(datetime(2026, 5, 25, 5, 15), W()) < 1.0   # partway up
    assert abs(d.level(datetime(2026, 5, 25, 5, 30), W()) - 1.0) < 1e-6  # full by sunrise


def test_bedtime_winds_down_smoothly_no_cliff():
    d = Dimmer(evening_floor=0.5, night_floor=0.16)   # bedtime 21:30, wind-down to 22:15
    before = d.level(datetime(2026, 5, 25, 21, 29), W())
    after = d.level(datetime(2026, 5, 25, 21, 31), W())
    assert abs(before - after) < 0.05            # continuous across bedtime, no 0.5->0.16 jump
    assert 0.16 < d.level(datetime(2026, 5, 25, 21, 52), W()) < 0.5   # mid wind-down
    assert d.level(datetime(2026, 5, 25, 22, 30), W()) == 0.16        # floor reached after
