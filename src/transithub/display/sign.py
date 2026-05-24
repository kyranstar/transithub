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
_ALERT_COLOR = (240, 60, 40)     # red disruption tag
_BLINK_MS = 250                  # ~2Hz on/off for arriving "Now"

# Alert badge: show the countdown, then flash the tag, repeating.
_BADGE_CYCLE_MS = 5000
_BADGE_TIME_MS = 3500            # countdown is shown for this slice of the cycle
_BADGE_FLASH_MS = 250            # blink rate of the tag within its slice


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

    def _build_panels(self, arrivals_by_train, tags, now) -> List[Panel]:
        threshold = self.cfg.display.arriving_threshold_seconds
        panels: List[Panel] = []
        for i, arrivals in enumerate(arrivals_by_train):
            train = self.cfg.trains[i] if i < len(self.cfg.trains) else None
            weight = float(train.weight if train else 1)
            line = train.line if train else (arrivals[0].line if arrivals else "?")
            tag = tags[i] if i < len(tags) else None
            if tag == "SUSP":
                weight *= _SUSPENDED_WEIGHT_FACTOR   # suspended -> show half as often
            if arrivals:
                rows = []
                for a in arrivals[:self.per_page]:
                    text, arriving = format_time(a, now, threshold)
                    rows.append(RowModel(a.line, a.destination, text, arriving,
                                         has_arrival=True, alert_tag=tag))
            else:
                rows = [RowModel(line, "No service", "--", False,
                                 has_arrival=False, alert_tag=tag)]
            panels.append(Panel(rows=rows, weight=weight))
        return panels

    def render(self, arrivals_by_train, tick_ms: int, now: datetime,
               tags: Optional[List[Optional[str]]] = None) -> Image.Image:
        tags = tags or []
        img = Image.new("RGB", (self.cols, self.rows), (0, 0, 0))
        panels = self._build_panels(arrivals_by_train, tags, now)
        schedule = build_schedule(panels, self.cfg.display.page_seconds)
        page = pick_page(schedule, tick_ms)
        blink_on = (tick_ms // _BLINK_MS) % 2 == 0
        for i, row in enumerate(page):
            self._draw_row(img, row, i * _ROW_H, tick_ms, blink_on)
        return img

    def _right_field(self, row: RowModel, tick_ms: int, blink_on: bool):
        """The right-hand field: (text, color), or (None, None) to draw nothing."""
        if row.arriving:
            # Flash only the "Now" text; the bullet and destination stay lit.
            return (row.time_text, _TEXT_COLOR) if blink_on else (None, None)
        tag = row.alert_tag
        if tag and not row.has_arrival:
            return (tag, _ALERT_COLOR)          # suspended/no-service: steady tag
        if tag and row.has_arrival:
            phase = tick_ms % _BADGE_CYCLE_MS
            if phase < _BADGE_TIME_MS:
                return (row.time_text, _TEXT_COLOR)
            flash_on = ((phase - _BADGE_TIME_MS) // _BADGE_FLASH_MS) % 2 == 0
            return (tag, _ALERT_COLOR) if flash_on else (None, None)
        return (row.time_text, _TEXT_COLOR)

    def _draw_row(self, img, row: RowModel, y0: int, tick_ms: int, blink_on: bool):
        if row.line != "?":
            bullet = make_bullet(row.line, _BULLET_D)
            img.paste(bullet, (0, y0 + (_ROW_H - _BULLET_D) // 2), bullet)

        ty = y0 + (_ROW_H - self.font.height) // 2
        reserve = max(self.font.text_width(row.time_text),
                      self.font.text_width(row.alert_tag or ""))
        right_text, right_color = self._right_field(row, tick_ms, blink_on)
        if right_text is not None:
            rx = self.cols - self.font.text_width(right_text)
            self._blit(img, rx, ty, right_text, right_color, 0, self.cols)

        win_l = _BULLET_D + 2
        win_r = self.cols - reserve - 2
        self._draw_dest(img, row.destination, y0, win_l, win_r, tick_ms)

    def _draw_dest(self, img, dest, y0, win_l, win_r, tick_ms):
        ty = y0 + (_ROW_H - self.font.height) // 2
        dw = self.font.text_width(dest)
        window = win_r - win_l
        if window <= 0:
            return
        if dw <= window:
            self._blit(img, win_l, ty, dest, _DEST_COLOR, win_l, win_r)
        else:
            span = dw + 10  # gap before wrap
            off = (tick_ms * self.cfg.display.scroll_speed // 40) % span
            self._blit(img, win_l - off, ty, dest, _DEST_COLOR, win_l, win_r)
            self._blit(img, win_l - off + span, ty, dest, _DEST_COLOR, win_l, win_r)

    def _blit(self, img, x, y, text, color, clip_l, clip_r):
        for px, py in self.font.iter_pixels(x, y, text):
            if clip_l <= px < clip_r and 0 <= px < self.cols and 0 <= py < self.rows:
                img.putpixel((px, py), color)
