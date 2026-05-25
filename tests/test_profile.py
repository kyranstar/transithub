from datetime import datetime, time

from transithub.profile import Profile, day_profile


class W:
    def __init__(self, sunrise, sunset):
        self.sunrise = sunrise
        self.sunset = sunset


SR = datetime(2026, 5, 25, 5, 30)
SS = datetime(2026, 5, 25, 20, 0)


def test_day_between_sun():
    assert day_profile(datetime(2026, 5, 25, 12, 0), W(SR, SS)) is Profile.DAY


def test_evening_after_sunset_until_bedtime():
    assert day_profile(datetime(2026, 5, 25, 20, 30), W(SR, SS)) is Profile.EVENING


def test_night_after_bedtime():
    assert day_profile(datetime(2026, 5, 25, 22, 0), W(SR, SS)) is Profile.NIGHT


def test_night_before_sunrise():
    assert day_profile(datetime(2026, 5, 25, 3, 0), W(SR, SS)) is Profile.NIGHT


def test_fallback_without_weather():
    assert day_profile(datetime(2026, 5, 25, 12, 0)) is Profile.DAY
    assert day_profile(datetime(2026, 5, 25, 20, 0)) is Profile.EVENING
    assert day_profile(datetime(2026, 5, 25, 23, 30)) is Profile.NIGHT


def test_custom_bedtime_moves_night_earlier():
    assert day_profile(datetime(2026, 5, 25, 21, 0), W(SR, SS),
                       bedtime=time(20, 30)) is Profile.NIGHT
