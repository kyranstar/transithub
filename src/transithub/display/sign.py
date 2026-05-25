from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

from PIL import Image

from ..config import Config
from ..models import Arrival
from .bullets import make_bullet, _font  # reuse the cached spleen font

_BULLET_D = 15        # roundel diameter, fits a 16px row
_ROW_H = 16
_TEXT_COLOR = (255, 170, 40)     # amber countdown
_DEST_COLOR = (245, 222, 150)
_ALERT_COLOR = (240, 60, 40)     # red disruption message
_BLINK_MS = 250                  # ~2Hz on/off for arriving "Now"


def format_time(arrival: Arrival, now: datetime, threshold: int) -> Tuple[str, bool]:
    """Right-field text and whether it's arriving.

    Under `threshold` seconds -> flashing "Now". Otherwise minutes, but never "0m":
    anything from `threshold` up to 2 minutes reads "1m".
    """
    if arrival.is_arriving(now, threshold):
        return ("Now", True)
    return (f"{max(1, arrival.minutes_until(now))}m", False)


@dataclass
class RowModel:
    line: str
    destination: str
    time_text: str
    arriving: bool
    has_arrival: bool = True
    alert_tag: Optional[str] = None
    alert_reason: str = ""        # short cause ("SIGNALS", "SICK PASS"); "" if unknown


_SUSPENDED_WEIGHT_FACTOR = 0.5   # a suspended line shows half as often


@dataclass
class Panel:
    """One stop's screen: its next arrivals plus a relative airtime weight."""
    rows: List[RowModel]
    weight: float


def build_schedule(panels: List[Panel], page_seconds: int):
    """Weighted rotation: list of (rows, duration_seconds), one screen per stop."""
    if not panels:
        return [([], float(page_seconds))]
    return [(p.rows, float(p.weight * page_seconds)) for p in panels]


def pick_page(schedule, tick_ms: int) -> List[RowModel]:
    cycle = sum(d for _, d in schedule)
    if cycle <= 0:
        return schedule[0][0]
    t = (tick_ms / 1000.0) % cycle
    acc = 0.0
    for rows, dur in schedule:
        acc += dur
        if t < acc:
            return rows
    return schedule[-1][0]


class SignRenderer:
    def __init__(self, config: Config):
        self.cfg = config
        self.cols = config.matrix.cols
        self.rows = config.matrix.rows
        self.font = _font()
        self.per_page = max(1, self.rows // _ROW_H)   # arrivals shown per stop (2)

    def _build_panels(self, arrivals_by_train, alerts, now) -> List[Panel]:
        threshold = self.cfg.display.arriving_threshold_seconds
        panels: List[Panel] = []
        for i, arrivals in enumerate(arrivals_by_train):
            train = self.cfg.trains[i] if i < len(self.cfg.trains) else None
            weight = float(train.weight if train else 1)
            line = train.line if train else (arrivals[0].line if arrivals else "?")
            alert = alerts[i] if i < len(alerts) else None
            tag = alert.tag if alert else None
            reason = (alert.reason or "") if alert else ""
            if tag == "SUSP":
                weight *= _SUSPENDED_WEIGHT_FACTOR   # suspended -> show half as often
            if arrivals:
                rows = []
                for a in arrivals[:self.per_page]:
                    text, arriving = format_time(a, now, threshold)
                    rows.append(RowModel(a.line, a.destination, text, arriving,
                                         has_arrival=True, alert_tag=tag, alert_reason=reason))
            else:
                rows = [RowModel(line, "No service", "--", False,
                                 has_arrival=False, alert_tag=tag, alert_reason=reason)]
            panels.append(Panel(rows=rows, weight=weight))
        return panels

    def render(self, arrivals_by_train, tick_ms: int, now: datetime,
               alerts: Optional[List] = None) -> Image.Image:
        """`alerts` is one `LineAlert` (tag + reason) or None per tracked stop."""
        alerts = alerts or []
        img = Image.new("RGB", (self.cols, self.rows), (0, 0, 0))
        panels = self._build_panels(arrivals_by_train, alerts, now)
        schedule = build_schedule(panels, self.cfg.display.page_seconds)
        page = pick_page(schedule, tick_ms)
        blink_on = (tick_ms // _BLINK_MS) % 2 == 0
        for i, row in enumerate(page):
            self._draw_row(img, row, i * _ROW_H, tick_ms, blink_on)
        return img

    def _draw_row(self, img, row: RowModel, y0: int, tick_ms: int, blink_on: bool):
        if row.line != "?":
            bullet = make_bullet(row.line, _BULLET_D)
            img.paste(bullet, (0, y0 + (_ROW_H - _BULLET_D) // 2), bullet)

        ty = y0 + (_ROW_H - self.font.height) // 2
        win_l = _BULLET_D + 2

        # A disruption shows a red "TAG REASON" message (e.g. "DLY SIGNAL PROBLEM",
        # "SUSP SICK PASSENGER"), marqueeing if it's long. For a running line the
        # countdown stays anchored on the right; a suspension uses the whole row. An
        # arriving train keeps its flashing "Now" instead.
        if row.alert_tag and not row.arriving:
            msg = f"{row.alert_tag} {row.alert_reason}".strip()
            reserve = self.font.text_width(row.time_text)
            if row.has_arrival:
                self._blit(img, self.cols - reserve, ty, row.time_text, _TEXT_COLOR, 0, self.cols)
                win_r = self.cols - reserve - 2
            else:
                win_r = self.cols - 2
            self._draw_dest(img, msg, y0, win_l, win_r, tick_ms, _ALERT_COLOR)
            return

        # Normal row (or arriving): countdown / flashing "Now" on the right, headsign
        # in the middle.
        reserve = self.font.text_width(row.time_text)
        if not row.arriving or blink_on:
            self._blit(img, self.cols - reserve, ty, row.time_text, _TEXT_COLOR, 0, self.cols)
        self._draw_dest(img, row.destination, y0, win_l, self.cols - reserve - 2, tick_ms,
                        _DEST_COLOR)

    def _draw_dest(self, img, dest, y0, win_l, win_r, tick_ms, color=_DEST_COLOR):
        ty = y0 + (_ROW_H - self.font.height) // 2
        dw = self.font.text_width(dest)
        window = win_r - win_l
        if window <= 0:
            return
        if dw <= window:
            self._blit(img, win_l, ty, dest, color, win_l, win_r)
        else:
            span = dw + 10  # gap before wrap
            off = (tick_ms * self.cfg.display.scroll_speed // 40) % span
            self._blit(img, win_l - off, ty, dest, color, win_l, win_r)
            self._blit(img, win_l - off + span, ty, dest, color, win_l, win_r)

    def _blit(self, img, x, y, text, color, clip_l, clip_r):
        for px, py in self.font.iter_pixels(x, y, text):
            if clip_l <= px < clip_r and 0 <= px < self.cols and 0 <= py < self.rows:
                img.putpixel((px, py), color)
