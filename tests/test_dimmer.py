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
