"""Whose birthday is today, from a curated config list.

Mirrors the farmers-market feature: the owner lists people in YAML with a
year-agnostic ``MM-DD`` date; we surface the one whose birthday is today so the
sign can throw a little party. Parsing is tolerant — a bad/empty entry is skipped
rather than crashing the sign. The scene and source that *show* it live in
``display/scenes/birthday.py``.

A config entry looks like::

    {"name": "Yennifer", "date": "09-17"}
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass(frozen=True)
class BirthdaySpec:
    """One configured birthday: a person and their month/day (year-agnostic)."""
    name: str
    month: int        # 1..12
    day: int          # 1..31


def _parse_md(value) -> Optional[tuple[int, int]]:
    """A ``(month, day)`` pair from a config date string, or None.

    Accepts ``"MM-DD"``, ``"M-D"``, and ``"YYYY-MM-DD"`` (a leading 4-digit year
    is ignored — only month and day matter). Returns None for anything unparseable
    or out of range (month 1..12, day 1..31)."""
    parts = str(value or "").strip().split("-")
    if len(parts) == 3:                 # YYYY-MM-DD -> drop the year
        parts = parts[1:]
    if len(parts) != 2:
        return None
    try:
        month, day = int(parts[0]), int(parts[1])
    except (TypeError, ValueError):
        return None
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return month, day


def parse_specs(entries) -> List[BirthdaySpec]:
    """Parse a list of plain config dicts into ``BirthdaySpec``s.

    Each entry needs a non-empty ``name`` and a parseable ``date`` (``MM-DD``).
    Entries we can't parse are skipped, so one bad line never takes the feature
    down."""
    specs: List[BirthdaySpec] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        md = _parse_md(entry.get("date"))
        if md is None:
            continue
        specs.append(BirthdaySpec(name=name, month=md[0], day=md[1]))
    return specs


def birthday_today(specs: List[BirthdaySpec], now: datetime) -> Optional[str]:
    """The name of the first configured birthday on ``now``'s month/day (any
    year), else None. If several fall on the same day, the first listed wins."""
    for spec in specs:
        if spec.month == now.month and spec.day == now.day:
            return spec.name
    return None
