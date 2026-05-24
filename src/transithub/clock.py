from datetime import datetime
from zoneinfo import ZoneInfo

_NY = ZoneInfo("America/New_York")


def now() -> datetime:
    """Current NYC wall-clock time as a tz-naive datetime.

    The MTA feed reports arrival times as tz-naive America/New_York timestamps,
    so we compare against NYC time regardless of the host's system timezone
    (a Raspberry Pi often defaults to UTC).
    """
    return datetime.now(_NY).replace(tzinfo=None)
