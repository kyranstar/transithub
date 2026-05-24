from datetime import datetime, timedelta

from transithub.models import TrackedTrain
from transithub.mta.feed import FeedClient, feed_dependency_available

NOW = datetime(2026, 5, 23, 12, 0, 0)


class FakeStop:
    def __init__(self, stop_id, arrival):
        self.stop_id = stop_id
        self.arrival = arrival


class FakeTrip:
    def __init__(self, headsign, stops):
        self.headsign_text = headsign
        self.stop_time_updates = stops


class FakeFeed:
    def __init__(self, line):
        self.line = line
        self.refreshed = 0
        self._trips = [
            FakeTrip("8 Av", [FakeStop("L16N", NOW + timedelta(minutes=8))]),
            FakeTrip("8 Av", [FakeStop("L16N", NOW + timedelta(minutes=2))]),
            FakeTrip("Canarsie", [FakeStop("L16S", NOW + timedelta(minutes=1))]),  # wrong dir
        ]

    def refresh(self):
        self.refreshed += 1

    def filter_trips(self, line_id=None, headed_for_stop_id=None, underway=True):
        return [t for t in self._trips
                if any(s.stop_id == headed_for_stop_id for s in t.stop_time_updates)]


def test_returns_sorted_future_arrivals():
    client = FeedClient(feed_factory=FakeFeed)
    train = TrackedTrain(line="L", stop_id="L16", direction="N")
    arrivals = client.get_next_arrivals(train, count=2, now=NOW)
    assert [a.minutes_until(NOW) for a in arrivals] == [2, 8]
    assert arrivals[0].destination == "8 Av"  # live headsign


def test_destination_override_wins():
    client = FeedClient(feed_factory=FakeFeed)
    train = TrackedTrain(line="L", stop_id="L16", direction="N", destination="8 Av Manh")
    arrivals = client.get_next_arrivals(train, now=NOW)
    assert arrivals[0].destination == "8 Av Manh"


def test_feed_dependency_available():
    # nyct-gtfs is a declared dependency, so it must import in a correct install
    assert feed_dependency_available() is True


def test_feed_cached_per_line():
    client = FeedClient(feed_factory=FakeFeed)
    t = TrackedTrain(line="L", stop_id="L16", direction="N")
    client.get_next_arrivals(t, now=NOW)
    client.get_next_arrivals(t, now=NOW)
    assert client._feeds["L"].refreshed == 2  # reused, refreshed each call
