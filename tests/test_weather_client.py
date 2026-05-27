import json
from datetime import datetime
from pathlib import Path

from transithub.weather.client import WeatherClient
from transithub.weather.model import Condition

FIX = Path(__file__).parent / "fixtures"


def _fetch(url):
    name = "open_meteo_aqi.json" if "air-quality" in url else "open_meteo_forecast.json"
    return json.loads((FIX / name).read_text())


def test_parses_weather():
    w = WeatherClient(40.69, -73.92, fetcher=_fetch).fetch()
    assert w.temp == 49.1 and w.feels_like == 44.8
    assert w.condition is Condition.CLOUDY            # code 3
    assert w.today_high == 56.8 and w.today_low == 48.9
    assert w.precip_prob == 97 and w.aqi == 49
    assert w.sunrise == datetime(2026, 5, 23, 5, 31)
    assert w.sunset == datetime(2026, 5, 23, 20, 13)


def test_units_in_request_url():
    seen = {}

    def spy(url):
        seen[url] = True
        return _fetch(url)

    WeatherClient(40.69, -73.92, units="celsius", fetcher=spy).fetch()
    assert any("temperature_unit=celsius" in u for u in seen)
    assert any("air-quality" in u for u in seen)


def test_requests_humidity_and_wind():
    seen = {}

    def spy(url):
        seen[url] = True
        return _fetch(url)

    WeatherClient(40.69, -73.92, fetcher=spy).fetch()
    assert any("relative_humidity_2m" in u for u in seen)
    assert any("wind_speed_10m" in u for u in seen)


def test_parses_humidity_and_wind():
    def fetch(url):
        if "air-quality" in url:
            return _fetch(url)
        return {
            "current": {"temperature_2m": 60.0, "apparent_temperature": 58.0,
                        "weather_code": 45, "precipitation": 0.0,
                        "relative_humidity_2m": 82, "wind_speed_10m": 23.4},
            "daily": {"time": ["2026-05-23"], "weather_code": [45],
                      "temperature_2m_max": [62.0], "temperature_2m_min": [50.0],
                      "precipitation_probability_max": [10], "uv_index_max": [3.0],
                      "sunrise": ["2026-05-23T05:31"], "sunset": ["2026-05-23T20:13"]},
        }

    w = WeatherClient(40.69, -73.92, fetcher=fetch).fetch()
    assert w.humidity == 82
    assert w.wind_mph == 23.4
    assert w.condition is Condition.FOG       # code 45 -> fog


def test_humidity_and_wind_default_when_absent():
    # the legacy fixture lacks the new fields -> defensive defaults, no crash
    w = WeatherClient(40.69, -73.92, fetcher=_fetch).fetch()
    assert w.humidity == 0
    assert w.wind_mph == 0.0


def test_requests_hourly_uv():
    from urllib.parse import parse_qs, urlparse

    seen = {}

    def spy(url):
        seen[url] = True
        return _fetch(url)

    WeatherClient(40.69, -73.92, fetcher=spy).fetch()
    forecast = next(u for u in seen if "air-quality" not in u)
    hourly = parse_qs(urlparse(forecast).query)["hourly"][0]
    assert "uv_index" in hourly.split(",")


def test_uv_now_from_hourly():
    def fetch(url):
        if "air-quality" in url:
            return _fetch(url)
        f = _fetch(url)
        # a flat day of hourly UV -> whatever hour we're in reads the same value
        f["hourly"] = {
            "time": [f"2026-05-23T{h:02d}:00" for h in range(24)],
            "precipitation_probability": [0] * 24, "precipitation": [0.0] * 24,
            "snowfall": [0.0] * 24, "weather_code": [3] * 24,
            "uv_index": [4.0] * 24,
        }
        return f

    w = WeatherClient(40.69, -73.92, fetcher=fetch).fetch()
    assert w.uv_now == 4.0


def test_uv_now_falls_back_to_daily_max_without_hourly():
    # legacy fixture has no hourly block -> uv_now mirrors the day's max
    w = WeatherClient(40.69, -73.92, fetcher=_fetch).fetch()
    assert w.uv_now == w.uv_index
