"""End-to-end: drive the fully wired Director with synthetic snapshots for a
simulated hour and confirm the schedule behaves — scenes rotate, the trains stay
the backbone, and nothing crashes when rendered through the dimmer."""
from collections import Counter
from datetime import datetime, timedelta

from transithub.__main__ import _build_director
from transithub.config import Config
from transithub.display.sign import SignRenderer
from transithub.health import HealthMonitor
from transithub.local import LocalData, LocalHolder
from transithub.local.events import Event
from transithub.local.markets import Market
from transithub.models import TrackedTrain
from transithub.space import SpaceData
from transithub.space.humans import HumansInSpace
from transithub.sky import SkyData
from transithub.store import ArrivalStore, Holder, WeatherHolder
from transithub.weather.model import Condition, Weather

BASE = datetime(2026, 5, 25, 12, 0)


def _weather():
    return Weather(temp=70, feels_like=70, condition=Condition.CLEAR, today_high=75,
                   today_low=60, precip_prob=0, uv_index=3.0, aqi=30,
                   sunrise=BASE.replace(hour=6, minute=0),
                   sunset=BASE.replace(hour=20, minute=0), humidity=40, wind_mph=5.0)


def _holders(weather=None, humans=None, market=None, events=()):
    wh = WeatherHolder()
    wh.set(weather)
    local = LocalHolder()
    local._data = LocalData(market=market, events=list(events))
    return {
        "weather": wh,
        "sky": Holder(SkyData()),
        "space": Holder(SpaceData(humans=humans)),
        "local": local,
    }


def _director(holders):
    cfg = Config(trains=[TrackedTrain(line="L", stop_id="L16", direction="N")])
    renderer = SignRenderer(cfg)
    store = ArrivalStore(1)
    return _build_director(cfg, renderer, store, holders, HealthMonitor())


def _run(director, minutes=60, step_ms=5000):
    """Render every `step_ms` for `minutes`; return a Counter of active scene types."""
    seen = Counter()
    for mono in range(0, minutes * 60_000, step_ms):
        now = BASE + timedelta(milliseconds=mono)
        img = director.render(now, mono)
        assert img.size == (64, 32) and img.mode == "RGB"   # never crashes
        seen[type(director._active).__name__] += 1
    return seen


def test_trains_are_the_backbone_but_scenes_rotate():
    holders = _holders(
        weather=_weather(),
        humans=HumansInSpace(total=12, by_craft={"ISS": 9, "Tiangong": 3}),
        market=Market("UNION SQ", "UNTIL 6", 2.0),
        events=[Event("Movie Night", "PARK MOVIE", "8 PM", "TOMPKINS", 1.0,
                      BASE.replace(hour=20))],
    )
    seen = _run(_director(holders))

    assert seen["TrainScene"] == max(seen.values())     # trains dominate the hour
    assert seen["WeatherScene"] > 0                      # the 6-minute rundown fires
    assert seen["HumansInSpaceScene"] > 0                # the rare fact appears
    assert seen["MarketScene"] + seen["EventScene"] > 0  # neighborhood content shows


def test_calm_day_is_almost_all_trains():
    # No ambient data at all -> essentially trains plus the weather rundown.
    seen = _run(_director(_holders(weather=_weather())))
    assert set(seen) <= {"TrainScene", "WeatherScene"}
    assert seen["TrainScene"] > seen["WeatherScene"]


def test_night_dims_the_frame():
    holders = _holders(weather=_weather())
    director = _director(holders)
    # 2am: deep night -> the dimmer should pull brightness to the floor.
    night = datetime(2026, 5, 25, 2, 0)
    img = director.render(night, 1000)
    assert max(img.getpixel((x, y))[i] for x in range(64) for y in range(32)
               for i in range(3)) < 120     # nothing near full brightness at night
