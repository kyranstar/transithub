import textwrap

import pytest

from transithub.config import load_config


def _write(tmp_path, body):
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent(body))
    return str(p)


def test_loads_full_config(tmp_path):
    cfg = load_config(_write(tmp_path, """
        matrix:
          rows: 32
          cols: 64
          hardware_mapping: adafruit-hat
          brightness: 60
        mta:
          poll_seconds: 30
        display:
          arriving_threshold_seconds: 30
          page_seconds: 6
          scroll_speed: 1
        alerts:
          enabled: false
          poll_seconds: 90
        trains:
          - {line: "L", stop_id: "L16", direction: "N", weight: 3}
          - {line: "M", stop_id: "M08", direction: "N", destination: "Manhattan"}
    """))
    assert cfg.matrix.rows == 32 and cfg.matrix.cols == 64
    assert cfg.matrix.hardware_mapping == "adafruit-hat"
    assert cfg.mta.poll_seconds == 30
    assert cfg.display.page_seconds == 6
    assert cfg.alerts.enabled is False and cfg.alerts.poll_seconds == 90
    assert len(cfg.trains) == 2
    assert cfg.trains[0].gtfs_stop_id == "L16N"
    assert cfg.trains[0].weight == 3
    assert cfg.trains[1].destination == "Manhattan"
    assert cfg.trains[1].weight == 1  # default


def test_defaults_applied(tmp_path):
    cfg = load_config(_write(tmp_path, """
        trains:
          - {line: "L", stop_id: "L16", direction: "N"}
    """))
    assert cfg.matrix.rows == 32 and cfg.matrix.chain_length == 1
    assert cfg.matrix.hardware_mapping == "adafruit-hat"
    assert cfg.mta.poll_seconds == 30
    assert cfg.display.arriving_threshold_seconds == 20
    assert cfg.alerts.enabled is True and cfg.alerts.poll_seconds == 60


def test_requires_at_least_one_train(tmp_path):
    with pytest.raises(ValueError):
        load_config(_write(tmp_path, "trains: []\n"))


def test_loads_weather_config(tmp_path):
    cfg = load_config(_write(tmp_path, """
        trains:
          - {line: "L", stop_id: "L16", direction: "N"}
        location: {latitude: 40.5, longitude: -73.9}
        weather: {enabled: true, units: celsius, poll_seconds: 300, rundown_every_minutes: 10, rundown_seconds: 45}
        notifications: {sunrise: false, sunset: true}
        trash: {days: ["tuesday", "friday"]}
    """))
    assert cfg.location.latitude == 40.5 and cfg.location.longitude == -73.9
    assert cfg.weather.units == "celsius" and cfg.weather.rundown_every_minutes == 10
    assert cfg.notifications.sunrise is False and cfg.notifications.sunset is True
    assert cfg.trash.days == ["tuesday", "friday"]


def test_weather_defaults(tmp_path):
    cfg = load_config(_write(tmp_path, """
        trains:
          - {line: "L", stop_id: "L16", direction: "N"}
    """))
    assert abs(cfg.location.latitude - 40.70) < 0.01
    assert cfg.weather.enabled is True and cfg.weather.units == "fahrenheit"
    assert cfg.weather.rundown_every_minutes == 6 and cfg.weather.rundown_rounds == 2
    assert cfg.notifications.sunrise is True and cfg.trash.days == ["monday"]


def test_ambient_defaults(tmp_path):
    cfg = load_config(_write(tmp_path, """
        trains:
          - {line: "L", stop_id: "L16", direction: "N"}
    """))
    assert cfg.night.bedtime == "21:30"
    assert cfg.night.evening_brightness == 0.5 and cfg.night.night_brightness == 0.16
    assert cfg.sky.enabled is True and cfg.space.enabled is True
    assert cfg.local.enabled is True and cfg.local.markets == []


def test_ambient_overrides(tmp_path):
    cfg = load_config(_write(tmp_path, """
        trains:
          - {line: "L", stop_id: "L16", direction: "N"}
        night: {bedtime: "22:00", night_brightness: 0.1}
        sky: {enabled: false}
        local:
          markets:
            - {name: "TEST MKT", day: "monday", until: "5"}
    """))
    assert cfg.night.bedtime == "22:00" and cfg.night.night_brightness == 0.1
    assert cfg.sky.enabled is False
    assert cfg.local.markets[0]["name"] == "TEST MKT"
