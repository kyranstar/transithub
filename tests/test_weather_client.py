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
