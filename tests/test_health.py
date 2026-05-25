from datetime import datetime, timedelta

from transithub.health import HealthMonitor


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def test_silent_with_no_feeds():
    assert HealthMonitor(now_fn=Clock(datetime(2026, 5, 25, 12, 0))).warnings() == []


def test_silent_when_all_fresh():
    h = HealthMonitor(now_fn=Clock(datetime(2026, 5, 25, 12, 0)))
    h.ok("weather")
    h.ok("arrivals")
    assert h.warnings() == []


def test_offline_when_everything_fails():
    base = datetime(2026, 5, 25, 12, 0)
    clock = Clock(base)
    h = HealthMonitor(now_fn=clock, offline_after_s=120)
    h.ok("weather")
    h.ok("arrivals")
    clock.t = base + timedelta(seconds=200)
    h.fail("weather")
    h.fail("arrivals")
    assert h.warnings() == ["OFFLINE"]


def test_weather_stale_alone():
    base = datetime(2026, 5, 25, 12, 0)
    clock = Clock(base)
    h = HealthMonitor(now_fn=clock, weather_stale_s=1800, arrivals_stale_s=300)
    h.ok("weather")
    h.ok("arrivals")
    clock.t = base + timedelta(seconds=2000)
    h.ok("arrivals")                      # arrivals fresh, weather now 2000s old
    assert h.warnings() == ["WEATHER STALE"]


def test_trains_stale_alone():
    base = datetime(2026, 5, 25, 12, 0)
    clock = Clock(base)
    h = HealthMonitor(now_fn=clock, weather_stale_s=1800, arrivals_stale_s=300)
    h.ok("weather")
    h.ok("arrivals")
    clock.t = base + timedelta(seconds=400)
    h.ok("weather")                       # weather fresh, arrivals now 400s old
    assert h.warnings() == ["TRAINS STALE"]


def test_recovers_to_silent():
    base = datetime(2026, 5, 25, 12, 0)
    clock = Clock(base)
    h = HealthMonitor(now_fn=clock)
    h.fail("weather")
    h.fail("arrivals")
    assert h.warnings() == ["OFFLINE"]
    clock.t = base + timedelta(seconds=10)
    h.ok("weather")
    h.ok("arrivals")
    assert h.warnings() == []
