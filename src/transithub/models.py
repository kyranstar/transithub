from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TrackedTrain:
    """One configured stop: a line at a station in a direction."""
    line: str
    stop_id: str
    direction: str           # "N" or "S"
    destination: str = ""    # blank = use live headsign
    weight: int = 1          # relative share of screen time in the rotation

    @property
    def gtfs_stop_id(self) -> str:
        return f"{self.stop_id}{self.direction}"


@dataclass(frozen=True)
class Arrival:
    """A computed upcoming arrival at a tracked stop."""
    line: str
    destination: str
    arrival_time: datetime

    def seconds_until(self, now: datetime) -> float:
        return (self.arrival_time - now).total_seconds()

    def minutes_until(self, now: datetime) -> int:
        return max(0, int(self.seconds_until(now) // 60))

    def is_arriving(self, now: datetime, threshold_seconds: int) -> bool:
        return self.seconds_until(now) <= threshold_seconds
