from transithub.display.bullets import line_color, make_bullet, LINE_COLORS


def test_known_line_colors():
    assert line_color("L") == LINE_COLORS["L"]
    assert line_color("M") == (0xFF, 0x63, 0x19)


def test_unknown_line_defaults_gray():
    assert line_color("ZZ") == (0x80, 0x80, 0x80)


def test_make_bullet_size_and_fill():
    img = make_bullet("M", 15)
    assert img.size == (15, 15)
    # a pixel inside the circle but left of the centered letter is the line color
    fill = img.getpixel((2, 7))
    assert fill[:3] == (0xFF, 0x63, 0x19) and fill[3] == 255
    assert img.getpixel((0, 0))[3] == 0  # corner transparent


def test_make_bullet_has_white_letter_pixels():
    img = make_bullet("M", 15)
    whites = sum(1 for y in range(15) for x in range(15)
                 if img.getpixel((x, y))[:3] == (255, 255, 255))
    assert whites > 0
