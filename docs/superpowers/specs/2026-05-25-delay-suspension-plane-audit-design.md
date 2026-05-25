# Delay/Suspension Messaging + Plane Overhead — Audit & Fixes

Date: 2026-05-25
Status: Approved (pre-implementation)

This is the final audit before the repo is locked. Scope is bounded to three
parts: the alert reason parser, plane selection, and a tiny doc fix. No other
behavior changes.

## Part 1 — Reason parser (`mta/alerts.py`)

### Problem

`parse_reason` matches its keyword map with naive substring containment
(`keyword in hay`). The keyword `"ice"` therefore matches the `serv·ice`
substring, so nearly every *Reduced Service*, *No Scheduled Service*, and
*Suspended* alert — all of which contain the word "service" — parses as the
weather reason `ICE`. On the sign this renders as `SUSP ICE`. Confirmed:

```
parse_reason("No scheduled service is running on this line") -> "ICE"   # bug
parse_reason("Service has been suspended")                   -> "ICE"   # bug
parse_reason("due to a police investigation")                -> "POLICE" # only because
                                                                          # "police" is
                                                                          # checked first
```

This is a general defect: any short keyword embedded in a longer common word
will false-match (`ice` in service/office/notice/device, etc.).

### Fix: left-anchored word-boundary matching

Replace `keyword in hay` with a precompiled regex search anchored at a **left**
word boundary:

```python
re.search(r"\b" + re.escape(keyword), hay)
```

- Left boundary kills the embedded-suffix false positives: `\bice` does **not**
  match `service`/`office`/`notice`/`device`.
- It still matches the standalone term: `\bice` matches `ice on the rail`.
- It still matches plurals/suffixes: `\bsignal problem` matches "signal
  problem**s**"; `\bsnow` matches "snow**ing**". A *full* boundary (`\bice\b`)
  would wrongly break "signal problems", so left-anchored is the deliberate
  choice (verified empirically).

The keyword list stays an ordered list (specific phrases before generic ones,
so "signal problem" still wins over bare "signal"). Compile each keyword's
pattern once at module load (`re.compile`), preserving order.

### Keyword additions (high-confidence real MTA reasons)

Added because they are common, verifiable MTA mercury reason phrasings and are
currently unmapped:

| keyword           | label             | rationale                                            |
|-------------------|-------------------|------------------------------------------------------|
| `train traffic`   | `TRAIN TRAFFIC`   | the most common delay reason ("train traffic ahead") |
| `brake`           | `BRAKE PROBLEM`   | standard MTA mechanical reason                       |
| `door problem`    | `DOOR PROBLEM`    | standard MTA reason                                  |
| `earlier incident`| `EARLIER INCIDENT`| standard MTA reason                                  |
| `rail condition`  | `TRACK CONDITION` | folds into the existing label                        |
| `water main`      | `FLOODING`        | folds into the existing label                        |
| `icy`             | `ICE`             | legitimate winter phrasing                           |

Placement in the ordered list must not shadow or be shadowed incorrectly:
phrase keywords (`door problem`, `train traffic`, `rail condition`, `water
main`, `earlier incident`) carry their own context and can sit anywhere
sensible; `icy` sits next to `ice`; `brake` sits in the mechanical group.

### Testing — comprehensive, real-result driven

The defining requirement: **exercise the messaging with realistic MTA alert
text, not toy strings.** Concretely:

1. **Real-phrasing reason table.** A parametrized test mapping a corpus of
   real-world MTA alert header/description phrasings to their expected reason
   label. Includes, at minimum, one realistic phrasing per keyword (existing
   and new) — e.g. "delayed because of train traffic ahead of us", "while we
   address a mechanical problem", "due to brake problems", "because of a door
   problem", "an earlier incident", "rail condition", "a water main break",
   "icy conditions".

2. **False-positive guards (regression locks).** Assert the bug stays dead:
   - `"No scheduled service is running"` → `""` (not `ICE`)
   - `"Service has been suspended"` → `""` (not `ICE`)
   - `"reduced service"`, `"office"`, `"we'll notice"`, `"device"` → not `ICE`
   - A `Suspended` alert whose text only says "...service..." yields tag `SUSP`
     with reason `""` — i.e. the sign shows `SUSP`, never `SUSP ICE`.

3. **Plural/suffix matches still work.** `"signal problems"` → `SIGNAL PROBLEM`;
   `"replacing tracks"` → `TRACK WORK`; `"snowing heavily"` → `SNOW`.

4. **Full message output, end-to-end.** Extend the captured fixture
   (`tests/fixtures/alerts_sample.json`) with a few additional **realistic**
   alert entities covering the new reasons (e.g. a Delays alert citing train
   traffic, one citing brake problems), and assert the combined
   `tag + reason` that the sign would render via `alerts_for_trains` — proving
   the real feed shape flows through to the right message.

5. **Specificity ordering preserved.** "signal problem" beats bare "signal";
   "track maintenance" → TRACK WORK not TRACK CONDITION; etc.

All existing `test_alerts.py` assertions must continue to pass unchanged.

## Part 2 — Plane overhead (`sky/planes.py`)

### Problem

`parse_aircraft` ranks candidates by **horizontal** distance only and ignores
altitude, so a high cruiser passing overhead beats a low plane slightly off to
the side. The fixture demonstrates it precisely:

| callsign | alt (ft) | horizontal | slant (3D) |
|----------|---------:|-----------:|-----------:|
| BAW178   |   35,000 |    0.27 km |   10.67 km |
| UAL415   |    8,175 |    2.42 km |    3.48 km |
| DAL336   |   18,500 |   25.17 km |   25.80 km |

The old code picks `BAW178` (35,000 ft — inaudible) as "nearest plane
overhead." That is the user's complaint.

### Fix: slant-range ranking + lower ceiling

1. **Rank by slant range** — true 3D distance — instead of horizontal distance.
   In `_row_to_plane`, compute the sort key as
   `hypot(horizontal_m, altitude_m)` where
   `horizontal_m = horizontal_deg * 111_320` and
   `altitude_m = alt_ft * 0.3048`. Low-and-near now beats high-and-overhead.
   `parse_aircraft` continues to sort ascending on this key.

2. **Lower the default audible ceiling 12,000 → 10,000 ft** in:
   - `config.py` (`SkyConfig.plane_max_alt_ft`)
   - `config.example.yaml` (value + comment)
   - `planes.py` `DEFAULT_MAX_ALT_FT` (the `SkyClient` default)
   - the stale "35,000 ft" code comment near the constant

The floor (1,000 ft) and 3 nm radius are unchanged.

### Test impact (intentional — validates the fix)

Under slant ranking, several existing assertions in `test_sky_planes.py`
correctly flip from `BAW178` (35k overhead) to `UAL415` (8,175 ft):

- `test_nearest_plane_picks_closest_airborne` — pick, alt, dir, route
  assertions updated to `UAL415` / 8175 / its track-derived dir.
- `test_nearest_plane_handles_adsb_lol_ac_key` — pick → `UAL415`.
- `test_fetch_overhead_primary_with_route` — pick → `UAL415`, route still
  resolves (route_fetcher is callsign-agnostic in the test).
- `test_fetch_overhead_falls_back_to_second_feed` — pick → `UAL415`.
- `test_fetch_overhead_keeps_plane_when_route_unavailable` — pick → `UAL415`.

These updates are reframed as *demonstrating the new behavior*: the 35,000 ft
jet that used to win no longer does.

New test:

- `test_nearest_plane_ranks_by_slant_not_horizontal` — inline data with a
  high plane near-overhead and a low plane slightly off-axis; assert the **low**
  plane is selected, even though the high one is horizontally closer. This is
  the direct regression lock for the audibility fix.

`test_max_altitude_keeps_only_audible_traffic` updated to use the new 10,000 ft
ceiling for consistency (still selects `UAL415`).

## Part 3 — Polish (sure things only)

- Fix the stale `LineAlert.reason` docstring examples (`"SIGNALS"`,
  `"SICK PASS"`) to match the actual labels emitted (e.g. `SIGNAL PROBLEM`,
  `SICK PASSENGER`).

No other behavioral changes. Direction filtering, the sign marquee, severity
selection, and feed fallback are out of scope and left untouched.

## Out of scope

- Reworking direction parsing or the marquee.
- Broad/speculative reason keywords (vandalism, person-on-tracks, etc.).
- Any new config surface beyond changing the existing ceiling default.

## Success criteria

- `parse_reason` never returns `ICE` for "service"/"office"/"notice"-type text.
- A real `Suspended`/`Reduced Service` alert renders as `SUSP`/`RDCD`
  (with a real reason when present), never `SUSP ICE`.
- The selected plane is the most audible (lowest slant range under the 10k
  ceiling), not the nearest-overhead high cruiser.
- Full suite green, including the new real-phrasing corpus and slant test.
