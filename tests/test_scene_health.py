from transithub.display.scenes.health import HealthScene


def test_size_and_mode():
    img = HealthScene("OFFLINE").render(0)
    assert img.size == (64, 32) and img.mode == "RGB"


def test_draws_amber_icon_and_text():
    img = HealthScene("OFFLINE").render(0)
    assert any(img.getpixel((x, y)) == (250, 196, 60) for x in range(64) for y in range(32))
    assert any(img.getpixel((x, y)) == (255, 238, 214) for x in range(64) for y in range(32))


def test_duration():
    assert HealthScene("X").duration_ms == 6000
