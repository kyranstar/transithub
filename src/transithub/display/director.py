from datetime import datetime, timedelta
from typing import Callable


class Director:
    """Chooses the active scene each frame: trains by default, preempted by the
    weather rundown (on a cadence) and sunrise/sunset notifications (once per day)."""

    def __init__(self, train_scene, weather_provider: Callable[[], object],
                 make_weather_scene: Callable, make_sun_scene: Callable,
                 rundown_every_minutes: int = 15, weather_enabled: bool = True,
                 sunrise_enabled: bool = True, sunset_enabled: bool = True):
        self._train = train_scene
        self._weather_provider = weather_provider
        self._make_weather = make_weather_scene
        self._make_sun = make_sun_scene
        self._interval_ms = rundown_every_minutes * 60_000
        self._weather_enabled = weather_enabled
        self._sunrise_enabled = sunrise_enabled
        self._sunset_enabled = sunset_enabled

        self._active = train_scene
        self._active_start = 0
        self._last_rundown = -self._interval_ms + 30_000   # first rundown ~30s after boot
        self._fired = set()                                # {(event, date)}

    def _start(self, scene, mono_ms):
        self._active = scene
        self._active_start = mono_ms

    def _due_sun(self, now: datetime, weather):
        if weather is None:
            return None
        for enabled, kind, event in ((self._sunrise_enabled, "sunrise", weather.sunrise),
                                     (self._sunset_enabled, "sunset", weather.sunset)):
            if not enabled:
                continue
            open_t = event - timedelta(minutes=30 if kind == "sunrise" else 45)
            close_t = event + timedelta(minutes=30 if kind == "sunrise" else 10)
            key = (kind, now.date())
            if open_t <= now <= close_t and key not in self._fired:
                self._fired.add(key)
                return self._make_sun(kind, event)
        return None

    def render(self, now: datetime, mono_ms: int):
        # 1) finish an in-progress finite scene
        if self._active.duration_ms is not None:
            if mono_ms - self._active_start >= self._active.duration_ms:
                self._start(self._train, mono_ms)
            else:
                return self._active.render(mono_ms - self._active_start)

        # 2) only trigger new scenes from the default (train) state
        if self._active is self._train:
            weather = self._weather_provider()
            sun = self._due_sun(now, weather)
            if sun is not None:
                self._start(sun, mono_ms)
                return sun.render(0)
            if (self._weather_enabled and weather is not None
                    and mono_ms - self._last_rundown >= self._interval_ms):
                self._last_rundown = mono_ms
                ws = self._make_weather(weather, now)
                self._start(ws, mono_ms)
                return ws.render(0)

        return self._active.render(mono_ms - self._active_start)
