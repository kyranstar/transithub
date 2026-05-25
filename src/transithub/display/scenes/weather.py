from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from PIL import Image

from ...weather.model import (
    Condition, SunPhase, sun_phase, moon_phase, flags, summary,
    HOT_F, WINDY_MPH, AQI_UNHEALTHY, CLEAN_AQI,
)
from .. import scenery as S
from .base import Scene

INTRO_MS = 4000
SLIDE_MS = 7000          # leisurely cadence for the open-ended rundown
ROUND_SLIDE_MS = 3400    # snappier cadence when playing a fixed number of rounds
DIP_MS = 500
OUT = (16, 12, 28)
DIM_BG = [(0.0, (10, 12, 28)), (0.5, (34, 22, 40)), (1.0, (40, 22, 18))]
GO_BG = [(0.0, (8, 34, 26)), (0.5, (18, 70, 48)), (1.0, (30, 96, 66))]
STAY_BG = [(0.0, (40, 12, 16)), (0.5, (78, 26, 30)), (1.0, (104, 40, 36))]
AIR_BG = [(0.0, (10, 36, 52)), (0.5, (24, 78, 88)), (1.0, (40, 116, 110))]

_PAL = {
    SunPhase.SUNRISE: [(0, (30, 32, 78)), (0.5, (158, 92, 112)), (1.0, (236, 150, 92))],
    SunPhase.DAY:     [(0, (60, 116, 186)), (0.55, (118, 160, 206)), (1.0, (172, 196, 226))],
    SunPhase.SUNSET:  [(0, (46, 30, 86)), (0.5, (150, 72, 98)), (0.85, (226, 120, 72)), (1.0, (150, 72, 52))],
    SunPhase.NIGHT:   [(0, (8, 10, 30)), (0.6, (16, 18, 46)), (1.0, (28, 26, 58))],
}
_TINT = {Condition.CLEAR: (1.0, None, 0.0), Condition.CLOUDY: (0.82, (92, 94, 112), 0.18),
         Condition.FOG: (0.6, (120, 124, 134), 0.45),
         Condition.RAIN: (0.5, (44, 50, 66), 0.4), Condition.SNOW: (0.82, (130, 138, 158), 0.3)}


class WeatherScene(Scene):
    def __init__(self, weather, now: datetime, rundown_seconds=60, cols=64, rows=32,
                 trash_days=(), rounds: Optional[int] = None, lean: bool = False):
        self.w = weather
        self.now = now
        self.cols, self.rows = cols, rows
        self.lean = lean
        self.phase = sun_phase(now, weather.sunrise, weather.sunset)
        self.moon_phase = moon_phase(now)
        # When it's actively raining/snowing, every slide shares the precip scene.
        self._wet = weather.condition in (Condition.RAIN, Condition.SNOW)

        # The core is always the now/temp + forecast; lean mode stops there so a 2am
        # glance is just the essentials. The full deck adds a verbal verdict, an
        # optional clean-air beat, and the advisory/flag slides.
        self._slides = [self._now_slide, self._forecast_slide]
        if not lean:
            verdict = summary(weather, now)
            if verdict is not None:
                self._slides.append(self._summary_slide(verdict))
            if weather.aqi <= CLEAN_AQI:           # occasional clean-air positive beat
                self._slides.append(self._clean_air_slide)
            self._slides += [self._flag_slide(f) for f in flags(weather, now, list(trash_days))]
        self.slide_count = len(self._slides)

        # Cadence + total runtime. With `rounds` the scene plays exactly that many
        # full passes (snappy) and the duration is derived; otherwise it's an
        # open-ended rundown sized by `rundown_seconds` (backward compatible).
        if rounds is not None:
            self._slide_ms = ROUND_SLIDE_MS
            self.duration_ms = INTRO_MS + rounds * self.slide_count * self._slide_ms
        else:
            self._slide_ms = SLIDE_MS
            self.duration_ms = rundown_seconds * 1000

    # --- backgrounds --------------------------------------------------------
    def _scene_bg(self, frame: int) -> Image.Image:
        img = Image.new("RGB", (self.cols, self.rows), (0, 0, 0))
        sc, tint, amt = _TINT[self.w.condition]
        S.gradient(img, _PAL[self.phase], sc, tint, amt)
        cond = self.w.condition
        day = self.phase is SunPhase.DAY
        hot = max(self.w.temp, self.w.feels_like) >= HOT_F
        if cond is Condition.FOG:
            S.fog(img, frame)
            return img
        if self.phase is SunPhase.NIGHT and cond in (Condition.CLEAR, Condition.CLOUDY):
            S.stars(img, frame)
            S.moon(img, 46, 9, 5, self.moon_phase)
        elif cond in (Condition.CLEAR, Condition.CLOUDY):
            if day and hot and cond is Condition.CLEAR:   # swollen, throbbing heat sun
                S.pulsing_sun(img, 46, 11, 8, frame)
            elif day:                        # bright golden sun, high in a blue sky
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
        # One modulating overlay on top, most salient first: bad air reads as a hazy
        # orange/brown wash; otherwise strong wind streaks the sky.
        if self.w.aqi >= AQI_UNHEALTHY:
            S.haze(img, frame, (150, 96, 52))
        elif self.w.wind_mph >= WINDY_MPH:
            S.gusts(img, frame)
        return img

    def _centered(self, img, y, text, color, scale=1):
        S.draw_text(img, (self.cols - S.text_width(text, scale)) // 2, y, text, color, scale, OUT)

    def _dimbg(self) -> Image.Image:
        img = Image.new("RGB", (self.cols, self.rows), (0, 0, 0))
        S.gradient(img, DIM_BG)
        return img

    def _slide_bg(self, frame: int) -> Image.Image:
        # While precipitating, keep the (animated) rain/snow scene behind every slide.
        return S.dim(self._scene_bg(frame), 0.6) if self._wet else self._dimbg()

    # --- slides -------------------------------------------------------------
    def _now_slide(self, frame: int) -> Image.Image:
        img = S.dim(self._scene_bg(frame), 0.6)
        t = str(round(self.w.temp))
        tx = (self.cols - S.text_width(t, 2)) // 2 - 3
        S.draw_text(img, tx, 5, t, (255, 255, 255), 2, OUT)
        S.degree(img, tx + S.text_width(t, 2) + 1, 5, (255, 226, 178))
        clock = (self.now + timedelta(milliseconds=frame * 40)).strftime("%-I:%M")
        self._centered(img, 24, clock, (210, 220, 245))
        return img

    def _forecast_slide(self, frame: int) -> Image.Image:
        img = self._slide_bg(frame)
        self._centered(img, 4, "TODAY", (150, 160, 200))
        hl = f"{round(self.w.today_high)}/{round(self.w.today_low)}"
        self._centered(img, 15, hl, (255, 210, 160), scale=2)
        return img

    def _summary_slide(self, verdict: str):
        # A clean two-line verbal verdict on its own gradient: green for GO OUTSIDE,
        # warm red for STAY IN. Two short words keep each line well within 64px.
        go = verdict == "GO OUTSIDE"
        bg = GO_BG if go else STAY_BG
        words = verdict.split()
        accent = (150, 240, 170) if go else (255, 176, 150)

        def render(frame: int) -> Image.Image:
            img = Image.new("RGB", (self.cols, self.rows), (0, 0, 0))
            S.gradient(img, bg)
            self._centered(img, 6, words[0], accent)
            self._centered(img, 17, words[1], (255, 255, 255), scale=1)
            return img
        return render

    def _clean_air_slide(self, frame: int) -> Image.Image:
        # An occasional positive beat over a crisp blue/green sky.
        img = Image.new("RGB", (self.cols, self.rows), (0, 0, 0))
        S.gradient(img, AIR_BG)
        self._centered(img, 6, "GREAT", (200, 240, 230))
        self._centered(img, 17, "AIR", (255, 255, 255))
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
        slide_ms = self._slide_ms
        idx = (t // slide_ms) % self.slide_count
        within = t % slide_ms
        img = self._slides[idx](frame)
        if within < DIP_MS:
            return Image.blend(black, img, within / DIP_MS)
        if within > slide_ms - DIP_MS:
            return Image.blend(img, black, (within - (slide_ms - DIP_MS)) / DIP_MS)
        return img
