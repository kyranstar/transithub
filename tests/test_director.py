from datetime import datetime

from transithub.display.director import Director


class FakeScene:
    def __init__(self, name, duration_ms=None):
        self.name = name
        self.duration_ms = duration_ms
        self.last = None

    def render(self, elapsed_ms):
        self.last = elapsed_ms
        return self.name


SR = datetime(2026, 5, 23, 6, 0)
SS = datetime(2026, 5, 23, 20, 0)


class W:  # minimal weather stand-in
    sunrise, sunset = SR, SS


def _director(weather=lambda: W()):
    trains = FakeScene("trains")
    d = Director(
        train_scene=trains,
        weather_provider=weather,
        make_weather_scene=lambda w, now: FakeScene("weather", 60_000),
        make_sun_scene=lambda kind, t: FakeScene(f"sun:{kind}", 10_000),
        rundown_every_minutes=15, sunrise_enabled=True, sunset_enabled=True,
    )
    return d, trains


def test_trains_by_default():
    d, _ = _director()
    assert d.render(datetime(2026, 5, 23, 12, 0), 1000) == "trains"


def test_rundown_fires_on_cadence_then_returns():
    d, _ = _director()
    d.render(datetime(2026, 5, 23, 12, 0), 0)
    assert d.render(datetime(2026, 5, 23, 12, 16), 16 * 60_000) == "weather"
    assert d.render(datetime(2026, 5, 23, 12, 16, 30), 16 * 60_000 + 30_000) == "weather"
    assert d.render(datetime(2026, 5, 23, 12, 17, 5), 16 * 60_000 + 61_000) == "trains"


def test_sun_notification_fires_once_per_day():
    d, _ = _director()
    assert d.render(datetime(2026, 5, 23, 5, 35), 1000) == "sun:sunrise"
    assert d.render(datetime(2026, 5, 23, 5, 45), 12_000) == "trains"
    assert d.render(datetime(2026, 5, 23, 5, 50), 13_000) == "trains"
