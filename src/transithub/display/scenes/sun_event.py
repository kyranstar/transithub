from datetime import datetime

from PIL import Image

from .. import scenery as S
from .base import Scene

OUT = (10, 8, 24)
_PAL = [(0.0, (38, 28, 78)), (0.45, (120, 64, 96)), (0.8, (214, 120, 70)), (1.0, (196, 96, 52))]


class SunEventScene(Scene):
    duration_ms = 10_000

    def __init__(self, kind: str, event_time: datetime, cols=64, rows=32):
        self.kind = kind                       # "sunrise" or "sunset"
        self.event_time = event_time
        self.cols, self.rows = cols, rows

    def render(self, elapsed_ms: int) -> Image.Image:
        img = Image.new("RGB", (self.cols, self.rows), (0, 0, 0))
        S.gradient(img, _PAL)
        p = min(1.0, elapsed_ms / self.duration_ms)
        sy = int(21 - 13 * p) if self.kind == "sunrise" else int(8 + 13 * p)
        S.glow_sun(img, self.cols // 2, sy, 6, color=(255, 196, 120), intensity=1.0)
        px = img.load()
        for y in range(21, self.rows):
            for x in range(self.cols):
                px[x, y] = (18, 14, 40)
        label = "SUNRISE" if self.kind == "sunrise" else "SUNSET"
        S.draw_text(img, 3, 24, label, (240, 214, 178), outline=OUT)
        t = self.event_time.strftime("%-I:%M")
        S.draw_text(img, self.cols - S.text_width(t) - 2, 24, t, (250, 250, 255), outline=OUT)
        return img
