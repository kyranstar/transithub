from datetime import datetime

from transithub.weather.model import (
    Condition, condition_for_code, SunPhase, sun_phase, Weather, flags, Flag,
    PrecipWindow, precip_window,
)


def _w(**kw):
    base = dict(temp=54.0, feels_like=51.0, condition=Condition.CLOUDY,
                today_high=58.0, today_low=41.0, precip_prob=10, uv_index=2.0, aqi=40,
                sunrise=datetime(2026, 5, 23, 5, 31), sunset=datetime(2026, 5, 23, 20, 13))
    base.update(kw)
    return Weather(**base)


def test_condition_mapping():
    assert condition_for_code(0) is Condition.CLEAR
    assert condition_for_code(3) is Condition.CLOUDY
    assert condition_for_code(48) is Condition.CLOUDY
    assert condition_for_code(61) is Condition.RAIN
    assert condition_for_code(95) is Condition.RAIN
    assert condition_for_code(73) is Condition.SNOW
    assert condition_for_code(86) is Condition.SNOW


def test_sun_phase_windows():
    sr, ss = datetime(2026, 5, 23, 6, 0), datetime(2026, 5, 23, 20, 0)
    assert sun_phase(datetime(2026, 5, 23, 5, 45), sr, ss) is SunPhase.SUNRISE
    assert sun_phase(datetime(2026, 5, 23, 12, 0), sr, ss) is SunPhase.DAY
    assert sun_phase(datetime(2026, 5, 23, 19, 30), sr, ss) is SunPhase.SUNSET
    assert sun_phase(datetime(2026, 5, 23, 2, 0), sr, ss) is SunPhase.NIGHT


def test_flags_none_when_calm():
    assert flags(_w(), datetime(2026, 5, 23, 9, 0), trash_days=["monday"]) == []


def test_flag_uv_levels():
    assert flags(_w(uv_index=6.0), datetime(2026, 5, 23, 9, 0), [])[0] == Flag("UV HIGH", "SUNSCREEN")
    assert flags(_w(uv_index=9.0), datetime(2026, 5, 23, 9, 0), [])[0] == Flag("UV VERY HIGH", "SUNSCREEN")
    assert flags(_w(uv_index=11.5), datetime(2026, 5, 23, 9, 0), [])[0] == Flag("UV EXTREME", "SUNSCREEN")


def test_flag_aqi_levels():
    assert Flag("AIR QUALITY", "UNHEALTHY (SENS)") in flags(_w(aqi=120), datetime(2026, 5, 23, 9, 0), [])
    assert Flag("AIR QUALITY", "HAZARDOUS") in flags(_w(aqi=350), datetime(2026, 5, 23, 9, 0), [])
    assert all(f.headline != "AIR QUALITY" for f in flags(_w(aqi=80), datetime(2026, 5, 23, 9, 0), []))


def test_flag_precip_rain_vs_snow():
    rain = flags(_w(condition=Condition.RAIN, precip_prob=70), datetime(2026, 5, 23, 9, 0), [])
    snow = flags(_w(condition=Condition.SNOW, precip_prob=70), datetime(2026, 5, 23, 9, 0), [])
    assert Flag("RAIN LIKELY", "70%") in rain
    assert Flag("SNOW LIKELY", "70%") in snow


def test_flag_trash_tomorrow():
    out = flags(_w(), datetime(2026, 5, 23, 18, 0), trash_days=["sunday"])
    assert Flag("TRASH TMRW", "") in out
    assert Flag("TRASH TMRW", "") not in flags(_w(), datetime(2026, 5, 23, 9, 0), ["sunday"])


# --- precip window ---

def _hourly(start_hour, probs, precip=None, snow=None, codes=None):
    n = len(probs)
    times = [datetime(2026, 5, 24, start_hour + i, 0).isoformat() for i in range(n)]
    return {
        "time": times,
        "precipitation_probability": probs,
        "precipitation": precip or [0.0] * n,
        "snowfall": snow or [0.0] * n,
        "weather_code": codes or [61] * n,
    }


def test_precip_window_future_block():
    # rain 2a-6a (>=30%), then clears; now is midnight
    h = _hourly(0, [10, 20, 40, 80, 95, 60, 10, 0],
                precip=[0, 0, 0.05, 0.1, 0.24, 0.1, 0, 0])
    pw = precip_window(h, datetime(2026, 5, 24, 0, 30))
    assert pw.ongoing is False
    assert pw.start == datetime(2026, 5, 24, 2, 0)
    assert pw.end == datetime(2026, 5, 24, 6, 0)     # first hour back under 30%
    assert pw.peak_prob == 95
    assert round(pw.amount_in, 2) == 0.49
    assert pw.is_snow is False


def test_precip_window_ongoing():
    # it's raining now (now=3a, that hour is 80%)
    h = _hourly(0, [10, 20, 40, 80, 95, 60, 10, 0])
    pw = precip_window(h, datetime(2026, 5, 24, 3, 15))
    assert pw.ongoing is True
    assert pw.end == datetime(2026, 5, 24, 6, 0)


def test_precip_window_snow_uses_snowfall_amount():
    h = _hourly(0, [50, 60, 70], precip=[0.1, 0.1, 0.1], snow=[1.0, 1.0, 0.5],
                codes=[73, 73, 73])
    pw = precip_window(h, datetime(2026, 5, 24, 0, 0))
    assert pw.is_snow is True
    assert round(pw.amount_in, 2) == 2.5          # snowfall sum, not the liquid 0.3


def test_precip_window_none_when_dry():
    assert precip_window(_hourly(0, [0, 5, 10, 20]), datetime(2026, 5, 24, 0, 0)) is None


def test_precip_window_now_precip_overrides_low_hourly_chance():
    # it's actually raining now (now_precip=True) even though this hour's chance is 20%
    h = _hourly(0, [20, 20, 40, 80, 95, 10])
    pw = precip_window(h, datetime(2026, 5, 24, 1, 15), now_precip=True)
    assert pw.ongoing is True
    assert pw.start == datetime(2026, 5, 24, 1, 0)   # spans from now
    assert pw.end == datetime(2026, 5, 24, 5, 0)     # through the imminent block


def _pw(**kw):
    base = dict(is_snow=False, ongoing=False, start=datetime(2026, 5, 24, 18),
                end=datetime(2026, 5, 25, 2), peak_prob=97, amount_in=2.0)
    base.update(kw)
    return PrecipWindow(**base)


def test_flag_uses_precip_window_future():
    out = flags(_w(precip=_pw()), datetime(2026, 5, 24, 12, 0), [])
    assert Flag("RAIN 6p-2a", "97%  2.0in") in out


def test_flag_precip_ongoing_and_trace_hidden():
    pw = _pw(ongoing=True, end=datetime(2026, 5, 24, 18), peak_prob=80, amount_in=0.04)
    out = flags(_w(precip=pw), datetime(2026, 5, 24, 14, 0), [])
    assert Flag("RAIN til 6p", "80%") in out      # ongoing + trace amount hidden
