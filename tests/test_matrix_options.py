from transithub.config import MatrixConfig
from transithub.display.matrix import build_options_kwargs


def test_options_kwargs_from_config():
    cfg = MatrixConfig(rows=32, cols=64, chain_length=1, parallel=1,
                       hardware_mapping="adafruit-hat", brightness=55, gpio_slowdown=3,
                       pwm_bits=8, limit_refresh_rate_hz=100)
    kw = build_options_kwargs(cfg)
    assert kw["rows"] == 32 and kw["cols"] == 64
    assert kw["hardware_mapping"] == "adafruit-hat"
    assert kw["brightness"] == 55 and kw["gpio_slowdown"] == 3
    assert kw["pwm_bits"] == 8 and kw["limit_refresh_rate_hz"] == 100
    assert kw["drop_privileges"] is False  # keep root so it can read venv/fonts


def test_drop_privileges_passthrough():
    from transithub.config import MatrixConfig as MC
    assert build_options_kwargs(MC(drop_privileges=True))["drop_privileges"] is True
