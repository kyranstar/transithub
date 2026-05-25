"""A glanceable problem warning — only shown when something is genuinely wrong."""
from __future__ import annotations

from PIL import Image

from .. import scenery as S
from .base import Scene

_ICON = (250, 196, 60)       # amber alert
_TEXT = (255, 238, 214)
_OUT = (38, 18, 8)
_BG = (10, 7, 6)


class HealthScene(Scene):
    duration_ms = 6000

    def __init__(self, message: str, cols: int = 64, rows: int = 32):
        self.message = message
        self.cols, self.rows = cols, rows

    def render(self, elapsed_ms: int) -> Image.Image:
        img = Image.new("RGB", (self.cols, self.rows), _BG)
        if (elapsed_ms // 500) % 2 == 0:          # slow blink draws the eye
            self._warning_triangle(img, self.cols // 2, 2, 9, 8)
        x = (self.cols - S.text_width(self.message)) // 2
        S.draw_text(img, x, 21, self.message, _TEXT, outline=_OUT)
        return img

    def _warning_triangle(self, img, cx: int, top: int, half: int, h: int) -> None:
        px = img.load()

        def put(x, y):
            if 0 <= x < self.cols and 0 <= y < self.rows:
                px[x, y] = _ICON

        for i in range(h + 1):                    # the two slanted sides
            off = int(half * i / h)
            put(cx - off, top + i)
            put(cx + off, top + i)
        for x in range(cx - half, cx + half + 1):  # the base
            put(x, top + h)
        for y in range(top + 2, top + h - 2):      # the exclamation stroke
            put(cx, y)
        put(cx, top + h - 1)                        # exclamation dot
