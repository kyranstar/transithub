from transithub.display import scenery as S
from transithub.display.scenes.alert import AlertScene, AlertSource
from transithub.mta.alerts import LineAlert

_RED = (240, 60, 40)


def test_scene_size_duration_mode():
    s = AlertScene(LineAlert("L", "DLY", "SIGNALS"))
    assert s.duration_ms == 8000
    img = s.render(0)
    assert img.size == (64, 32) and img.mode == "RGB"


def test_scene_renders_status_and_reason_pixels():
    # Both the status word and the reason occupy distinct vertical bands.
    img = AlertScene(LineAlert("M", "DLY", "SIGNALS")).render(0)
    status_band = any(img.getpixel((x, y)) != (10, 7, 6)
                      for x in range(64) for y in range(16, 24))
    reason_band = any(img.getpixel((x, y)) != (10, 7, 6)
                      for x in range(64) for y in range(24, 32))
    assert status_band and reason_band


def test_scene_no_reason_leaves_bottom_row_clear():
    img = AlertScene(LineAlert("N", "DLY", "")).render(2000)
    assert all(img.getpixel((x, y)) == (10, 7, 6)
               for x in range(64) for y in range(24, 32))


def test_suspended_uses_red_and_flashes():
    # Severity color is red, and the urgent pulse changes brightness over time.
    on = AlertScene(LineAlert("C", "SUSP", "")).render(0)
    assert any(on.getpixel((x, y)) == _RED for x in range(64) for y in range(32))
    # A frame in the "off" half of the flash is dimmer somewhere on the status word.
    off = AlertScene(LineAlert("C", "SUSP", "")).render(300)
    on_lit = sum(1 for x in range(64) for y in range(16, 24)
                 if on.getpixel((x, y)) != (10, 7, 6))
    off_lit = sum(1 for x in range(64) for y in range(16, 24)
                  if off.getpixel((x, y)) == _RED)
    # full-red pixels in the off frame are fewer than lit pixels in the on frame
    assert off_lit < on_lit


def test_status_words_fit_panel_width():
    for tag, word in (("DLY", "DELAYED"), ("RDCD", "REDUCED"), ("SUSP", "SUSPENDED")):
        assert S.text_width(word) <= 64
    # The widest reason we emit must also fit.
    for reason in ("MECHANICAL", "TRACK WORK", "STALLED TRN", "SICK PASS"):
        assert S.text_width(reason) <= 64


def test_status_word_per_tag():
    assert AlertScene(LineAlert("L", "DLY", ""))._status == "DELAYED"
    assert AlertScene(LineAlert("L", "RDCD", ""))._status == "REDUCED"
    assert AlertScene(LineAlert("L", "SUSP", ""))._status == "SUSPENDED"


# -- AlertSource -----------------------------------------------------------

def test_source_none_when_no_disruption():
    src = AlertSource(provider=lambda: [None, None])
    assert src.poll(ctx=None) is None
    assert AlertSource(provider=lambda: [])._candidates() == []


def test_source_returns_scene_for_disrupted_line():
    src = AlertSource(provider=lambda: [None, LineAlert("M", "DLY", "SIGNALS")])
    scene = src.poll(ctx=None)
    assert isinstance(scene, AlertScene)
    assert scene.alert.line == "M" and scene.alert.reason == "SIGNALS"


def test_source_prefers_most_severe():
    src = AlertSource(provider=lambda: [LineAlert("L", "DLY", ""),
                                        LineAlert("M", "SUSP", "")])
    scene = src.poll(ctx=None)
    assert scene.alert.line == "M" and scene.alert.tag == "SUSP"


def test_source_rotates_among_equal_severity():
    alerts = [LineAlert("L", "DLY", "SIGNALS"), LineAlert("M", "DLY", "FDNY")]
    src = AlertSource(provider=lambda: list(alerts))
    lines = [src.poll(ctx=None).alert.line for _ in range(4)]
    assert lines == ["L", "M", "L", "M"]


def test_source_dedupes_by_line():
    # Same line disrupted at two tracked stops -> one candidate, no rotation churn.
    src = AlertSource(provider=lambda: [LineAlert("L", "DLY", "SIGNALS"),
                                        LineAlert("L", "DLY", "SIGNALS")])
    assert len(src._candidates()) == 1
    assert src.poll(ctx=None).alert.line == "L"
