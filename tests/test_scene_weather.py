from datetime import datetime

from transithub.weather.model import Weather, Condition
from transithub.display.scenes.weather import WeatherScene, INTRO_MS, ROUND_SLIDE_MS

NOW = datetime(2026, 5, 23, 14, 0)


def _w(**kw):
    base = dict(temp=54.0, feels_like=51.0, condition=Condition.CLOUDY, today_high=58.0,
                today_low=41.0, precip_prob=10, uv_index=2.0, aqi=40,
                sunrise=datetime(2026, 5, 23, 5, 31), sunset=datetime(2026, 5, 23, 20, 13))
    base.update(kw)
    return Weather(**base)


def _scene(w, secs=60, **kw):
    return WeatherScene(w, NOW, rundown_seconds=secs, cols=64, rows=32, trash_days=[], **kw)


def test_duration_and_size():
    s = _scene(_w())
    assert s.duration_ms == 60_000
    assert s.render(0).size == (64, 32) and s.render(50_000).mode == "RGB"


def test_calm_day_has_core_plus_clean_air():
    # cloudy, mild, aqi 40 -> now + forecast + a "great air" beat (no verdict/flags)
    assert _scene(_w()).slide_count == 3


def test_high_uv_adds_a_flag_slide():
    assert _scene(_w(uv_index=9.0)).slide_count == 4  # +1 over the calm-day baseline


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


# --- fog (the crash that prompted this feature) -----------------------------
def test_fog_renders_without_crashing():
    # WMO 45/48 -> Condition.FOG must not KeyError in _TINT / _scene_bg
    s = _scene(_w(condition=Condition.FOG))
    assert s._scene_bg(3).size == (64, 32)
    img = s.render(5000)                      # full render path, past intro
    assert img.size == (64, 32) and img.mode == "RGB"


def test_fog_background_differs_from_clear():
    fog = _scene(_w(condition=Condition.FOG))._scene_bg(3)
    clear = _scene(_w(condition=Condition.CLEAR))._scene_bg(3)
    assert fog.tobytes() != clear.tobytes()


# --- condition heroes -------------------------------------------------------
def _hot_day(**kw):
    # midday, clear, scorching -> the pulsing-sun hero
    return WeatherScene(_w(condition=Condition.CLEAR, temp=96.0, feels_like=99.0, **kw),
                        NOW, rundown_seconds=60, cols=64, rows=32, trash_days=[])


def test_hot_day_scene_renders_and_differs_from_mild():
    hot = _hot_day()._scene_bg(2)
    mild = WeatherScene(_w(condition=Condition.CLEAR, temp=68.0, feels_like=66.0),
                        NOW, rundown_seconds=60, cols=64, rows=32, trash_days=[])._scene_bg(2)
    assert hot.size == (64, 32)
    assert hot.tobytes() != mild.tobytes()    # pulsing sun replaces the static sun


def test_windy_overlay_changes_the_sky():
    calm = _scene(_w(condition=Condition.CLEAR, wind_mph=4.0))._scene_bg(5)
    windy = _scene(_w(condition=Condition.CLEAR, wind_mph=30.0))._scene_bg(5)
    assert calm.tobytes() != windy.tobytes()


def test_bad_aqi_hazes_the_sky():
    clean = _scene(_w(condition=Condition.CLEAR, aqi=30))._scene_bg(5)
    smoky = _scene(_w(condition=Condition.CLEAR, aqi=160))._scene_bg(5)
    assert clean.tobytes() != smoky.tobytes()


# --- verbal summary slide ---------------------------------------------------
def _slide_at(scene, idx):
    """Render the middle of slide `idx` (past intro, clear of the dip fades)."""
    t = INTRO_MS + idx * scene._slide_ms + scene._slide_ms // 2
    return scene.render(t)


def test_stay_in_summary_slide_present():
    # scorching feels-like -> STAY IN verdict gets its own slide right after the core
    s = _hot_day()                       # [now, forecast, STAY IN, great-air]
    assert s.slide_count == 4
    img = _slide_at(s, 2)                # the verdict slide
    r, g, b = img.getpixel((1, 31))      # STAY_BG bottom is warm: red dominates
    assert r > b and r > g


def test_nice_day_yields_go_outside_slide():
    # Hold everything constant except one lever: a moderate 18mph breeze is too
    # gusty for "GO OUTSIDE" yet below the STAY-IN wind cutoff -> no verdict. So the
    # only difference between the decks is the GO OUTSIDE slide itself.
    common = dict(condition=Condition.CLEAR, temp=68.0, feels_like=66.0,
                  aqi=30, uv_index=4.0, precip_prob=5)
    nice = _scene(_w(wind_mph=6.0, **common))
    breezy = _scene(_w(wind_mph=18.0, **common))
    assert nice.slide_count == breezy.slide_count + 1


def test_no_summary_slide_for_unremarkable_day():
    # mild but not "lovely" (aqi 60 > clean) and not punishing -> no verdict slide
    plain = _scene(_w(condition=Condition.CLEAR, temp=84.0, feels_like=84.0,
                      aqi=60, uv_index=4.0, wind_mph=6.0, precip_prob=5))
    # only now + forecast (aqi 60 also skips clean-air)
    assert plain.slide_count == 2


# --- rounds cadence ---------------------------------------------------------
def test_rounds_derives_duration():
    s = _scene(_w(uv_index=9.0), rounds=2)
    assert s._slide_ms == ROUND_SLIDE_MS
    assert s.duration_ms == INTRO_MS + 2 * s.slide_count * ROUND_SLIDE_MS


def test_rounds_none_keeps_rundown_duration():
    s = _scene(_w(), secs=45)               # no rounds -> backward-compatible
    assert s.duration_ms == 45_000


# --- lean (night) mode ------------------------------------------------------
def test_lean_drops_advisory_and_extra_slides():
    # humid + high UV would add WINDOWS + UV flags and a verdict; lean keeps only core
    w = _w(condition=Condition.CLEAR, humidity=90, uv_index=9.0, aqi=30,
           temp=96.0, feels_like=99.0)
    full = _scene(w)
    lean = _scene(w, lean=True)
    assert lean.slide_count == 2            # just now + forecast
    assert full.slide_count > lean.slide_count


def test_lean_still_shows_temp():
    lean = _scene(_w(), lean=True)
    img = lean.render(5000)
    assert any(img.getpixel((x, y)) == (255, 255, 255)
               for x in range(64) for y in range(32))
