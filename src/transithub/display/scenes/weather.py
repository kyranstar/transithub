from datetime import datetime, timedelta

from PIL import Image

from ...weather.model import Condition, SunPhase, sun_phase, moon_phase, flags
from .. import scenery as S
from .base import Scene

INTRO_MS = 4000
SLIDE_MS = 7000
DIP_MS = 500
OUT = (16, 12, 28)
DIM_BG = [(0.0, (10, 12, 28)), (0.5, (34, 22, 40)), (1.0, (40, 22, 18))]

_PAL = {
    SunPhase.SUNRISE: [(0, (30, 32, 78)), (0.5, (158, 92, 112)), (1.0, (236, 150, 92))],
    SunPhase.DAY:     [(0, (60, 116, 186)), (0.55, (118, 160, 206)), (1.0, (172, 196, 226))],
    SunPhase.SUNSET:  [(0, (46, 30, 86)), (0.5, (150, 72, 98)), (0.85, (226, 120, 72)), (1.0, (150, 72, 52))],
    SunPhase.NIGHT:   [(0, (8, 10, 30)), (0.6, (16, 18, 46)), (1.0, (28, 26, 58))],
}
_TINT = {Condition.CLEAR: (1.0, None, 0.0), Condition.CLOUDY: (0.82, (92, 94, 112), 0.18),
         Condition.RAIN: (0.5, (44, 50, 66), 0.4), Condition.SNOW: (0.82, (130, 138, 158), 0.3)}


class WeatherScene(Scene):
    def __init__(self, weather, now: datetime, rundown_seconds=60, cols=64, rows=32, trash_days=()):
        self.w = weather
        self.now = now
        self.cols, self.rows = cols, rows
        self.duration_ms = rundown_seconds * 1000
        self.phase = sun_phase(now, weather.sunrise, weather.sunset)
        self.moon_phase = moon_phase(now)
        # When it's actively raining/snowing, every slide shares the precip scene.
        self._wet = weather.condition in (Condition.RAIN, Condition.SNOW)
        self._flags = flags(weather, now, list(trash_days))
        self._slides = [self._now_slide, self._forecast_slide]
        self._slides += [self._flag_slide(f) for f in self._flags]
        self.slide_count = len(self._slides)

    def _scene_bg(self, frame: int) -> Image.Image:
        img = Image.new("RGB", (self.cols, self.rows), (0, 0, 0))
        sc, tint, amt = _TINT[self.w.condition]
        S.gradient(img, _PAL[self.phase], sc, tint, amt)
        cond = self.w.condition
        if self.phase is SunPhase.NIGHT and cond in (Condition.CLEAR, Condition.CLOUDY):
            S.stars(img, frame)
            S.moon(img, 46, 9, 5, self.moon_phase)
        elif cond in (Condition.CLEAR, Condition.CLOUDY):
            if self.phase is SunPhase.DAY:   # bright golden sun, high in a blue sky
                S.glow_sun(img, 46, 11, 8, color=(255, 210, 96), intensity=1.0)
            else:                            # sunrise / sunset — low, warm sun
                S.glow_sun(img, 16, 22, 7, intensity=0.95)
        if cond is Condition.CLOUDY:
            S.cloud(img, (20 + frame) % (self.cols + 30) - 8, 9, 22, (150, 156, 178), 0.7)
        elif cond is Condition.RAIN:
            S.cloud(img, 18, 7, 26, (96, 100, 122), 0.85)
            S.rain(img, frame)
        elif cond is Condition.SNOW:
            S.cloud(img, 18, 7, 24, (176, 182, 202), 0.8)
            S.snow(img, frame)
        return img

    def _centered(self, img, y, text, color, scale=1):
        S.draw_text(img, (self.cols - S.text_width(text, scale)) // 2, y, text, color, scale, OUT)

    def _now_slide(self, frame: int) -> Image.Image:
        img = S.dim(self._scene_bg(frame), 0.6)
        t = str(round(self.w.temp))
        tx = (self.cols - S.text_width(t, 2)) // 2 - 3
        S.draw_text(img, tx, 5, t, (255, 255, 255), 2, OUT)
        S.degree(img, tx + S.text_width(t, 2) + 1, 5, (255, 226, 178))
        clock = (self.now + timedelta(milliseconds=frame * 40)).strftime("%-I:%M")
        self._centered(img, 24, clock, (210, 220, 245))
        return img

    def _dimbg(self) -> Image.Image:
        img = Image.new("RGB", (self.cols, self.rows), (0, 0, 0))
        S.gradient(img, DIM_BG)
        return img

    def _slide_bg(self, frame: int) -> Image.Image:
        # While precipitating, keep the (animated) rain/snow scene behind every slide.
        return S.dim(self._scene_bg(frame), 0.6) if self._wet else self._dimbg()

    def _forecast_slide(self, frame: int) -> Image.Image:
        img = self._slide_bg(frame)
        self._centered(img, 4, "TODAY", (150, 160, 200))
        hl = f"{round(self.w.today_high)}/{round(self.w.today_low)}"
        self._centered(img, 15, hl, (255, 210, 160), scale=2)
        return img

    def _flag_slide(self, flag):
        def render(frame: int) -> Image.Image:
            img = self._slide_bg(frame)
            if flag.detail:
                self._centered(img, 7, flag.headline, (255, 170, 60))
                self._centered(img, 18, flag.detail, (255, 235, 200))
            else:
                self._centered(img, 12, flag.headline, (255, 170, 60))
            return img
        return render

    def render(self, elapsed_ms: int) -> Image.Image:
        frame = elapsed_ms // 100
        black = Image.new("RGB", (self.cols, self.rows), (0, 0, 0))
        if elapsed_ms < INTRO_MS:
            fade = min(1.0, elapsed_ms / 1200)
            return Image.blend(black, self._scene_bg(frame), fade)
        t = elapsed_ms - INTRO_MS
        idx = (t // SLIDE_MS) % self.slide_count
        within = t % SLIDE_MS
        img = self._slides[idx](frame)
        if within < DIP_MS:
            return Image.blend(black, img, within / DIP_MS)
        if within > SLIDE_MS - DIP_MS:
            return Image.blend(img, black, (within - (SLIDE_MS - DIP_MS)) / DIP_MS)
        return img
