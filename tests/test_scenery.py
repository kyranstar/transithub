from PIL import Image

from transithub.display import scenery as S


def _img():
    return Image.new("RGB", (64, 32), (0, 0, 0))


def test_gradient_fills_rows_differently():
    img = _img()
    S.gradient(img, [(0.0, (0, 0, 0)), (1.0, (200, 100, 50))])
    assert img.getpixel((0, 0)) != img.getpixel((0, 31))


def test_text_width_and_draw():
    img = _img()
    assert S.text_width("54", scale=2) == S.text_width("54", scale=1) * 2
    S.draw_text(img, 0, 0, "5", (255, 255, 255), scale=1)
    assert any(img.getpixel((x, y)) == (255, 255, 255) for x in range(6) for y in range(8))


def test_outline_adds_dark_pixels():
    img = _img()
    S.draw_text(img, 5, 5, "5", (255, 255, 255), scale=1, outline=(20, 20, 20))
    assert any(img.getpixel((x, y)) == (20, 20, 20) for x in range(12) for y in range(12))


def test_glow_sun_lights_center():
    img = _img()
    S.glow_sun(img, 32, 16, 6, color=(255, 220, 160))
    assert img.getpixel((32, 16)) == (255, 220, 160)


def test_dim_darkens():
    img = Image.new("RGB", (4, 4), (200, 200, 200))
    assert S.dim(img, 0.5).getpixel((0, 0)) == (100, 100, 100)


# --- moon phases ---

CX, CY, R = 32, 16, 6


def _lit_sides(phase):
    """(# of non-black pixels left of center, # right of center) for a moon."""
    img = _img()
    S.moon(img, CX, CY, R, phase)
    left = sum(img.getpixel((x, y)) != (0, 0, 0) for x in range(CX) for y in range(32))
    right = sum(img.getpixel((x, y)) != (0, 0, 0) for x in range(CX, 64) for y in range(32))
    return left, right


def test_moon_waxing_crescent_lights_right():
    left, right = _lit_sides(0.10)          # waxing crescent -> sunlit on the right
    assert right > left * 3


def test_moon_waning_crescent_lights_left():
    left, right = _lit_sides(0.90)          # waning crescent -> sunlit on the left
    assert left > right * 3


def test_moon_full_lights_whole_disc():
    img = _img()
    S.moon(img, CX, CY, R, 0.5)
    assert img.getpixel((CX, CY)) != (0, 0, 0)            # center lit
    assert img.getpixel((CX - R + 1, CY)) != (0, 0, 0)    # left limb lit
    assert img.getpixel((CX + R - 1, CY)) != (0, 0, 0)    # right limb lit


def test_moon_new_draws_nothing():
    img = _img()
    S.moon(img, CX, CY, R, 0.0)             # new moon is invisible -> no pixels, no stray glow
    assert img.tobytes() == _img().tobytes()


# --- weather hero primitives ---

def _nonblack(img):
    return sum(img.getpixel((x, y)) != (0, 0, 0) for x in range(64) for y in range(32))


def test_fog_draws_pixels_and_drifts():
    a, b = _img(), _img()
    S.fog(a, 0)
    S.fog(b, 12)
    assert _nonblack(a) > 0
    assert a.tobytes() != b.tobytes()       # the bank drifts between frames


def test_pulsing_sun_lights_center_and_breathes():
    a, b = _img(), _img()
    S.pulsing_sun(a, 32, 16, 6, 0)
    S.pulsing_sun(b, 32, 16, 6, 18)         # roughly anti-phase
    assert a.getpixel((32, 16)) != (0, 0, 0)
    assert a.tobytes() != b.tobytes()       # the glow pulses over time


def test_gusts_draw_streaks_that_move():
    a, b = _img(), _img()
    S.gusts(a, 0)
    S.gusts(b, 7)
    assert _nonblack(a) > 0
    assert a.tobytes() != b.tobytes()       # streaks travel across the panel


def test_gusts_stay_in_bounds():
    img = _img()
    for f in range(0, 40):
        S.gusts(img, f)                     # must never index outside the panel
    assert img.size == (64, 32)


def test_haze_tints_without_clearing():
    img = _img()
    S.gradient(img, [(0.0, (20, 20, 20)), (1.0, (60, 60, 60))])
    before = img.getpixel((10, 10))
    S.haze(img, 0, (200, 120, 60), 0.4)
    after = img.getpixel((10, 10))
    assert after != before                  # the wash shifts existing pixels toward the tint
    assert after != (0, 0, 0)               # it never blacks out the scene
