import json
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Callable

from ..clock import now as now_eastern
from .model import Weather, condition_for_code, precip_window

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AQI_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"


def _default_fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "transithub"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


class WeatherClient:
    """Fetches current weather + today's forecast + US AQI from Open-Meteo (no API key)."""

    def __init__(self, latitude: float, longitude: float, units: str = "fahrenheit",
                 fetcher: Callable[[str], dict] = _default_fetch):
        self.lat = latitude
        self.lon = longitude
        self.units = units
        self._fetch = fetcher

    def _forecast_url(self) -> str:
        q = urllib.parse.urlencode({
            "latitude": self.lat, "longitude": self.lon,
            "current": "temperature_2m,apparent_temperature,weather_code,precipitation",
            "hourly": "precipitation_probability,precipitation,snowfall,weather_code",
            "daily": ("weather_code,temperature_2m_max,temperature_2m_min,"
                      "precipitation_probability_max,uv_index_max,sunrise,sunset"),
            "temperature_unit": self.units,
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "America/New_York",
            "forecast_days": 2,
        })
        return f"{FORECAST_URL}?{q}"

    def _aqi_url(self) -> str:
        q = urllib.parse.urlencode({
            "latitude": self.lat, "longitude": self.lon,
            "current": "us_aqi", "timezone": "America/New_York",
        })
        return f"{AQI_URL}?{q}"

    def fetch(self) -> Weather:
        f = self._fetch(self._forecast_url())
        cur, daily = f["current"], f["daily"]
        try:
            aqi = int(self._fetch(self._aqi_url())["current"]["us_aqi"])
        except Exception:
            aqi = 0     # AQI is optional; never block the weather on it
        now_precip = float(cur.get("precipitation") or 0) > 0
        precip = (precip_window(f["hourly"], now_eastern(), now_precip=now_precip)
                  if "hourly" in f else None)
        return Weather(
            temp=float(cur["temperature_2m"]),
            feels_like=float(cur["apparent_temperature"]),
            condition=condition_for_code(int(cur["weather_code"])),
            today_high=float(daily["temperature_2m_max"][0]),
            today_low=float(daily["temperature_2m_min"][0]),
            precip_prob=int(daily["precipitation_probability_max"][0]),
            uv_index=float(daily["uv_index_max"][0]),
            aqi=aqi,
            sunrise=datetime.fromisoformat(daily["sunrise"][0]),
            sunset=datetime.fromisoformat(daily["sunset"][0]),
            precip=precip,
        )
