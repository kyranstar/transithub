# Scene framework

TransitHub shows one thing at a time on a 64×32 panel. The trains are always the
baseline; everything else — weather, sky events, neighborhood happenings, the odd
fact — *interjects*, plays its piece, and gets out of the way. This document
describes how that scheduling works so the experience stays calm and legible
instead of a slideshow that never sits still.

## The contract

A **`Scene`** renders one frame at a time and knows how long it wants to live:

```python
class Scene:
    duration_ms: int | None          # None = run until preempted (only the trains)
    def render(self, elapsed_ms: int) -> Image.Image: ...   # always 64×32 RGB
```

A **`SceneSource`** decides, each time the screen is free, whether it has
something to show *right now*:

```python
class SceneSource:
    name: str
    def poll(self, ctx: Context) -> Scene | None: ...   # a fresh Scene, or None
```

Sources are pure with respect to scheduling — they answer "do I want the screen?"
and hand back a Scene. They never decide *when* relative to other sources; the
`Director` owns that. A source reads the world through `Context`, never globals.

```python
@dataclass
class Context:
    now: datetime              # NYC wall clock
    mono_ms: int               # monotonic ms since boot (cooldown math)
    weather: Weather | None    # latest snapshot (or None before first fetch)
    profile: Profile           # DAY / EVENING / NIGHT
    sky: SkyData | None        # ISS pass + plane overhead snapshot
    space: SpaceData | None    # humans-in-space + EPIC earth frame
    local: LocalData | None    # farmers market + neighborhood events
    health: list[str]          # active health warnings (empty = all well)
```

The data fields are plain snapshots filled by background pollers (same pattern as
`WeatherHolder` today). A source that needs no data ignores the fields it doesn't
use.

## Layers and priority

The `Director` holds an ordered set of **`Slot`s**. A slot binds a source to a
scheduling policy:

```python
@dataclass
class Slot:
    source: SceneSource
    priority: int          # higher wins when several are ready
    cooldown_ms: int       # minimum gap between this source's plays
    profiles: set[Profile] # which day parts it runs in
    takeover: bool = False # may cut into a lower-priority finite scene
    interjection: bool = True  # subject to the global anti-back-to-back gap
```

Priority bands (higher = more urgent):

| Band | Sources | When |
|------|---------|------|
| 100 | **Health** (stale data / offline) | only when a feed is really broken; repeats while unresolved |
| 90  | **ISS pass** | the minutes around a visible pass |
| 85  | **Plane overhead** | while a plane is actually over you |
| 80  | **Full / new moon** | after sunset on the calendar day of the event |
| 60  | **Sunrise / sunset** | once each, around the event |
| 50  | **Weather rundown** | every 6 min (see cadence below) |
| 40  | **Market / neighborhood event** | a few daytime plays when something's on |
| 30  | **Interjections** (humans in space, Earth from space) | rare, randomized |
| 0   | **Trains** | the default; fills all remaining time |

## The render loop

Each frame, `Director.render(now, mono_ms)`:

1. Build the `Context` (current profile, snapshots, health).
2. **If a finite scene is mid-play:** let it finish, *unless* a `takeover` slot of
   higher priority than the running scene is ready — then preempt it. (A plane
   passing overhead is worth interrupting a weather slide; a fun fact is not.)
3. **If the screen is free** (trains, or a scene just ended): walk the slots in
   priority order and start the first whose `source.poll(ctx)` returns a Scene and
   whose cooldown has elapsed and whose `profiles` includes the current profile and
   that doesn't violate the global interjection gap.
4. Otherwise show the trains.
5. Apply the **dimmer** to the chosen frame.

Cooldowns are tracked per source (`mono_ms` of last play). A single
`min_interjection_gap_ms` keeps two non-default scenes from running back-to-back,
so the trains always get a breath between interruptions.

This keeps every "when do I show X" decision in one tested place. Adding a feature
means writing a `SceneSource` and registering a `Slot` — no new branches in the
loop.

## Day parts and dimming

`Profile` is derived from the sun times and the clock:

- **DAY** — between sunrise and sunset.
- **EVENING** — sunset until bedtime (~21:30).
- **NIGHT** — bedtime until sunrise.

The profile both gates slots (markets/events are daytime; the moon is night) and
drives the **dimmer**, which scales the final frame's brightness so the panel
isn't a nightlight-from-hell at 3am:

- DAY → full configured brightness.
- EVENING → ramps down from sunset to bedtime.
- NIGHT → a low floor (a dim, readable glow).

Dimming is applied once to the composed frame, so every scene dims uniformly and
the simulator shows exactly what the panel will.

## Weather cadence

The rundown fires **every 6 minutes** and plays **two full rounds** of its slide
deck, then yields — short enough to stay welcome, frequent enough to be useful. At
night the deck is leaner (time + temperature, skipping advisory slides) so a glance
at 2am is just the essentials.

## Health warnings

Pollers report success/failure to a `HealthMonitor`. It stays silent until
something is genuinely wrong — no recent successful weather fetch, or arrivals
stale well past their poll interval, or every feed failing (Wi-Fi down). Then it
surfaces a short, high-priority warning that repeats every couple of minutes until
the data recovers. The goal: invisible when healthy, impossible to miss when not.

## Why this shape

- **One concept per screen.** Sources emit a Scene that shows a single idea; the
  Director never composites two sources together.
- **Testable in isolation.** Each source is a small unit with an injected data
  snapshot. The Director is tested with fake sources for priority, cooldown,
  takeover, and profile gating — no clock, no network.
- **Calm by construction.** Cooldowns, the interjection gap, and profile gating are
  the knobs that keep the display from feeling like a billboard.
