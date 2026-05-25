from datetime import datetime

from transithub.display.director import Context
from transithub.display.sources import (HealthSource, SunEventSource,
                                         WeatherRundownSource)
from transithub.profile import Profile


class W:
    sunrise = datetime(2026, 5, 25, 6, 0)
    sunset = datetime(2026, 5, 25, 20, 0)


def _ctx(now, weather=None, health=(), profile=Profile.DAY):
    return Context(now=now, mono_ms=0, profile=profile, weather=weather, health=health)


def test_weather_source_none_without_data():
    s = WeatherRundownSource(make_scene=lambda w, now, lean: "WX")
    assert s.poll(_ctx(datetime(2026, 5, 25, 12, 0))) is None
    assert s.poll(_ctx(datetime(2026, 5, 25, 12, 0), weather=W())) == "WX"


def test_weather_source_lean_at_night():
    seen = {}

    def make(w, now, lean):
        seen["lean"] = lean
        return "WX"

    s = WeatherRundownSource(make_scene=make)
    s.poll(_ctx(datetime(2026, 5, 25, 23, 0), weather=W(), profile=Profile.NIGHT))
    assert seen["lean"] is True
    s.poll(_ctx(datetime(2026, 5, 25, 12, 0), weather=W(), profile=Profile.DAY))
    assert seen["lean"] is False


def test_sun_source_fires_once_then_suppresses():
    s = SunEventSource(make_scene=lambda kind, t: f"sun:{kind}")
    assert s.poll(_ctx(datetime(2026, 5, 25, 5, 35), W())) == "sun:sunrise"
    assert s.poll(_ctx(datetime(2026, 5, 25, 5, 40), W())) is None


def test_sun_source_sunset_window():
    s = SunEventSource(make_scene=lambda kind, t: f"sun:{kind}")
    assert s.poll(_ctx(datetime(2026, 5, 25, 19, 30), W())) == "sun:sunset"


def test_sun_source_respects_disable():
    s = SunEventSource(make_scene=lambda kind, t: f"sun:{kind}", sunrise_enabled=False)
    assert s.poll(_ctx(datetime(2026, 5, 25, 5, 35), W())) is None


def test_health_source():
    s = HealthSource()
    assert s.poll(_ctx(datetime(2026, 5, 25, 12, 0))) is None
    scene = s.poll(_ctx(datetime(2026, 5, 25, 12, 0), health=("OFFLINE",)))
    assert scene is not None and scene.message == "OFFLINE"
