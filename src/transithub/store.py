import threading
from typing import List, Optional

from .models import Arrival
from .mta.alerts import LineAlert


class ArrivalStore:
    """Thread-safe shared state: arrivals and an alert tag per tracked stop.

    Written by the poller threads, read by the renderer.
    """

    def __init__(self, n_trains: int):
        self._lock = threading.Lock()
        self._data: List[List[Arrival]] = [[] for _ in range(n_trains)]
        self._alerts: List[Optional[str]] = [None] * n_trains
        self._line_alerts: List[Optional[LineAlert]] = [None] * n_trains

    def set(self, index: int, arrivals: List[Arrival]) -> None:
        with self._lock:
            self._data[index] = list(arrivals)

    def snapshot(self) -> List[List[Arrival]]:
        with self._lock:
            return [list(x) for x in self._data]

    def set_alerts(self, tags: List[Optional[str]]) -> None:
        with self._lock:
            self._alerts = list(tags)

    def alerts(self) -> List[Optional[str]]:
        with self._lock:
            return list(self._alerts)

    def set_line_alerts(self, alerts: List[Optional[LineAlert]]) -> None:
        """Rich per-stop alerts (tag + reason) for the AlertScene. Additive: the
        string-tag view via `set_alerts`/`alerts` is unchanged."""
        with self._lock:
            self._line_alerts = list(alerts)

    def line_alerts(self) -> List[Optional[LineAlert]]:
        with self._lock:
            return list(self._line_alerts)


class WeatherHolder:
    """Thread-safe latest Weather (or None)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._value = None

    def set(self, weather) -> None:
        with self._lock:
            self._value = weather

    def get(self):
        with self._lock:
            return self._value


class Holder:
    """Thread-safe latest-value holder for a background snapshot (e.g. SkyData,
    SpaceData): a poller `set`s it, the render loop `get`s it."""

    def __init__(self, value=None):
        self._lock = threading.Lock()
        self._value = value

    def set(self, value) -> None:
        with self._lock:
            self._value = value

    def get(self):
        with self._lock:
            return self._value
