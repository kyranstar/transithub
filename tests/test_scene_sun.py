from datetime import datetime

from transithub.display.scenes.sun_event import SunEventScene


def test_sun_scene_size_and_duration():
    s = SunEventScene("sunset", datetime(2026, 5, 23, 20, 13), cols=64, rows=32)
    assert s.duration_ms == 10_000
    img = s.render(2000)
    assert img.size == (64, 32)
    # the dark band at the bottom holds text -> some bright pixels in the lower rows
    assert any(img.getpixel((x, y))[0] > 180 for x in range(64) for y in range(23, 32))
