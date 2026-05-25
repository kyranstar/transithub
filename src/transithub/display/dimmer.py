"""Brightness over the day: full sun by day, a gentle fade after sunset, a low
readable glow deep at night — so the panel isn't a floodlight at 3am."""
from __future__ import annotations

from datetime import datetime, time

from PIL import Image

from ..profile import DEFAULT_BEDTIME, Profile, day_profile


class Dimmer:
    """Scales the final frame's brightness based on the time of day.

    DAY is full brightness. EVENING ramps linearly from full at sunset down to
    `evening_floor` at bedtime. NIGHT holds `night_floor` — a dim but legible level.
    """

    def __init__(self, evening_floor: float = 0.5, night_floor: float = 0.16,
                 bedtime: time = DEFAULT_BEDTIME):
        self.evening_floor = evening_floor
        self.night_floor = night_floor
        self.bedtime = bedtime

    def level(self, now: datetime, weather=None) -> float:
        profile = day_profile(now, weather, self.bedtime)
        if profile is Profile.DAY:
            return 1.0
        if profile is Profile.NIGHT:
            return self.night_floor
        ss = getattr(weather, "sunset", None)
        if not isinstance(ss, datetime):
            return self.evening_floor
        bed = now.replace(hour=self.bedtime.hour, minute=self.bedtime.minute,
                          second=0, microsecond=0)
        span = (bed - ss).total_seconds()
        frac = 0.0 if span <= 0 else max(0.0, min(1.0, (now - ss).total_seconds() / span))
        return 1.0 + (self.evening_floor - 1.0) * frac

    def apply(self, img: Image.Image, ctx) -> Image.Image:
        level = self.level(ctx.now, getattr(ctx, "weather", None))
        if level >= 0.999:
            return img
        return Image.eval(img, lambda v: int(v * level))
