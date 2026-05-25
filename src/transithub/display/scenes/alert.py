"""A full-screen beat for a disrupted tracked line: bullet + status + reason.

One concept per screen. If several lines are disrupted, the source rotates which
one it shows per play rather than cramming them together. The motion is keyed to
severity: delays get a gentle pulse, suspensions a subtle urgent flash/shake."""
from __future__ import annotations

import math
from typing import Callable, List, Optional, Sequence

from PIL import Image

from ...mta.alerts import LineAlert
from .. import scenery as S
from ..bullets import make_bullet
from .base import Scene

# tag -> the spelled-out status word shown under the bullet.
_STATUS = {"DLY": "DELAYED", "RDCD": "REDUCED", "SUSP": "SUSPENDED"}
_STATUS_COLOR = {
    "DLY": (255, 176, 48),    # amber
    "RDCD": (255, 176, 48),
    "SUSP": (240, 60, 40),    # red — most urgent
}
_REASON_COLOR = (236, 224, 196)
_OUT = (10, 8, 6)
_BG = (10, 7, 6)
_BULLET_D = 15


class AlertScene(Scene):
    duration_ms = 8000

    def __init__(self, alert: LineAlert, cols: int = 64, rows: int = 32):
        self.alert = alert
        self.cols, self.rows = cols, rows
        self._status = _STATUS.get(alert.tag, alert.tag)
        self._color = _STATUS_COLOR.get(alert.tag, (255, 176, 48))
        self._urgent = alert.tag == "SUSP"

    def render(self, elapsed_ms: int) -> Image.Image:
        frame = elapsed_ms // 100
        img = Image.new("RGB", (self.cols, self.rows), _BG)

        # Motion: a gentle brightness pulse; suspensions flash harder and nudge
        # the bullet side to side a pixel for a touch of urgency.
        if self._urgent:
            pulse = 0.6 + 0.4 * (1 if (frame // 3) % 2 == 0 else 0)
            shake = 1 if (frame // 2) % 2 == 0 else -1
        else:
            pulse = 0.78 + 0.22 * (0.5 + 0.5 * math.sin(frame * 0.5))
            shake = 0

        # Bullet up top, status word centered below, reason on the bottom row —
        # one idea, stacked, nothing clipped. Everything is scale 1 so the longest
        # status ("SUSPENDED", 45px) and reason ("MECHANICAL", 50px) still fit 64px.
        bx = (self.cols - _BULLET_D) // 2 + shake
        bullet = make_bullet(self.alert.line, _BULLET_D)
        if pulse < 1.0:
            bullet = self._fade(bullet, pulse)
        img.paste(bullet, (bx, 0), bullet)

        status_color = S.lerp((0, 0, 0), self._color, pulse)
        sx = (self.cols - S.text_width(self._status)) // 2
        S.draw_text(img, sx, 16, self._status, status_color, outline=_OUT)

        reason = self.alert.reason
        if reason:
            rx = (self.cols - S.text_width(reason)) // 2
            S.draw_text(img, rx, 24, reason, _REASON_COLOR, outline=_OUT)
        return img

    @staticmethod
    def _fade(bullet: Image.Image, factor: float) -> Image.Image:
        """Scale RGB by `factor`, keeping the alpha so the disc stays a disc."""
        r, g, b, a = bullet.split()
        rgb = Image.merge("RGB", (r, g, b)).point(lambda v: int(v * factor))
        r2, g2, b2 = rgb.split()
        return Image.merge("RGBA", (r2, g2, b2, a))


class AlertSource:
    """Emits an AlertScene for the most-severe disrupted tracked line.

    `provider()` returns the current per-stop `List[Optional[LineAlert]]` (wired to
    `store.line_alerts`). When several lines are disrupted at the top severity, the
    source rotates which one it shows on successive plays so no single line hogs the
    screen. Returns None when nothing is disrupted."""
    name = "alerts"

    # Most-severe first, so a suspension always outranks a delay for the screen.
    _ORDER = {"SUSP": 3, "RDCD": 2, "DLY": 1}

    def __init__(self, provider: Callable[[], Sequence[Optional[LineAlert]]],
                 cols: int = 64, rows: int = 32):
        self._provider = provider
        self.cols, self.rows = cols, rows
        self._rotation = 0

    def _candidates(self) -> List[LineAlert]:
        """The disrupted alerts at the top severity, de-duplicated by line."""
        alerts = [a for a in (self._provider() or []) if a is not None]
        if not alerts:
            return []
        top = max(self._ORDER.get(a.tag, 0) for a in alerts)
        out: List[LineAlert] = []
        seen = set()
        for a in alerts:
            if self._ORDER.get(a.tag, 0) == top and a.line not in seen:
                seen.add(a.line)
                out.append(a)
        return out

    def poll(self, ctx) -> Optional[Scene]:
        candidates = self._candidates()
        if not candidates:
            return None
        chosen = candidates[self._rotation % len(candidates)]
        self._rotation += 1
        return AlertScene(chosen, self.cols, self.rows)
