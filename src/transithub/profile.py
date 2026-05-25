"""Day parts: when it's day, winding-down evening, or night.

Drives both which scenes are allowed to play (markets are a daytime thing, the
moon is a night thing) and how much the panel is dimmed."""
from __future__ import annotations

from datetime import datetime, time
from enum import Enum

DEFAULT_BEDTIME = time(21, 30)   # evening ramps down toward here; night begins after


class Profile(str, Enum):
    DAY = "day"
    EVENING = "evening"
    NIGHT = "night"


def day_profile(now: datetime, weather=None, bedtime: time = DEFAULT_BEDTIME) -> Profile:
    """DAY between sunrise and sunset, EVENING from sunset to bedtime, NIGHT after.

    Uses the real sun times from `weather` when available; otherwise falls back to
    a reasonable fixed schedule so the display still behaves before the first
    weather fetch."""
    sr = getattr(weather, "sunrise", None)
    ss = getattr(weather, "sunset", None)
    if isinstance(sr, datetime) and isinstance(ss, datetime):
        if sr <= now < ss:
            return Profile.DAY
        bed = now.replace(hour=bedtime.hour, minute=bedtime.minute, second=0, microsecond=0)
        if ss <= now < bed:
            return Profile.EVENING
        return Profile.NIGHT

    t = now.time()
    if time(19, 0) <= t < bedtime:
        return Profile.EVENING
    if time(6, 30) <= t < time(19, 0):
        return Profile.DAY
    return Profile.NIGHT
