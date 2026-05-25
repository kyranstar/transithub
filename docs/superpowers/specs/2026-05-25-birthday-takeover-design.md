# Birthday Takeover — Design

Date: 2026-05-25
Status: Approved (proceed straight through plan + implementation; no further approval gates)

A celebratory fullscreen takeover that says HAPPY BIRTHDAY + a person's name on
their birthday, rotating through three animations and recurring every configurable
number of minutes across the whole calendar day. Mirrors the config-driven,
no-network farmers-market feature.

## Architecture (parallels the market feature)

- **`src/transithub/birthdays.py`** — UI-free logic:
  - `BirthdaySpec(name: str, month: int, day: int)` (frozen dataclass).
  - `parse_specs(entries) -> List[BirthdaySpec]` — tolerant parsing of plain
    config dicts; a bad/unparseable entry is skipped, never raised (one bad line
    never takes the feature down), exactly like `markets.parse_specs`.
  - `birthday_today(specs, now) -> Optional[str]` — the name of the first spec
    whose `month`/`day` matches `now`, else None.
- **`src/transithub/display/scenes/birthday.py`** — the screen:
  - `BirthdayScene(name, style, cols=64, rows=32)` — one of three animations.
  - `BirthdaySource(specs, cols=64, rows=32)` — decides from `ctx.now`, rotates
    the style per appearance. No network, no holder — specs + the clock, like
    `MarketSource`.

## Config

New `birthdays` section, and a new cadence knob on the existing `local` section.

```yaml
birthdays:
  enabled: true
  every_minutes: 10          # how often a birthday takeover appears
  # name + date as MM-DD (year-agnostic). Rotates confetti -> cake -> fireworks.
  people:
    - {name: "Yennifer", date: "09-17"}

local:
  enabled: true
  every_minutes: 30          # how often the market notice appears (NEW knob)
  markets:
    - {name: "MARIA HERNANDEZ", day: "saturday",
       season: ["2026-05-23", "2026-11-22"], until: "3"}
```

- `BirthdaysConfig(enabled: bool = True, every_minutes: int = 10, people: List[dict] = [])`.
  Default `people` is **empty** (config-only); the Yennifer/09-17 entry lives only
  in `config.example.yaml` as the documented placeholder.
- `LocalConfig` gains `every_minutes: int = 30`. The market cadence is currently a
  hardcoded `120 * 60_000` in `_build_director`; this lifts it into config. **Note:
  this changes the market default from 120 → 30 minutes** (intentional, per owner).
- Both wired through `config.py`'s `Config`, `load_config` (`_section(...)`), and
  `config.example.yaml`.

### Date parsing (`birthdays.parse_specs`)

Each entry is a dict with a `name` and a `date` string. `date` is parsed by
`_parse_md`:
- Accepts `"MM-DD"`, `"M-D"`, and `"YYYY-MM-DD"` (a leading 4-digit year is
  ignored — only month/day matter).
- Validates `1 <= month <= 12` and `1 <= day <= 31`; out-of-range or unparseable
  → entry skipped.
- Missing/blank `name` → skipped. Non-dict entry → skipped.

Edge cases (documented, not special-cased): multiple people on one day → the
first listed wins; a `02-29` birthday only fires in leap years (it matches the
literal month/day, and Feb 29 only exists on leap years).

## The three animations (`BirthdayScene`, `duration_ms = 9000`)

Every style renders 64×32 RGB and shows the header **HAPPY BIRTHDAY** and the
**name**, fit-checked to the 64px panel (header may wrap to two lines; the name is
shortened with the market scene's `_fit` approach so it never clips). The
style-specific motion fills the remaining space / background, keeping the same
"don't crowd the text" discipline as the market awning:

- **confetti** — balloons drift upward, confetti flecks fall, warm gradient.
- **cake** — a pixel cake with candle flames that flicker, soft glow pulse.
- **fireworks** — spark bursts bloom and fade against a night sky.

A short fade-in (first ~600 ms) so each takeover arrives calmly, matching
`MarketScene`.

`_STYLES = ("confetti", "cake", "fireworks")`.

## Switching & scheduling (`BirthdaySource` + the Slot)

- **Rotate per appearance:** the source holds an integer counter; each poll that
  returns a scene picks `_STYLES[i % 3]` then increments `i`. So consecutive
  appearances cycle confetti → cake → fireworks → confetti…
- `poll(ctx)`: `name = birthday_today(self.specs, ctx.now)`; if None return None;
  else build a `BirthdayScene(name, next_style)`.
- **Slot wiring** in `__main__._build_director`:
  - `priority=70` (above weather 50 / market 40 / space 30; below the sky/health
    band: moon 80, plane 85, iss 90, health 100).
  - `cooldown_ms = cfg.birthdays.every_minutes * 60_000`.
  - `interjection=False` (the 20 s anti-back-to-back gap must not suppress the
    fixed cadence), `first_after_ms=60_000` (let trains show first right after
    boot). `takeover=False` (it waits for a free screen rather than cutting a
    running scene; trains are the default and fill almost all time, so it appears
    within its cadence).
  - `profiles` left at the default `frozenset(Profile)` → **all profiles**.
- **Midnight to midnight:** because eligibility is purely `birthday_today` +
  cooldown + all-profiles, the takeover is live the entire calendar day — from
  12:00 am, every `every_minutes`, until 11:59:59 pm. The existing night dimmer
  keeps the overnight hours gentle.
- The market Slot's `cooldown_ms` likewise becomes
  `cfg.local.every_minutes * 60_000`.

## Testing

- **`tests/test_birthdays.py`** (mirrors `test_local_markets.py`):
  - `parse_specs`: basic `MM-DD`; `M-D`; `YYYY-MM-DD` year ignored; missing name
    skipped; bad/empty date skipped; out-of-range month/day skipped; non-dict
    skipped; multiple valid entries preserved in order.
  - `birthday_today`: matches month+day regardless of year (different year `now`
    still matches); wrong day → None; multiple people same day → first; empty
    specs → None; `02-29` matches on a leap day and not on a non-leap Feb 28.
- **`tests/test_scene_birthday.py`** (mirrors `test_scene_local.py`):
  - `BirthdayScene`: for each of the three styles, `render(0)` and a mid frame
    return a 64×32 RGB image and draw a non-black pixel; `duration_ms == 9000`;
    header/name lines fit ≤64px; a long name is truncated to fit.
  - `BirthdaySource`: returns a `BirthdayScene` on a matching day, None otherwise;
    **rotates** style across three consecutive matching polls
    (confetti → cake → fireworks); empty specs → None.
- Full existing suite stays green. The one expected change: any test asserting the
  market's 120-minute cadence (if present) updates to read from
  `cfg.local.every_minutes`; the market scene/logic tests are unaffected.

## Docs

- One concise bullet in the README features list (birthday takeovers, configurable
  cadence). `config.example.yaml` documents both new sections/knobs.

## Out of scope

- Per-person colors/themes, multi-person same-day display, age/years, network
  birthday sources. Name is shown; one celebrant per day (first listed).
