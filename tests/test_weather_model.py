import math
from datetime import datetime, timedelta

from transithub.weather.model import (
    Condition, condition_for_code, SunPhase, sun_phase, Weather, flags, Flag,
    PrecipWindow, precip_window, moon_phase, summary, current_uv,
)


def _illum(phase):
    return (1 - math.cos(2 * math.pi * phase)) / 2


def _w(**kw):
    base = dict(temp=54.0, feels_like=51.0, condition=Condition.CLOUDY,
                today_high=58.0, today_low=41.0, precip_prob=10, uv_index=2.0, aqi=40,
                sunrise=datetime(2026, 5, 23, 5, 31), sunset=datetime(2026, 5, 23, 20, 13))
    base.update(kw)
    return Weather(**base)


def test_condition_mapping():
    assert condition_for_code(0) is Condition.CLEAR
    assert condition_for_code(3) is Condition.CLOUDY
    assert condition_for_code(61) is Condition.RAIN
    assert condition_for_code(95) is Condition.RAIN
    assert condition_for_code(73) is Condition.SNOW
    assert condition_for_code(86) is Condition.SNOW


def test_condition_fog_codes():
    assert condition_for_code(45) is Condition.FOG
    assert condition_for_code(48) is Condition.FOG


def test_weather_humidity_and_wind_default_to_zero():
    w = _w()                              # _w omits humidity/wind -> defaults
    assert w.humidity == 0
    assert w.wind_mph == 0.0


def test_weather_carries_humidity_and_wind():
    w = _w(humidity=88, wind_mph=24.5)
    assert w.humidity == 88
    assert w.wind_mph == 24.5


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


# --- UV warning is a daytime, peak-aware beat ---
# _w() day: sunrise 05:31, sunset 20:13 -> solar noon ~12:52.
UV_MORNING = datetime(2026, 5, 23, 9, 0)         # sun up, before the peak
UV_AFTERNOON = datetime(2026, 5, 23, 16, 0)      # sun up, past the peak
UV_AFTER_SUNSET = datetime(2026, 5, 23, 21, 0)   # sun is down


def test_flag_uv_shown_in_morning_even_when_current_reading_low():
    # current UV still low at 9am, but the day peaks high -> warn ahead of the peak
    out = flags(_w(uv_index=9.0, uv_now=1.0), UV_MORNING, [])
    assert Flag("UV VERY HIGH", "SUNSCREEN") in out


def test_flag_uv_hidden_after_sunset():
    out = flags(_w(uv_index=11.0, uv_now=0.0), UV_AFTER_SUNSET, [])
    assert all(not f.headline.startswith("UV") for f in out)


def test_flag_uv_hidden_after_peak_once_current_retreats_below_threshold():
    # past solar noon and the real reading has eased under the warn floor -> stand down
    out = flags(_w(uv_index=9.0, uv_now=3.0), UV_AFTERNOON, [])
    assert all(not f.headline.startswith("UV") for f in out)


def test_flag_uv_still_shown_after_peak_while_current_stays_high():
    out = flags(_w(uv_index=9.0, uv_now=7.0), UV_AFTERNOON, [])
    assert Flag("UV VERY HIGH", "SUNSCREEN") in out


def test_current_uv_picks_the_current_hour():
    h = {"time": [datetime(2026, 5, 23, n, 0).isoformat() for n in range(6)],
         "uv_index": [0.0, 0.2, 1.0, 3.0, 5.0, 7.0]}
    assert current_uv(h, datetime(2026, 5, 23, 4, 30)) == 5.0


def test_current_uv_none_without_hourly_data():
    assert current_uv({}, datetime(2026, 5, 23, 4, 30)) is None


def test_flag_aqi_levels():
    # Unhealthy air surfaces a single glanceable "close your windows" advisory whose
    # detail carries the severity; clean air says nothing.
    assert Flag("WINDOWS", "UNHEALTHY") in flags(_w(aqi=160), datetime(2026, 5, 23, 9, 0), [])
    assert Flag("WINDOWS", "HAZARDOUS") in flags(_w(aqi=350), datetime(2026, 5, 23, 9, 0), [])
    assert all(f.headline in ("WINDOWS",) or f.headline != "AIR QUALITY"
               for f in flags(_w(aqi=160), datetime(2026, 5, 23, 9, 0), []))
    assert all(f.headline != "WINDOWS" for f in flags(_w(aqi=80), datetime(2026, 5, 23, 9, 0), []))


def test_flag_precip_rain_vs_snow():
    rain = flags(_w(condition=Condition.RAIN, precip_prob=70), datetime(2026, 5, 23, 9, 0), [])
    snow = flags(_w(condition=Condition.SNOW, precip_prob=70), datetime(2026, 5, 23, 9, 0), [])
    assert Flag("RAIN LIKELY", "70%") in rain
    assert Flag("SNOW LIKELY", "70%") in snow


def test_flag_trash_tomorrow():
    out = flags(_w(), datetime(2026, 5, 23, 18, 0), trash_days=["sunday"])
    assert Flag("TRASH TMRW", "") in out
    assert Flag("TRASH TMRW", "") not in flags(_w(), datetime(2026, 5, 23, 9, 0), ["sunday"])


# --- window-closed advisory (folded into flags) ---

DAYTIME = datetime(2026, 5, 23, 13, 0)


def test_flag_windows_when_humid_but_otherwise_pleasant():
    out = flags(_w(temp=72, feels_like=72, humidity=85, aqi=30, uv_index=2), DAYTIME, [])
    assert Flag("WINDOWS", "HUMID") in out


def test_flag_windows_when_aqi_unhealthy():
    out = flags(_w(temp=72, feels_like=72, aqi=130, uv_index=2), DAYTIME, [])
    # one combined advisory, not a bare "AIR QUALITY" plus a separate "WINDOWS"
    assert Flag("WINDOWS", "BAD AIR") in out
    assert all(f.headline != "AIR QUALITY" for f in out)


def test_no_windows_flag_when_air_clean_and_dry():
    out = flags(_w(temp=72, feels_like=72, humidity=45, aqi=30, uv_index=2), DAYTIME, [])
    assert all(f.headline != "WINDOWS" for f in out)


# --- verbal summary ---

def test_summary_go_outside_on_a_perfect_day():
    w = _w(temp=68, feels_like=68, condition=Condition.CLEAR, precip_prob=5,
           aqi=25, uv_index=4, wind_mph=6)
    assert summary(w, DAYTIME) == "GO OUTSIDE"


def test_summary_stay_in_when_freezing():
    w = _w(temp=18, feels_like=10, today_high=24, today_low=12)
    assert summary(w, DAYTIME) == "STAY IN"


def test_summary_stay_in_when_scorching():
    w = _w(temp=96, feels_like=101, today_high=98, today_low=80)
    assert summary(w, DAYTIME) == "STAY IN"


def test_summary_stay_in_when_raining():
    w = _w(temp=66, feels_like=66, condition=Condition.RAIN, precip=_pw(ongoing=True))
    assert summary(w, DAYTIME) == "STAY IN"


def test_summary_stay_in_when_air_is_bad():
    w = _w(temp=70, feels_like=70, aqi=160)
    assert summary(w, DAYTIME) == "STAY IN"


def test_summary_stay_in_when_very_windy():
    w = _w(temp=66, feels_like=66, wind_mph=30)
    assert summary(w, DAYTIME) == "STAY IN"


def test_summary_no_go_outside_while_uv_warning_active():
    # lovely otherwise, but a high-UV morning is exactly when not to send you out bare
    w = _w(temp=68, feels_like=68, condition=Condition.CLEAR, precip_prob=5,
           aqi=25, wind_mph=6, uv_index=9.0, uv_now=2.0)
    assert summary(w, UV_MORNING) != "GO OUTSIDE"


def test_summary_go_outside_once_uv_retreats_before_sunset():
    # same day, late afternoon: the real UV has eased off -> a clear "GO OUTSIDE"
    w = _w(temp=68, feels_like=68, condition=Condition.CLEAR, precip_prob=5,
           aqi=25, wind_mph=6, uv_index=9.0, uv_now=3.0)
    assert summary(w, UV_AFTERNOON) == "GO OUTSIDE"


def test_summary_none_when_merely_okay():
    # 50F, dry, fine air, light breeze -> not great, not bad -> no verdict
    w = _w(temp=50, feels_like=48, precip_prob=15, aqi=40, uv_index=3, wind_mph=10)
    assert summary(w, DAYTIME) is None


def test_summary_fits_the_panel():
    from transithub.display import scenery as S
    for verdict in ("GO OUTSIDE", "STAY IN"):
        assert S.text_width(verdict, 1) <= 64


# --- moon phase (verified against moongiant.com / timeanddate.com) ---

def test_moon_phase_new():
    # New Moon ~May 16, 2026 -> barely illuminated, fraction near 0 (or 1)
    p = moon_phase(datetime(2026, 5, 16, 12, 0))
    assert min(p, 1 - p) < 0.02
    assert _illum(p) < 0.02


def test_moon_phase_first_quarter():
    # First Quarter on May 23, 2026 (~50% lit, waxing)
    p = moon_phase(datetime(2026, 5, 23, 12, 0))
    assert abs(p - 0.25) < 0.02


def test_moon_phase_full():
    # Full Moon ~May 31, 2026
    p = moon_phase(datetime(2026, 5, 31, 12, 0))
    assert abs(p - 0.5) < 0.02


def test_moon_phase_waxing_gibbous_today():
    # May 24, 2026: Waxing Gibbous, ~63% illuminated per moongiant.com
    p = moon_phase(datetime(2026, 5, 24, 12, 0))
    assert 0.25 < p < 0.5                      # between first quarter and full -> waxing gibbous
    assert 0.58 < _illum(p) < 0.66


def test_moon_phase_always_in_range():
    for day in range(1, 60):
        p = moon_phase(datetime(2026, 1, 1) + timedelta(days=day))
        assert 0.0 <= p < 1.0


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
