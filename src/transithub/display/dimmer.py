"""Brightness over the day, as one smooth curve: a dawn ramp up to full daylight, a
gentle fade after sunset, a wind-down to a low readable glow after bedtime, held
through the night — no abrupt jumps, so the panel never blinks bright or dark."""
from __future__ import annotations

from datetime import datetime, time, timedelta

from PIL import Image

from ..profile import DEFAULT_BEDTIME

DAWN_RAMP = timedelta(minutes=30)    # brighten to full over the half hour up to sunrise
WIND_DOWN = timedelta(minutes=45)    # ease to the night floor over the 45 min after bedtime

# Clock-based sun times used before the first weather fetch.
_FALLBACK_SUNRISE = time(6, 30)
_FALLBACK_SUNSET = time(19, 0)


def _ramp(now: datetime, t0: datetime, t1: datetime, v0: float, v1: float) -> float:
    """Linear from v0 at t0 to v1 at t1, clamped outside the span (v1 if degenerate)."""
    span = (t1 - t0).total_seconds()
    if span <= 0:
        return v1
    frac = max(0.0, min(1.0, (now - t0).total_seconds() / span))
    return v0 + (v1 - v0) * frac


class Dimmer:
    """Scales the final frame's brightness by the time of day, on a continuous curve.

    Full by day; fades from full at sunset down to `evening_floor` at bedtime, then
    eases to `night_floor` over the following ``WIND_DOWN``; holds `night_floor`
    overnight; ramps back up to full over ``DAWN_RAMP`` into sunrise. Every
    transition is gradual — no sudden brighten at dawn or drop at bedtime."""

    def __init__(self, evening_floor: float = 0.5, night_floor: float = 0.16,
                 bedtime: time = DEFAULT_BEDTIME):
        self.evening_floor = evening_floor
        self.night_floor = night_floor
        self.bedtime = bedtime

    def level(self, now: datetime, weather=None) -> float:
        sr = getattr(weather, "sunrise", None)
        ss = getattr(weather, "sunset", None)
        if not (isinstance(sr, datetime) and isinstance(ss, datetime)):
            sr = now.replace(hour=_FALLBACK_SUNRISE.hour, minute=_FALLBACK_SUNRISE.minute,
                             second=0, microsecond=0)
            ss = now.replace(hour=_FALLBACK_SUNSET.hour, minute=_FALLBACK_SUNSET.minute,
                             second=0, microsecond=0)
        bed = now.replace(hour=self.bedtime.hour, minute=self.bedtime.minute,
                          second=0, microsecond=0)
        nf, ef = self.night_floor, self.evening_floor

        if now < sr - DAWN_RAMP:
            return nf                                          # deep night, before dawn
        if now < sr:
            return _ramp(now, sr - DAWN_RAMP, sr, nf, 1.0)     # dawn ramp up to full
        if now < ss:
            return 1.0                                         # full daylight
        if now < bed:
            return _ramp(now, ss, bed, 1.0, ef)                # evening fade
        if now < bed + WIND_DOWN:
            return _ramp(now, bed, bed + WIND_DOWN, ef, nf)    # bedtime wind-down
        return nf                                              # deep night, after bedtime

    def apply(self, img: Image.Image, ctx) -> Image.Image:
        level = self.level(ctx.now, getattr(ctx, "weather", None))
        if level >= 0.999:
            return img
        return Image.eval(img, lambda v: int(v * level))
