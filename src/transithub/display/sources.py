"""Built-in scene sources and the Director factory.

Each feature contributes a `SceneSource` (here or in its own module) wired into a
`Slot` by `build_director`. Keeping the wiring in one place makes the whole
schedule — priorities, cadences, day parts — readable at a glance."""
from __future__ import annotations

from datetime import timedelta
from typing import Callable, Optional

from .director import Context
from .scenes.base import Scene
from .scenes.health import HealthScene


class HealthSource:
    """Surfaces the most severe active health warning, or nothing."""
    name = "health"

    def __init__(self, cols: int = 64, rows: int = 32):
        self.cols, self.rows = cols, rows

    def poll(self, ctx: Context) -> Optional[Scene]:
        if ctx.health:
            return HealthScene(ctx.health[0], self.cols, self.rows)
        return None


class WeatherRundownSource:
    """The animated weather rundown; the Director's cooldown sets its cadence."""
    name = "weather"

    def __init__(self, make_scene: Callable):
        self._make = make_scene

    def poll(self, ctx: Context) -> Optional[Scene]:
        if ctx.weather is None:
            return None
        return self._make(ctx.weather, ctx.now)


class SunEventSource:
    """Sunrise/sunset notice, fired once each per day within its window."""
    name = "sun"

    def __init__(self, make_scene: Callable, sunrise_enabled: bool = True,
                 sunset_enabled: bool = True):
        self._make = make_scene
        self._sunrise = sunrise_enabled
        self._sunset = sunset_enabled
        self._fired: set = set()

    def poll(self, ctx: Context) -> Optional[Scene]:
        w = ctx.weather
        if w is None:
            return None
        for enabled, kind, event in (
            (self._sunrise, "sunrise", w.sunrise),
            (self._sunset, "sunset", w.sunset),
        ):
            if not enabled:
                continue
            open_t = event - timedelta(minutes=30 if kind == "sunrise" else 45)
            close_t = event + timedelta(minutes=30 if kind == "sunrise" else 10)
            key = (kind, ctx.now.date())
            if open_t <= ctx.now <= close_t and key not in self._fired:
                self._fired.add(key)
                return self._make(kind, event)
        return None
