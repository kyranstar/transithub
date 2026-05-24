import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List, Optional


class Condition(str, Enum):
    CLEAR = "clear"
    CLOUDY = "cloudy"
    RAIN = "rain"
    SNOW = "snow"


class SunPhase(str, Enum):
    SUNRISE = "sunrise"
    DAY = "day"
    SUNSET = "sunset"
    NIGHT = "night"


def condition_for_code(code: int) -> Condition:
    """Map a WMO weather code to one of four scene categories."""
    if code in (0, 1):
        return Condition.CLEAR
    if code in (2, 3, 45, 48):
        return Condition.CLOUDY
    if code in (71, 72, 73, 74, 75, 76, 77, 85, 86):
        return Condition.SNOW
    return Condition.RAIN  # 51-67 drizzle/rain, 80-82 showers, 95-99 thunderstorm


@dataclass(frozen=True)
class PrecipWindow:
    """The soonest (or ongoing) stretch of rain/snow."""
    is_snow: bool
    ongoing: bool        # True if it's precipitating right now
    start: datetime      # when it starts (ignored when ongoing)
    end: datetime        # when it stops
    peak_prob: int       # highest chance across the window
    amount_in: float     # total rain (or snow depth) over the window, inches


@dataclass(frozen=True)
class Weather:
    temp: float
    feels_like: float
    condition: Condition
    today_high: float
    today_low: float
    precip_prob: int
    uv_index: float
    aqi: int
    sunrise: datetime
    sunset: datetime
    precip: Optional[PrecipWindow] = None


@dataclass(frozen=True)
class Flag:
    headline: str
    detail: str = ""


def _hour_label(dt: datetime) -> str:
    """Compact hour like '6p', '2a', '12a'."""
    return dt.strftime("%-I%p").lower().replace("m", "")


def _window_label(start: datetime, end: datetime) -> str:
    s, e = _hour_label(start), _hour_label(end)
    return f"{s[:-1]}-{e}" if s[-1] == e[-1] else f"{s}-{e}"   # "2-8a" or "6p-2a"


PRECIP_THRESHOLD = 30   # percent chance that counts as a "rainy/snowy" hour
_TRACE_IN = 0.1         # hide amounts below this (inches)


def precip_window(hourly: dict, now: datetime, now_precip: bool = False,
                  threshold: int = PRECIP_THRESHOLD) -> Optional[PrecipWindow]:
    """The soonest (or ongoing) precip stretch (>= threshold% chance) from `hourly`.

    `now_precip` is the real current observation (is it precipitating right now?) —
    it makes the window 'ongoing' even when this hour's forecast chance is below
    threshold, so a light-but-real rain reads "RAIN til <end>".
    """
    times = [datetime.fromisoformat(t) for t in hourly.get("time", [])]
    if not times:
        return None
    prob = hourly["precipitation_probability"]
    amt = hourly["precipitation"]
    snow = hourly["snowfall"]
    codes = hourly["weather_code"]
    n = len(times)

    cur = 0
    for i in range(n):
        if times[i] <= now:
            cur = i
        else:
            break

    def rainy(i):
        return (prob[i] or 0) >= threshold

    ongoing = now_precip or rainy(cur)
    first = cur if rainy(cur) else next((i for i in range(cur, n) if rainy(i)), None)
    if first is None and not ongoing:
        return None

    if first is None:                 # precipitating now, forecast clears immediately
        lo, hi = cur, min(cur + 1, n)
    else:
        end = first
        while end < n and rainy(end):
            end += 1
        lo, hi = (cur if ongoing else first), end   # ongoing spans from now -> end

    block = range(lo, hi)
    is_snow = any(condition_for_code(codes[i]) is Condition.SNOW for i in block)
    amount = sum((snow[i] if is_snow else amt[i]) or 0 for i in block)
    return PrecipWindow(
        is_snow=is_snow,
        ongoing=ongoing,
        start=times[lo],
        end=times[hi] if hi < n else times[-1],
        peak_prob=int(max((prob[i] or 0) for i in block)),
        amount_in=round(amount, 2),
    )


def _julian_day(dt: datetime) -> float:
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)        # naive datetimes are treated as UTC
    y, m = dt.year, dt.month
    d = dt.day + (dt.hour + dt.minute / 60 + dt.second / 3600) / 24
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + b - 1524.5


def moon_phase(now: datetime) -> float:
    """Lunar phase as a fraction in [0, 1): 0 new, 0.25 first quarter, 0.5 full,
    0.75 last quarter. Astronomical (no API) — mean elongation plus the leading
    periodic terms (Meeus, ch. 48), accurate to ~1-2% illumination."""
    T = (_julian_day(now) - 2451545.0) / 36525.0          # Julian centuries since J2000
    D = 297.8501921 + 445267.1114034 * T - 0.0018819 * T * T   # mean elongation Moon-Sun
    M = 357.5291092 + 35999.0502909 * T                        # Sun's mean anomaly
    Mp = 134.9633964 + 477198.8675055 * T + 0.0087414 * T * T  # Moon's mean anomaly
    r = math.radians
    phase_angle = (180 - D
                   - 6.289 * math.sin(r(Mp)) + 2.100 * math.sin(r(M))
                   - 1.274 * math.sin(r(2 * D - Mp)) - 0.658 * math.sin(r(2 * D))
                   - 0.214 * math.sin(r(2 * Mp)) - 0.110 * math.sin(r(D)))
    illum = (1 + math.cos(r(phase_angle))) / 2            # sunlit fraction of the disc
    elong = math.acos(max(-1.0, min(1.0, 1 - 2 * illum))) / (2 * math.pi)   # 0..0.5
    return elong if (D % 360) < 180 else 1 - elong       # waxing first half, waning second


def sun_phase(now: datetime, sunrise: datetime, sunset: datetime) -> SunPhase:
    if sunrise - timedelta(minutes=30) <= now <= sunrise + timedelta(minutes=30):
        return SunPhase.SUNRISE
    if sunset - timedelta(minutes=45) <= now <= sunset + timedelta(minutes=10):
        return SunPhase.SUNSET
    if sunrise < now < sunset:
        return SunPhase.DAY
    return SunPhase.NIGHT


def trash_tomorrow(now: datetime, trash_days: List[str]) -> bool:
    if now.hour < 15:                       # only 3pm -> midnight
        return False
    tomorrow = (now + timedelta(days=1)).strftime("%A").lower()
    return tomorrow in {d.strip().lower() for d in trash_days}


def flags(weather: Weather, now: datetime, trash_days: List[str]) -> List[Flag]:
    out: List[Flag] = []
    if trash_tomorrow(now, trash_days):
        out.append(Flag("TRASH TMRW"))
    pw = weather.precip
    if pw is not None:
        kind = "SNOW" if pw.is_snow else "RAIN"
        head = f"{kind} til {_hour_label(pw.end)}" if pw.ongoing \
            else f"{kind} {_window_label(pw.start, pw.end)}"
        detail = (f"{pw.peak_prob}%  {pw.amount_in:.1f}in"
                  if pw.amount_in >= _TRACE_IN else f"{pw.peak_prob}%")
        out.append(Flag(head, detail))
    elif weather.precip_prob >= 50:   # fallback when no hourly data
        head = "SNOW LIKELY" if weather.condition is Condition.SNOW else "RAIN LIKELY"
        out.append(Flag(head, f"{weather.precip_prob}%"))
    uv = weather.uv_index
    if uv >= 11:
        out.append(Flag("UV EXTREME", "SUNSCREEN"))
    elif uv >= 8:
        out.append(Flag("UV VERY HIGH", "SUNSCREEN"))
    elif uv >= 6:
        out.append(Flag("UV HIGH", "SUNSCREEN"))
    aqi = weather.aqi
    if aqi >= 301:
        out.append(Flag("AIR QUALITY", "HAZARDOUS"))
    elif aqi >= 201:
        out.append(Flag("AIR QUALITY", "VERY UNHEALTHY"))
    elif aqi >= 151:
        out.append(Flag("AIR QUALITY", "UNHEALTHY"))
    elif aqi >= 101:
        out.append(Flag("AIR QUALITY", "UNHEALTHY (SENS)"))
    return out
