from datetime import datetime

from transithub.weather.model import Weather, Condition
from transithub.display.scenes.weather import WeatherScene

NOW = datetime(2026, 5, 23, 14, 0)


def _w(**kw):
    base = dict(temp=54.0, feels_like=51.0, condition=Condition.CLOUDY, today_high=58.0,
                today_low=41.0, precip_prob=10, uv_index=2.0, aqi=40,
                sunrise=datetime(2026, 5, 23, 5, 31), sunset=datetime(2026, 5, 23, 20, 13))
    base.update(kw)
    return Weather(**base)


def _scene(w, secs=60):
    return WeatherScene(w, NOW, rundown_seconds=secs, cols=64, rows=32, trash_days=[])


def test_duration_and_size():
    s = _scene(_w())
    assert s.duration_ms == 60_000
    assert s.render(0).size == (64, 32) and s.render(50_000).mode == "RGB"


def test_calm_day_has_two_slides_no_flags():
    assert _scene(_w()).slide_count == 2


def test_high_uv_adds_a_flag_slide():
    assert _scene(_w(uv_index=9.0)).slide_count == 3


def test_now_slide_shows_temp_pixels():
    s = _scene(_w())
    img = s.render(5000)               # past the intro, on the Now slide
    assert any(img.getpixel((x, y)) == (255, 255, 255)
               for x in range(64) for y in range(32))


def test_wet_carries_scene_background_to_forecast_slide():
    # the forecast slide of a rainy rundown uses the rain scene, not the plain dim bg
    forecast_tick = 4000 + 7000 + 1500       # past intro + Now, mid Forecast slide
    rain = _scene(_w(condition=Condition.RAIN)).render(forecast_tick)
    dry = _scene(_w(condition=Condition.CLOUDY)).render(forecast_tick)
    assert rain.tobytes() != dry.tobytes()   # backgrounds differ -> rain scene carried over


def _night(now, **kw):
    return WeatherScene(_w(condition=Condition.CLEAR, **kw), now,
                        rundown_seconds=60, cols=64, rows=32, trash_days=[])


def test_clear_night_draws_the_moon():
    # waxing gibbous night -> moon pixels in the top-right corner
    img = _night(datetime(2026, 5, 24, 23, 0))._scene_bg(0)
    assert any(img.getpixel((x, y)) == (220, 226, 246)
               for x in range(40, 56) for y in range(0, 16))


def test_moon_phase_varies_the_scene():
    # a new-moon night (no moon) differs from a gibbous night (moon shown)
    new = _night(datetime(2026, 5, 16, 23, 0))._scene_bg(0)
    gibbous = _night(datetime(2026, 5, 24, 23, 0))._scene_bg(0)
    assert new.tobytes() != gibbous.tobytes()
