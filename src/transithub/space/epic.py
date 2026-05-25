"""A recent picture of the whole Earth, from a million miles out.

NASA's EPIC camera on DSCOVR shoots the full sunlit disc several times a day and
publishes it keyless. We grab the metadata, download ONE recent frame, crop it to
the disc, shrink it so Earth is a ~28px ball on a 64x32 panel, and nudge the
colour for the LED look. The processed frame is cached on the snapshot so render
is cheap and we fetch at most once per poll (the coordinator polls ~hourly).
"""
from __future__ import annotations

import io
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional, Tuple

from PIL import Image, ImageEnhance

META_URL = "https://epic.gsfc.nasa.gov/api/natural"
# archive/natural/YYYY/MM/DD/png/<image>.png — date parts come from the item.
_ARCHIVE = "https://epic.gsfc.nasa.gov/archive/natural/{y}/{m}/{d}/png/{image}.png"

COLS, ROWS = 64, 32
DISC_PX = 28          # target Earth diameter on the panel
_BLACK = (0, 0, 0)


@dataclass(frozen=True)
class EarthFrame:
    """A ready-to-show Earth: the composed 64x32 RGB image plus a short caption."""
    base_image: Image.Image      # 64x32 RGB, disc centered on black
    caption: str                 # e.g. "EARTH 8:22PM" or "EARTH 19N"
    captured: Optional[datetime] = None


def _default_json_fetch(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "transithub"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        import json
        return json.loads(resp.read().decode("utf-8"))


def _default_image_fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "transithub"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def image_url(item: dict) -> str:
    """Build the PNG archive URL for an EPIC metadata item."""
    name = item["image"]
    when = _parse_date(item.get("date", ""))
    if when is None:
        raise ValueError(f"EPIC item {name!r} has no usable date")
    return _ARCHIVE.format(y=f"{when.year:04d}", m=f"{when.month:02d}",
                           d=f"{when.day:02d}", image=name)


def _parse_date(text: str) -> Optional[datetime]:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _disc_bbox(img: Image.Image, thresh: int = 24) -> Optional[Tuple[int, int, int, int]]:
    """Bounding box of the lit Earth disc (non-space pixels), or None if all black."""
    gray = img.convert("L")
    # Pillow's point-thresholded getbbox finds the lit region cheaply.
    mask = gray.point(lambda v: 255 if v > thresh else 0)
    return mask.getbbox()


def _square(bbox: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
    x0, y0, x1, y1 = bbox
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    half = max(x1 - x0, y1 - y0) / 2.0
    return (int(cx - half), int(cy - half), int(cx + half), int(cy + half))


def process(raw: bytes, cols: int = COLS, rows: int = ROWS,
            disc_px: int = DISC_PX) -> Image.Image:
    """Crop to the disc, downscale to a ~`disc_px` ball, colour-grade, center on black.

    Color-grading is deliberately modest — a small saturation and contrast lift so
    the blues and cloud whites read on a dim LED panel without looking cartoonish.
    """
    src = Image.open(io.BytesIO(raw)).convert("RGB")
    bbox = _disc_bbox(src)
    if bbox is None:                       # nothing lit -> just a black frame
        return Image.new("RGB", (cols, rows), _BLACK)
    sq = _square(bbox)
    disc = src.crop(sq)
    disc = disc.resize((disc_px, disc_px), Image.LANCZOS)
    disc = ImageEnhance.Color(disc).enhance(1.35)      # modest saturation lift
    disc = ImageEnhance.Contrast(disc).enhance(1.12)   # gentle contrast
    disc = ImageEnhance.Brightness(disc).enhance(1.08)
    frame = Image.new("RGB", (cols, rows), _BLACK)
    frame.paste(disc, ((cols - disc_px) // 2, (rows - disc_px) // 2))
    return frame


def _caption(item: dict, when: Optional[datetime]) -> str:
    """A short caption that fits: 'EARTH' + capture time, falling back to a region."""
    if when is not None:
        return "EARTH " + when.strftime("%-I:%M%p").replace("AM", "A").replace("PM", "P")
    cc = item.get("centroid_coordinates") or {}
    lat = cc.get("lat")
    if isinstance(lat, (int, float)):
        hemi = "N" if lat >= 0 else "S"
        return f"EARTH {abs(int(round(lat)))}{hemi}"
    return "EARTH"


class EpicClient:
    """Fetches and processes one recent EPIC Earth image (no API key).

    Two injectable fetchers keep tests offline: `json_fetcher(url)->list` for the
    metadata array and `image_fetcher(url)->bytes` for the PNG.
    """

    def __init__(self,
                 json_fetcher: Callable[[str], list] = _default_json_fetch,
                 image_fetcher: Callable[[str], bytes] = _default_image_fetch,
                 cols: int = COLS, rows: int = ROWS, disc_px: int = DISC_PX):
        self._json = json_fetcher
        self._image = image_fetcher
        self.cols, self.rows, self.disc_px = cols, rows, disc_px

    def fetch(self) -> Optional[EarthFrame]:
        try:
            meta = self._json(META_URL)
        except Exception:
            return None
        if not isinstance(meta, list) or not meta:
            return None
        item = meta[0]                      # the most recent capture
        when = _parse_date(item.get("date", ""))
        try:
            raw = self._image(image_url(item))
            frame = process(raw, self.cols, self.rows, self.disc_px)
        except Exception:
            return None
        return EarthFrame(base_image=frame, caption=_caption(item, when), captured=when)
