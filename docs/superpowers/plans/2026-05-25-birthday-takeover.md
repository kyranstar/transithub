# Birthday Takeover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A configurable, recurring fullscreen "HAPPY BIRTHDAY <name>" takeover that rotates through three animations on a person's birthday, mirroring the config-driven farmers-market feature.

**Architecture:** UI-free logic in `birthdays.py` (parse config dicts → specs; "who has a birthday today"); a `BirthdayScene` (three styles) + `BirthdaySource` (rotates style per appearance) in `display/scenes/birthday.py`; wired into the Director as a Slot whose cadence comes from config. The market's cadence is lifted into config at the same time.

**Tech Stack:** Python 3.13, Pillow, stdlib `datetime`/`math`, pytest. Run tests from repo root inside `.venv` (`source .venv/bin/activate`). Commits omit any Co-Authored-By trailer (repo convention).

---

### Task 1: Birthday logic (`birthdays.py`)

**Files:**
- Create: `src/transithub/birthdays.py`
- Test: `tests/test_birthdays.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_birthdays.py`:

```python
"""Offline tests for the config-driven birthday logic.

No network: birthdays come from plain config dicts (as parsed from YAML). ``now``
is pinned so "whose birthday is today" is deterministic. Yennifer/09-17 is the
documented placeholder and the backbone case."""
from __future__ import annotations

from datetime import datetime

from transithub.birthdays import BirthdaySpec, birthday_today, parse_specs

YEN = {"name": "Yennifer", "date": "09-17"}


# --- spec parsing ----------------------------------------------------------
def test_parse_basic_mmdd():
    assert parse_specs([YEN]) == [BirthdaySpec(name="Yennifer", month=9, day=17)]


def test_parse_single_digit_month_day():
    specs = parse_specs([{"name": "Sam", "date": "3-4"}])
    assert specs and specs[0].month == 3 and specs[0].day == 4


def test_parse_ignores_leading_year():
    specs = parse_specs([{"name": "Ana", "date": "1990-12-25"}])
    assert specs and (specs[0].month, specs[0].day) == (12, 25)


def test_parse_skips_bad_entries():
    specs = parse_specs([
        {"name": "Good", "date": "09-17"},
        {"name": "No date"},                        # missing date -> skipped
        {"name": "Bad date", "date": "soon"},       # unparseable -> skipped
        {"name": "Out of range", "date": "13-40"},  # invalid month/day -> skipped
        {"date": "01-01"},                          # missing name -> skipped
        "not a dict",                               # wrong type -> skipped
    ])
    assert [s.name for s in specs] == ["Good"]


def test_parse_preserves_order():
    specs = parse_specs([{"name": "A", "date": "01-02"}, {"name": "B", "date": "03-04"}])
    assert [s.name for s in specs] == ["A", "B"]


# --- birthday_today: month+day, any year -----------------------------------
def test_birthday_today_matches_regardless_of_year():
    specs = parse_specs([YEN])
    assert birthday_today(specs, datetime(2026, 9, 17, 0, 0)) == "Yennifer"   # midnight
    assert birthday_today(specs, datetime(2031, 9, 17, 23, 59)) == "Yennifer"  # other year


def test_birthday_today_wrong_day_is_none():
    specs = parse_specs([YEN])
    assert birthday_today(specs, datetime(2026, 9, 16, 12, 0)) is None
    assert birthday_today(specs, datetime(2026, 10, 17, 12, 0)) is None


def test_birthday_today_first_match_wins():
    specs = parse_specs([{"name": "First", "date": "09-17"},
                         {"name": "Second", "date": "09-17"}])
    assert birthday_today(specs, datetime(2026, 9, 17, 8, 0)) == "First"


def test_birthday_today_empty_is_none():
    assert birthday_today([], datetime(2026, 9, 17)) is None


def test_birthday_today_leap_day():
    specs = parse_specs([{"name": "Leap", "date": "02-29"}])
    assert birthday_today(specs, datetime(2024, 2, 29, 12, 0)) == "Leap"   # leap year
    assert birthday_today(specs, datetime(2025, 2, 28, 12, 0)) is None     # non-leap
```

- [ ] **Step 2: Run to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/test_birthdays.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'transithub.birthdays'`.

- [ ] **Step 3: Create `src/transithub/birthdays.py`**

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `source .venv/bin/activate && python -m pytest tests/test_birthdays.py -q`
Expected: PASS (all 9 tests).

- [ ] **Step 5: Commit**

```bash
git add src/transithub/birthdays.py tests/test_birthdays.py
git commit -m "Birthday logic: config-driven specs + who-is-today"
```

---

### Task 2: Birthday scene + source (`display/scenes/birthday.py`)

Three rotating animations, header "HAPPY"/"BIRTHDAY" + name. The header must wrap
to two lines because "HAPPY BIRTHDAY" is 70px wide (> the 64px panel); "HAPPY"
(25px) and "BIRTHDAY" (40px) each fit. Text is drawn over a full-frame animated
background with an outline so it stays legible (the `sky.py` pattern).

**Files:**
- Create: `src/transithub/display/scenes/birthday.py`
- Test: `tests/test_scene_birthday.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scene_birthday.py`:

```python
"""Render + rotation tests for the birthday scene and its source.

No network: the scene is built from a name + style, the source from parsed config
specs plus a Context whose ``now`` we set directly. Every text line must fit the
64px panel, and the source must rotate through the three styles."""
from __future__ import annotations

from datetime import datetime

from transithub.birthdays import parse_specs
from transithub.display import scenery as S
from transithub.display.director import Context
from transithub.display.scenes.birthday import (BirthdayScene, BirthdaySource,
                                                 _STYLES)
from transithub.profile import Profile

YEN = {"name": "Yennifer", "date": "09-17"}
BDAY = datetime(2026, 9, 17, 0, 0)        # midnight on the birthday
NOT_BDAY = datetime(2026, 9, 18, 12, 0)


def _ctx(now=BDAY, profile=Profile.DAY):
    return Context(now=now, mono_ms=0, profile=profile)


# --- BirthdayScene ---------------------------------------------------------
def test_scene_duration_and_styles():
    assert BirthdayScene("Yennifer").duration_ms == 9000
    assert _STYLES == ("confetti", "cake", "fireworks")


def test_scene_renders_each_style():
    for style in _STYLES:
        s = BirthdayScene("Yennifer", style)
        for t in (0, 300, 4000):
            img = s.render(t)
            assert img.size == (64, 32) and img.mode == "RGB"


def test_scene_draws_something():
    for style in _STYLES:
        img = BirthdayScene("Yennifer", style).render(2000)
        assert any(img.getpixel((x, y)) != (0, 0, 0)
                   for x in range(64) for y in range(32)), f"{style} drew nothing"


def test_scene_lines_fit_panel():
    for line in BirthdayScene("Yennifer").lines():
        assert S.text_width(line) <= 64, f"{line!r} overflows"


def test_scene_long_name_truncated():
    for line in BirthdayScene("BARTHOLOMEW MAXIMILIANO").lines():
        assert S.text_width(line) <= 64


def test_scene_shows_header_and_name():
    lines = BirthdayScene("Yennifer").lines()
    assert lines[0] == "HAPPY" and lines[1] == "BIRTHDAY"
    assert "YENNIFER" in lines[2]


def test_scene_unknown_style_falls_back_to_confetti():
    assert BirthdayScene("Yennifer", "sparkles").style == "confetti"


# --- BirthdaySource --------------------------------------------------------
def test_source_returns_scene_on_birthday():
    src = BirthdaySource(parse_specs([YEN]))
    scene = src.poll(_ctx(now=BDAY))
    assert isinstance(scene, BirthdayScene) and scene.name == "Yennifer"


def test_source_none_when_not_birthday():
    assert BirthdaySource(parse_specs([YEN])).poll(_ctx(now=NOT_BDAY)) is None


def test_source_empty_specs_is_none():
    assert BirthdaySource([]).poll(_ctx()) is None


def test_source_rotates_style_per_appearance():
    src = BirthdaySource(parse_specs([YEN]))
    styles = [src.poll(_ctx(now=BDAY)).style for _ in range(4)]
    assert styles == ["confetti", "cake", "fireworks", "confetti"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/test_scene_birthday.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'transithub.display.scenes.birthday'`.

- [ ] **Step 3: Create `src/transithub/display/scenes/birthday.py`**

```python
"""Birthday takeover: HAPPY BIRTHDAY + a name, on someone's birthday.

One celebrant per day (the first configured). A fullscreen takeover that rotates
through three animations on each appearance — confetti & balloons, a candlelit
cake, and fireworks. Config-driven and clockwork only: the source reads
``ctx.now`` against the parsed birthday specs; there's no background poller. Text
is drawn over the animated background with an outline so it stays legible."""
from __future__ import annotations

import math
from typing import List, Optional

from PIL import Image

from ...birthdays import birthday_today
from .. import scenery as S
from ..director import Context
from .base import Scene

COLS, ROWS = 64, 32
DURATION_MS = 9000
_STYLES = ("confetti", "cake", "fireworks")

_OUT = (8, 6, 18)                 # dark outline so text reads over the motion
_HDR = (255, 236, 140)            # warm "HAPPY BIRTHDAY"
_NAME = (255, 255, 255)
_PARTY = ((255, 240, 130), (140, 220, 250), (250, 140, 170), (150, 240, 160))

_CONFETTI_BG = [(0.0, (54, 22, 74)), (0.55, (122, 50, 96)), (1.0, (198, 92, 68))]
_CAKE_BG = [(0.0, (32, 22, 56)), (1.0, (16, 12, 34))]
_FW_BG = [(0.0, (6, 8, 26)), (1.0, (14, 14, 40))]
_FW_COLORS = ((255, 210, 120), (140, 220, 255), (250, 150, 190), (170, 245, 170))


def _fit(text: str, max_px: int = 62) -> str:
    """Shorten ``text`` so it renders within ``max_px`` — drop trailing words
    first, then hard-trim characters as a last resort. Never clips."""
    if S.text_width(text) <= max_px:
        return text
    words = text.split()
    while len(words) > 1:
        words.pop()
        candidate = " ".join(words)
        if S.text_width(candidate) <= max_px:
            return candidate
    out = words[0] if words else text
    while out and S.text_width(out) > max_px:
        out = out[:-1]
    return out


def _centered(img: Image.Image, y: int, text: str, color) -> None:
    S.draw_text(img, (COLS - S.text_width(text)) // 2, y, text, color, outline=_OUT)


class BirthdayScene(Scene):
    """"HAPPY / BIRTHDAY / <name>" over a rotating party animation."""
    duration_ms = DURATION_MS

    def __init__(self, name: str, style: str = "confetti", cols: int = COLS, rows: int = ROWS):
        self.name = name
        self.style = style if style in _STYLES else "confetti"
        self.cols, self.rows = cols, rows

    def lines(self) -> List[str]:
        return ["HAPPY", "BIRTHDAY", _fit((self.name or "").upper())]

    # -- animated backgrounds ---------------------------------------------
    def _bg_confetti(self, img: Image.Image, frame: int) -> None:
        S.gradient(img, _CONFETTI_BG)
        px = img.load()
        for i in range(22):                            # confetti drifting down
            y = (i * 5 + frame) % self.rows
            x = (i * 13 + y // 3) % self.cols
            px[x, y] = _PARTY[i % len(_PARTY)]
        for b in range(3):                             # balloons rising from below
            bx = 10 + b * 22
            by = (self.rows + 2) - ((frame + b * 13) % (self.rows + 6))
            color = _PARTY[(b + 1) % len(_PARTY)]
            for dx, dy in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)):
                X, Y = bx + dx, by + dy
                if 0 <= X < self.cols and 0 <= Y < self.rows:
                    px[X, Y] = color
            for k in (2, 3, 4):                         # string
                Y = by + k
                if 0 <= bx < self.cols and 0 <= Y < self.rows:
                    px[bx, Y] = (210, 210, 220)

    def _bg_cake(self, img: Image.Image, frame: int) -> None:
        S.gradient(img, _CAKE_BG)
        px = img.load()
        base_top = self.rows - 5                        # cake body: bottom 5 rows
        for x in range(8, self.cols - 8):
            for y in range(base_top, self.rows):
                px[x, y] = (198, 122, 86)
            px[x, base_top] = (250, 240, 246)           # icing along the top edge
        for j, cx in enumerate(range(13, self.cols - 9, 11)):   # candles + flames
            for y in range(base_top - 4, base_top):
                px[cx, y] = (244, 238, 250)
            fy = base_top - 5 - (1 if ((frame + j * 2) % 6) < 3 else 0)
            if 0 <= fy < self.rows:
                px[cx, fy] = (255, 244, 186)
                if fy + 1 < self.rows:
                    px[cx, fy + 1] = (255, 188, 86)

    def _bg_fireworks(self, img: Image.Image, frame: int) -> None:
        S.gradient(img, _FW_BG)
        S.stars(img, frame, seed=29, count=10)
        px = img.load()
        for j, (cx, cy) in enumerate(((14, 9), (50, 8), (32, 25))):
            phase = (frame + j * 7) % 18                 # expand-then-fade cycle
            if phase >= 12:                              # faded part of the cycle
                continue
            r = phase // 3 + 1
            color = _FW_COLORS[j % len(_FW_COLORS)]
            for ang in range(0, 360, 45):                # 8 spokes
                x = int(cx + r * math.cos(math.radians(ang)))
                y = int(cy + r * math.sin(math.radians(ang)))
                if 0 <= x < self.cols and 0 <= y < self.rows:
                    px[x, y] = color
            if 0 <= cx < self.cols and 0 <= cy < self.rows:
                px[cx, cy] = (255, 255, 255)

    def render(self, elapsed_ms: int) -> Image.Image:
        frame = elapsed_ms // 100
        img = Image.new("RGB", (self.cols, self.rows), (0, 0, 0))
        bg = {"cake": self._bg_cake, "fireworks": self._bg_fireworks}.get(
            self.style, self._bg_confetti)
        bg(img, frame)
        hdr1, hdr2, name = self.lines()
        _centered(img, 1, hdr1, _HDR)
        _centered(img, 9, hdr2, _HDR)
        _centered(img, 18, name, _NAME)
        if elapsed_ms < 600:        # gentle fade-in so it arrives calmly
            return Image.blend(Image.new("RGB", (self.cols, self.rows), (0, 0, 0)),
                               img, elapsed_ms / 600)
        return img


class BirthdaySource:
    """Shows the configured birthday for today, decided from ``ctx.now``.

    Holds the parsed specs and an index that advances each appearance, so
    consecutive takeovers rotate confetti -> cake -> fireworks. No network, no
    holder — just the specs and the clock."""
    name = "birthday"

    def __init__(self, specs, cols: int = COLS, rows: int = ROWS):
        self.specs = list(specs)
        self.cols, self.rows = cols, rows
        self._i = 0

    def poll(self, ctx: Context) -> Optional[Scene]:
        who = birthday_today(self.specs, ctx.now)
        if who is None:
            return None
        style = _STYLES[self._i % len(_STYLES)]
        self._i += 1
        return BirthdayScene(who, style, self.cols, self.rows)
```

- [ ] **Step 4: Run to verify it passes**

Run: `source .venv/bin/activate && python -m pytest tests/test_scene_birthday.py -q`
Expected: PASS (all 11 tests).

- [ ] **Step 5: Commit**

```bash
git add src/transithub/display/scenes/birthday.py tests/test_scene_birthday.py
git commit -m "Birthday scene + source: three rotating party animations"
```

---

### Task 3: Config — birthdays section + configurable market cadence

**Files:**
- Modify: `src/transithub/config.py` (`LocalConfig` ~line 90; add `BirthdaysConfig`; `Config` ~line 100; `load_config` ~line 137)
- Modify: `config.example.yaml`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
def test_birthdays_and_market_cadence(tmp_path):
    cfg = load_config(_write(tmp_path, """
        trains:
          - {line: "L", stop_id: "L16", direction: "N"}
        local:
          every_minutes: 45
        birthdays:
          every_minutes: 15
          people:
            - {name: "Yennifer", date: "09-17"}
    """))
    assert cfg.local.every_minutes == 45
    assert cfg.birthdays.enabled is True and cfg.birthdays.every_minutes == 15
    assert cfg.birthdays.people == [{"name": "Yennifer", "date": "09-17"}]


def test_birthdays_and_local_cadence_defaults(tmp_path):
    cfg = load_config(_write(tmp_path, """
        trains:
          - {line: "L", stop_id: "L16", direction: "N"}
    """))
    assert cfg.local.every_minutes == 30           # market cadence default
    assert cfg.birthdays.enabled is True
    assert cfg.birthdays.every_minutes == 10 and cfg.birthdays.people == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/test_config.py -q`
Expected: FAIL — `AttributeError: 'LocalConfig' object has no attribute 'every_minutes'` / `'Config' object has no attribute 'birthdays'`.

- [ ] **Step 3: Add `every_minutes` to `LocalConfig` and a `BirthdaysConfig`**

In `src/transithub/config.py`, replace the `LocalConfig` dataclass with:

```python
@dataclass
class LocalConfig:
    enabled: bool = True                    # show a nearby farmers market open today
    every_minutes: int = 30                 # how often the market notice appears
    markets: List[dict] = field(default_factory=list)   # curated; see config.example.yaml
```

And add a new dataclass immediately after `LocalConfig`:

```python
@dataclass
class BirthdaysConfig:
    enabled: bool = True                    # show a HAPPY BIRTHDAY takeover on someone's day
    every_minutes: int = 10                 # how often the birthday takeover appears
    people: List[dict] = field(default_factory=list)    # {name, date: "MM-DD"}; see config.example.yaml
```

- [ ] **Step 4: Register `birthdays` on `Config` and in `load_config`**

In `src/transithub/config.py`, add the field to the `Config` dataclass (right
after the `local` line):

```python
    birthdays: BirthdaysConfig = field(default_factory=BirthdaysConfig)
```

And in `load_config`'s `return Config(...)` call, add (right after the `local=`
line):

```python
        birthdays=_section(BirthdaysConfig, raw.get("birthdays")),
```

- [ ] **Step 5: Run to verify it passes**

Run: `source .venv/bin/activate && python -m pytest tests/test_config.py -q`
Expected: PASS — the two new tests and all pre-existing config tests
(`test_ambient_defaults` etc.) stay green (new fields have defaults).

- [ ] **Step 6: Document both in `config.example.yaml`**

In `config.example.yaml`, find the `local:` section. Add an `every_minutes: 30`
line under it (just below `enabled:` if present, else at the top of the section),
and add a new `birthdays:` section immediately after the `local:` block:

```yaml
birthdays:
  enabled: true
  every_minutes: 10            # how often a birthday takeover appears (all day)
  # Each entry: a name and a year-agnostic date as MM-DD. On that day the sign
  # throws a fullscreen party, rotating confetti -> cake -> fireworks.
  people:
    - {name: "Yennifer", date: "09-17"}
```

For the `local:` section, add this line (keeping the existing `enabled`/`markets`
keys):

```yaml
  every_minutes: 30            # how often the market notice appears
```

- [ ] **Step 7: Commit**

```bash
git add src/transithub/config.py config.example.yaml tests/test_config.py
git commit -m "Config: birthdays section + configurable market cadence (default 30m)"
```

---

### Task 4: Wire the birthday Slot + market cadence into the Director

**Files:**
- Modify: `src/transithub/__main__.py` (imports ~lines 7-29; `_build_director` ~lines 196-210)

- [ ] **Step 1: Add the imports**

In `src/transithub/__main__.py`, add these two imports alongside the existing
ones (the birthdays parser is aliased so it doesn't collide with the market
`parse_specs` already imported from `.local`):

```python
from .birthdays import parse_specs as parse_birthday_specs
from .display.scenes.birthday import BirthdaySource
```

- [ ] **Step 2: Use the config cadence for the market Slot**

In `_build_director`, the market Slot currently hardcodes its cadence. Change its
`cooldown_ms` from `120 * 60_000` to read config:

```python
    market_specs = parse_specs(cfg.local.markets) if cfg.local.enabled else []
    if market_specs:
        slots.append(Slot(MarketSource(market_specs, cols, rows), priority=40,
                          cooldown_ms=cfg.local.every_minutes * 60_000,
                          first_after_ms=3 * 60_000, profiles=DAY_EVENING))
```

- [ ] **Step 3: Add the birthday Slot**

In `_build_director`, immediately after the market Slot block (and before the
space block), add:

```python
    birthday_specs = parse_birthday_specs(cfg.birthdays.people) if cfg.birthdays.enabled else []
    if birthday_specs:
        # A personal, celebratory takeover. Active the whole calendar day (all
        # profiles, from midnight); the night dimmer keeps the small hours gentle.
        # interjection=False so the global anti-back-to-back gap can't suppress the
        # fixed cadence; it waits for a free screen rather than cutting a scene.
        slots.append(Slot(BirthdaySource(birthday_specs, cols, rows), priority=70,
                          cooldown_ms=cfg.birthdays.every_minutes * 60_000,
                          first_after_ms=60_000, interjection=False))
```

- [ ] **Step 4: Smoke-test that the app still builds and the full suite passes**

Run:
```bash
source .venv/bin/activate && python -c "import transithub.__main__ as m; print('import ok')" && python -m pytest -q
```
Expected: `import ok` then all tests pass (no new failures from the wiring).

- [ ] **Step 5: Verify the birthday Slot is actually wired (manual director check)**

Run:
```bash
source .venv/bin/activate && python -c "
from datetime import datetime
from transithub.display.scenes.birthday import BirthdaySource
from transithub.birthdays import parse_specs
from transithub.display.director import Context
from transithub.profile import Profile
src = BirthdaySource(parse_specs([{'name':'Yennifer','date':'09-17'}]))
ctx = Context(now=datetime(2026,9,17,0,0), mono_ms=0, profile=Profile.NIGHT)
s = src.poll(ctx)
print('midnight night-profile ->', type(s).__name__, getattr(s,'name',None), getattr(s,'style',None))
"
```
Expected: `midnight night-profile -> BirthdayScene Yennifer confetti` — confirms it
fires at 00:00 even in the NIGHT profile.

- [ ] **Step 6: Commit**

```bash
git add src/transithub/__main__.py
git commit -m "Wire birthday takeover Slot + market cadence from config"
```

---

### Task 5: README mention + final verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a concise feature bullet to the README**

In `README.md`, find the features list that mentions the existing ambient scenes
(weather/ISS/planes/moon/markets). Add one bullet in the same style/voice, e.g.:

```markdown
- **Birthday takeovers** — name someone in `birthdays:` and on their day the sign throws a fullscreen party, rotating confetti, cake, and fireworks animations every few minutes (cadence configurable).
```

Match the surrounding bullets' exact formatting (capitalization, bold lead-in,
trailing punctuation) so it reads as part of the existing list.

- [ ] **Step 2: Run the full suite**

Run: `source .venv/bin/activate && python -m pytest -q`
Expected: PASS — all pre-existing tests plus the new birthday logic, scene, and
config tests.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "README: mention birthday takeovers"
```

---

## Self-Review

**Spec coverage:**
- `birthdays.py` (BirthdaySpec, parse_specs, _parse_md, birthday_today) → Task 1. ✓
- `BirthdayScene` (3 styles, duration 9000, header+name, fit, fade-in) → Task 2. ✓
- `BirthdaySource` (rotate per appearance, ctx.now-driven) → Task 2. ✓
- `BirthdaysConfig` (enabled/every_minutes/people, empty default) + `LocalConfig.every_minutes=30` + load_config wiring + config.example.yaml (Yennifer placeholder) → Task 3. ✓
- Director Slot (priority 70, cooldown from config, interjection=False, first_after_ms, all profiles) + market cadence from config → Task 4. ✓
- Midnight/all-profiles behavior → verified by Task 1 midnight test + Task 4 Step 5 night-profile check. ✓
- Tests: parsing, birthday_today incl. leap day + any-year + first-wins; scene render/fit/draw per style; source rotation/none → Tasks 1-2. ✓
- README bullet → Task 5. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases"; every code step shows complete code; every run step shows the exact command + expected output.

**Type/name consistency:** `BirthdaySpec(name, month, day)`, `parse_specs`, `birthday_today(specs, now)->Optional[str]`, `BirthdayScene(name, style, cols, rows)` with `.lines()`/`.style`/`.name`/`duration_ms=9000`, `_STYLES=("confetti","cake","fireworks")`, `BirthdaySource(specs, cols, rows).poll`, `BirthdaysConfig`/`LocalConfig.every_minutes`, alias `parse_birthday_specs` — all consistent across tasks. Imports verified against `__main__.py` (market `parse_specs` comes from `.local`; birthdays aliased to avoid collision).
