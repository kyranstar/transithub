from datetime import datetime, timezone

from transithub.clock import now


def test_now_is_naive():
    assert now().tzinfo is None


def test_now_matches_new_york_offset():
    # now() should equal current UTC shifted into America/New_York (within seconds),
    # proving it ignores the host's system timezone.
    from zoneinfo import ZoneInfo
    expected = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York")).replace(tzinfo=None)
    delta = abs((now() - expected).total_seconds())
    assert delta < 5
