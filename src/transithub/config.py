from dataclasses import dataclass, field
from typing import List
import yaml

from .models import TrackedTrain


@dataclass
class MatrixConfig:
    rows: int = 32
    cols: int = 64
    chain_length: int = 1
    parallel: int = 1
    hardware_mapping: str = "adafruit-hat"
    brightness: int = 60
    gpio_slowdown: int = 2
    pwm_bits: int = 11          # lower (e.g. 7-8) raises refresh rate to reduce flicker
    limit_refresh_rate_hz: int = 0   # 0 = unlimited; set ~100 to hold a steady rate (anti-flicker)
    # The matrix library drops root to the 'daemon' user after init by default,
    # which then can't read the venv/fonts under your home dir. Keep root instead.
    drop_privileges: bool = False


@dataclass
class MtaConfig:
    poll_seconds: int = 30


@dataclass
class DisplayConfig:
    arriving_threshold_seconds: int = 20
    page_seconds: int = 6
    scroll_speed: int = 1


@dataclass
class AlertsConfig:
    enabled: bool = True
    poll_seconds: int = 60


@dataclass
class LocationConfig:
    latitude: float = 40.70    # Bushwick, Brooklyn (neighborhood-level)
    longitude: float = -73.92


@dataclass
class WeatherConfig:
    enabled: bool = True
    units: str = "fahrenheit"
    poll_seconds: int = 600
    rundown_every_minutes: int = 7     # how often the weather rundown interrupts
    rundown_rounds: int = 2            # full passes of the slide deck per rundown


@dataclass
class NotificationsConfig:
    sunrise: bool = True
    sunset: bool = True


@dataclass
class NightConfig:
    """Evening/overnight dimming. Brightness ramps from full at sunset down to
    `evening_brightness` at `bedtime`, then holds `night_brightness` overnight."""
    bedtime: str = "21:30"
    evening_brightness: float = 0.5
    night_brightness: float = 0.16


@dataclass
class SkyConfig:
    enabled: bool = True            # master switch for the sky scenes
    iss: bool = True                # ISS pass heads-up + overhead arc
    planes: bool = True             # a plane passing directly overhead
    moon: bool = True               # full / new-moon-night salute
    plane_radius_nm: float = 3.0    # how close a plane must be to count as "overhead"
    plane_max_alt_ft: int = 10000   # only planes below this (low, audible) count


@dataclass
class SpaceConfig:
    enabled: bool = True            # master switch for the space interjections
    humans: bool = True             # "N humans in space" fact
    earth: bool = True              # NASA EPIC photo of Earth


@dataclass
class LocalConfig:
    enabled: bool = True                    # show a nearby farmers market open today
    markets: List[dict] = field(default_factory=list)   # curated; see config.example.yaml


@dataclass
class TrashConfig:
    days: List[str] = field(default_factory=lambda: ["monday"])


@dataclass
class Config:
    matrix: MatrixConfig = field(default_factory=MatrixConfig)
    mta: MtaConfig = field(default_factory=MtaConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    alerts: AlertsConfig = field(default_factory=AlertsConfig)
    location: LocationConfig = field(default_factory=LocationConfig)
    weather: WeatherConfig = field(default_factory=WeatherConfig)
    notifications: NotificationsConfig = field(default_factory=NotificationsConfig)
    night: NightConfig = field(default_factory=NightConfig)
    sky: SkyConfig = field(default_factory=SkyConfig)
    space: SpaceConfig = field(default_factory=SpaceConfig)
    local: LocalConfig = field(default_factory=LocalConfig)
    trash: TrashConfig = field(default_factory=TrashConfig)
    trains: List[TrackedTrain] = field(default_factory=list)


def _section(cls, data: dict):
    known = set(cls.__dataclass_fields__)
    return cls(**{k: v for k, v in (data or {}).items() if k in known})


def load_config(path: str) -> Config:
    with open(path) as fh:
        raw = yaml.safe_load(fh) or {}
    trains = [
        TrackedTrain(
            line=str(t["line"]),
            stop_id=str(t["stop_id"]),
            direction=str(t["direction"]),
            destination=str(t.get("destination", "")),
            weight=int(t.get("weight", 1)),
        )
        for t in (raw.get("trains") or [])
    ]
    if not trains:
        raise ValueError("config must list at least one train under 'trains'")
    return Config(
        matrix=_section(MatrixConfig, raw.get("matrix")),
        mta=_section(MtaConfig, raw.get("mta")),
        display=_section(DisplayConfig, raw.get("display")),
        alerts=_section(AlertsConfig, raw.get("alerts")),
        location=_section(LocationConfig, raw.get("location")),
        weather=_section(WeatherConfig, raw.get("weather")),
        notifications=_section(NotificationsConfig, raw.get("notifications")),
        night=_section(NightConfig, raw.get("night")),
        sky=_section(SkyConfig, raw.get("sky")),
        space=_section(SpaceConfig, raw.get("space")),
        local=_section(LocalConfig, raw.get("local")),
        trash=_section(TrashConfig, raw.get("trash")),
        trains=trains,
    )
