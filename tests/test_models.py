from datetime import datetime, timedelta

from transithub.models import TrackedTrain, Arrival

NOW = datetime(2026, 5, 23, 12, 0, 0)


def test_gtfs_stop_id_appends_direction():
    assert TrackedTrain(line="L", stop_id="L16", direction="N").gtfs_stop_id == "L16N"


def test_minutes_until_floors():
    a = Arrival(line="L", destination="8 Av", arrival_time=NOW + timedelta(seconds=149))
    assert a.minutes_until(NOW) == 2


def test_minutes_until_never_negative():
    a = Arrival(line="L", destination="8 Av", arrival_time=NOW - timedelta(seconds=30))
    assert a.minutes_until(NOW) == 0


def test_is_arriving_within_threshold():
    a = Arrival(line="L", destination="8 Av", arrival_time=NOW + timedelta(seconds=20))
    assert a.is_arriving(NOW, threshold_seconds=30) is True


def test_not_arriving_outside_threshold():
    a = Arrival(line="L", destination="8 Av", arrival_time=NOW + timedelta(seconds=90))
    assert a.is_arriving(NOW, threshold_seconds=30) is False
