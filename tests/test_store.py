from datetime import datetime, timedelta

from transithub.models import Arrival
from transithub.store import ArrivalStore

NOW = datetime(2026, 5, 23, 12, 0, 0)


def test_store_roundtrip_preserves_order():
    store = ArrivalStore(n_trains=2)
    store.set(0, [Arrival("L", "8 Av", NOW + timedelta(minutes=2))])
    store.set(1, [Arrival("M", "Manh", NOW + timedelta(minutes=8))])
    snap = store.snapshot()
    assert len(snap) == 2
    assert snap[0][0].line == "L" and snap[1][0].line == "M"


def test_store_defaults_to_empty_lists():
    store = ArrivalStore(n_trains=3)
    assert store.snapshot() == [[], [], []]


def test_store_alerts_roundtrip():
    store = ArrivalStore(n_trains=2)
    assert store.alerts() == [None, None]
    store.set_alerts([None, "SUSP"])
    assert store.alerts() == [None, "SUSP"]


def test_weather_holder_roundtrip():
    from transithub.store import WeatherHolder
    h = WeatherHolder()
    assert h.get() is None
    h.set("w")
    assert h.get() == "w"
