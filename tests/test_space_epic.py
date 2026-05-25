import json
from datetime import datetime
from pathlib import Path

from PIL import Image

from transithub.space.epic import EarthFrame, EpicClient, image_url, process

FIX = Path(__file__).parent / "fixtures"


def _meta():
    return json.loads((FIX / "epic_natural.json").read_text())


def _sample_png_bytes() -> bytes:
    return (FIX / "epic_sample.png").read_bytes()


def test_image_url_construction_from_date():
    item = {"image": "epic_1b_20260522002712", "date": "2026-05-22 00:22:24"}
    assert image_url(item) == (
        "https://epic.gsfc.nasa.gov/archive/natural/2026/05/22/png/"
        "epic_1b_20260522002712.png")


def test_process_yields_64x32_rgb_with_nonblack_disc():
    frame = process(_sample_png_bytes())
    assert frame.size == (64, 32) and frame.mode == "RGB"
    # The disc lands centered; the very center pixel must be lit (not space).
    assert frame.getpixel((32, 16)) != (0, 0, 0)
    # The corners are space -> black.
    assert frame.getpixel((0, 0)) == (0, 0, 0)
    assert frame.getpixel((63, 31)) == (0, 0, 0)
    # A meaningful number of lit pixels (a real disc, not a stray dot).
    lit = sum(1 for x in range(64) for y in range(32)
              if frame.getpixel((x, y)) != (0, 0, 0))
    assert lit > 200


def test_all_black_input_gives_black_frame():
    black = Image.new("RGB", (120, 120), (0, 0, 0))
    import io
    buf = io.BytesIO()
    black.save(buf, format="PNG")
    frame = process(buf.getvalue())
    assert frame.size == (64, 32)
    assert frame.getpixel((32, 16)) == (0, 0, 0)


def test_fetch_downloads_one_image_and_builds_frame():
    seen = {"json": 0, "img": []}

    def json_fetch(url):
        seen["json"] += 1
        return _meta()

    def img_fetch(url):
        seen["img"].append(url)
        return _sample_png_bytes()

    ef = EpicClient(json_fetcher=json_fetch, image_fetcher=img_fetch).fetch()
    assert isinstance(ef, EarthFrame)
    assert ef.base_image.size == (64, 32) and ef.base_image.mode == "RGB"
    assert ef.caption.startswith("EARTH")
    assert ef.captured == datetime(2026, 5, 22, 0, 22, 24)
    # exactly ONE image download (bandwidth discipline)
    assert seen["json"] == 1 and len(seen["img"]) == 1
    assert seen["img"][0].endswith(".png")


def test_caption_fits_panel_width():
    from transithub.display import scenery as S
    ef = EpicClient(json_fetcher=lambda u: _meta(),
                    image_fetcher=lambda u: _sample_png_bytes()).fetch()
    assert S.text_width(ef.caption) <= 64


def test_fetch_none_when_json_raises():
    def boom(url):
        raise OSError("down")
    ef = EpicClient(json_fetcher=boom, image_fetcher=lambda u: _sample_png_bytes())
    assert ef.fetch() is None


def test_fetch_none_when_image_raises():
    def boom(url):
        raise OSError("down")
    ef = EpicClient(json_fetcher=lambda u: _meta(), image_fetcher=boom)
    assert ef.fetch() is None


def test_fetch_none_on_empty_metadata():
    assert EpicClient(json_fetcher=lambda u: [],
                      image_fetcher=lambda u: _sample_png_bytes()).fetch() is None
