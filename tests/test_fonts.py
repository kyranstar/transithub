from pathlib import Path

from transithub.display.fonts import BitmapFont

FIXTURE = str(Path(__file__).parent / "fixtures" / "tiny.bdf")


def test_loads_glyph():
    f = BitmapFont.load(FIXTURE)
    assert "I" in f
    assert f.height == 5


def test_text_width_uses_dwidth():
    f = BitmapFont.load(FIXTURE)
    assert f.text_width("II") == 8  # 2 * dwidth(4)


def test_iter_pixels_positions():
    f = BitmapFont.load(FIXTURE)
    pts = set(f.iter_pixels(0, 0, "I"))
    assert (0, 0) in pts and (1, 0) in pts and (2, 0) in pts
    assert (1, 1) in pts and (1, 2) in pts and (1, 3) in pts
    assert (0, 4) in pts and (2, 4) in pts
    assert (0, 1) not in pts


def test_missing_glyph_falls_back_to_default():
    f = BitmapFont.load(FIXTURE)
    assert list(f.iter_pixels(0, 0, "?"))  # uses DEFAULT_CHAR, not empty
