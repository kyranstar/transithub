from datetime import datetime
from typing import Callable, Dict, List, Optional

from ..clock import now as now_eastern
from ..models import Arrival, TrackedTrain


def feed_dependency_available() -> bool:
    """True if the nyct-gtfs backend can be imported in this environment."""
    import importlib.util
    return importlib.util.find_spec("nyct_gtfs") is not None


def _default_factory(line: str):
    from nyct_gtfs import NYCTFeed  # imported lazily; network on construct
    return NYCTFeed(line)


class FeedClient:
    """Fetches upcoming arrivals for tracked trains via nyct-gtfs."""

    def __init__(self, feed_factory: Callable[[str], object] = _default_factory):
        self._factory = feed_factory
        self._feeds: Dict[str, object] = {}

    def _feed(self, line: str):
        if line not in self._feeds:
            self._feeds[line] = self._factory(line)
        return self._feeds[line]

    def get_next_arrivals(
        self, train: TrackedTrain, count: int = 2, now: Optional[datetime] = None
    ) -> List[Arrival]:
        now = now or now_eastern()
        feed = self._feed(train.line)
        feed.refresh()
        target = train.gtfs_stop_id
        found: List[Arrival] = []
        for trip in feed.filter_trips(
            line_id=train.line, headed_for_stop_id=target, underway=True
        ):
            for stop in trip.stop_time_updates:
                if stop.stop_id == target and stop.arrival and stop.arrival >= now:
                    dest = train.destination or trip.headsign_text
                    found.append(Arrival(train.line, dest, stop.arrival))
                    break
        found.sort(key=lambda a: a.arrival_time)
        return found[:count]
