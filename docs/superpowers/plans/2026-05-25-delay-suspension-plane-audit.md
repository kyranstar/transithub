# Delay/Suspension Messaging + Plane Overhead — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kill the `SUSP ICE` false positive in the alert reason parser, pick the plane you'd actually hear (slant-range ranking + a 10,000 ft ceiling), and lock both with comprehensive real-result tests — the final commit before the repo is locked.

**Architecture:** Two independent, well-bounded modules. `mta/alerts.py` parses MTA alert prose into a short reason via an ordered keyword map; the fix swaps naive substring containment for left-anchored word-boundary regex and adds a few verified keywords. `sky/planes.py` selects the nearest airborne craft; the fix ranks by true 3D slant range instead of horizontal distance and lowers the audible ceiling. No other behavior changes.

**Tech Stack:** Python 3.13, stdlib `re` / `math`, pytest. Run tests from the repo root inside `.venv` (`source .venv/bin/activate`).

---

### Task 1: Reason parser — word-boundary matching + verified keywords

The substring matcher (`keyword in hay`) lets `"ice"` match the `serv·ice`
substring, so any *service*/*suspended* alert renders `SUSP ICE`. Switch to a
left-anchored word boundary and add a few high-confidence real MTA reasons.

**Files:**
- Modify: `src/transithub/mta/alerts.py` (the `_REASON_KEYWORDS` list ~lines 54-87, and `parse_reason` ~lines 114-132)
- Test: `tests/test_alerts.py`

- [ ] **Step 1: Write the failing tests**

Add `import pytest` at the top of `tests/test_alerts.py` (next to the existing
imports), then append these tests to the `-- reason parsing --` section:

```python
# Real-world MTA phrasings -> expected reason. The messaging must hold up against
# the actual prose the feed ships, not toy strings.
REAL_REASON_CASES = [
    ("Northbound [4] trains are delayed because of train traffic ahead of us.", "TRAIN TRAFFIC"),
    ("[A] trains are delayed while we address a mechanical problem on a train.", "MECHANICAL PROBLEM"),
    ("[2] trains are running with delays because of brake problems on a train.", "BRAKE PROBLEM"),
    ("[7] service is delayed because of a door problem on a train.", "DOOR PROBLEM"),
    ("[F] trains are delayed because of an earlier incident at Coney Island.", "EARLIER INCIDENT"),
    ("Trains are delayed due to a rail condition near the station.", "TRACK CONDITION"),
    ("[N] service is suspended because of a water main break in the area.", "FLOODING"),
    ("[Q] trains are delayed because of icy conditions on the tracks.", "ICE"),
    ("[L] trains are delayed because of a sick passenger at Bedford Av.", "SICK PASSENGER"),
    ("Trains are delayed due to an NYPD investigation.", "POLICE"),
    ("[M] trains are delayed while we address signal problems at Myrtle Av.", "SIGNAL PROBLEM"),
    ("[6] trains are delayed because of FDNY activity.", "FDNY"),
    ("[3] trains are delayed because of a switch problem.", "SWITCH PROBLEM"),
    ("[D] trains are delayed because of a disabled train ahead.", "STALLED TRAIN"),
    ("[B] trains are delayed because of a power problem.", "POWER PROBLEM"),
]


@pytest.mark.parametrize("text,expected", REAL_REASON_CASES)
def test_parse_reason_real_world_phrasings(text, expected):
    assert parse_reason(text) == expected


def test_parse_reason_ignores_service_substring():
    # The SUSP ICE bug: 'ice' must never match the 'serv·ice' (or office/notice) substring.
    assert parse_reason("No scheduled service is running on this line") == ""
    assert parse_reason("Service has been suspended") == ""
    assert parse_reason("We are providing reduced service") == ""
    assert parse_reason("Please notice the schedule change") == ""
    assert parse_reason("Visit us at our office") == ""


def test_parse_reason_matches_plurals_and_suffixes():
    # Left-anchored boundary still matches word continuations (the reason we don't
    # use a full \\bword\\b boundary, which would break these).
    assert parse_reason("we are addressing signal problems") == "SIGNAL PROBLEM"
    assert parse_reason("We're replacing tracks this weekend") == "TRACK WORK"
    assert parse_reason("delays because it is snowing heavily") == "SNOW"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_alerts.py -q`
Expected: FAIL — `test_parse_reason_ignores_service_substring` returns `"ICE"`
instead of `""`, and the new-keyword cases (train traffic, brake, door, earlier
incident, rail condition, water main, icy) return `""` instead of their labels.

- [ ] **Step 3: Add the verified keywords**

In `src/transithub/mta/alerts.py`, replace the `_REASON_KEYWORDS` list with the
version below (existing entries kept in order; new entries marked `# +`):

```python
_REASON_KEYWORDS: List[tuple[str, str]] = [
    ("sick passenger", "SICK PASSENGER"),
    ("sick customer", "SICK PASSENGER"),
    ("ill passenger", "SICK PASSENGER"),
    ("ill customer", "SICK PASSENGER"),
    ("nypd", "POLICE"),
    ("police", "POLICE"),
    ("fdny", "FDNY"),
    ("smoke", "SMOKE"),
    ("fire", "FIRE"),
    ("medical", "MEDICAL"),
    ("injury", "MEDICAL"),
    ("injured", "MEDICAL"),
    ("signal problem", "SIGNAL PROBLEM"),
    ("signal malfunction", "SIGNAL PROBLEM"),
    ("signal maintenance", "SIGNAL WORK"),
    ("signal", "SIGNAL PROBLEM"),
    ("switch", "SWITCH PROBLEM"),
    ("brake", "BRAKE PROBLEM"),               # +
    ("mechanical", "MECHANICAL PROBLEM"),
    ("door problem", "DOOR PROBLEM"),          # +
    ("disabled train", "STALLED TRAIN"),
    ("track maintenance", "TRACK WORK"),
    ("replacing track", "TRACK WORK"),
    ("track work", "TRACK WORK"),
    ("track condition", "TRACK CONDITION"),
    ("rail condition", "TRACK CONDITION"),     # +
    ("rubbish", "DEBRIS ON TRACK"),
    ("debris", "DEBRIS ON TRACK"),
    ("litter", "DEBRIS ON TRACK"),
    ("power", "POWER PROBLEM"),
    ("snow", "SNOW"),
    ("ice", "ICE"),
    ("icy", "ICE"),                            # +
    ("weather", "WEATHER"),
    ("flooding", "FLOODING"),
    ("water condition", "FLOODING"),
    ("water main", "FLOODING"),                # +
    ("train traffic", "TRAIN TRAFFIC"),        # +
    ("earlier incident", "EARLIER INCIDENT"),  # + (vague; kept last so specific reasons win)
]

# Precompiled left-anchored word-boundary patterns, in priority order. A LEFT
# boundary (not a full \bword\b) is deliberate: it stops 'ice' from matching
# 'serv·ice'/'office'/'notice' while still matching word continuations like
# 'signal problem(s)' and 'snow(ing)'.
_REASON_PATTERNS: List[tuple[re.Pattern, str]] = [
    (re.compile(r"\b" + re.escape(kw)), label) for kw, label in _REASON_KEYWORDS
]
```

- [ ] **Step 4: Switch `parse_reason` to the compiled patterns**

In the same file, change the matching loop in `parse_reason` from substring
containment to the precompiled patterns:

```python
    for hay in haystacks:
        for pattern, label in _REASON_PATTERNS:
            if pattern.search(hay):
                return label
    return ""
```

(Only the inner loop changes — the `_WHATS_HAPPENING_RE` handling and the
`haystacks` construction above it stay exactly as they are.)

- [ ] **Step 5: Run the full alerts suite to verify it passes**

Run: `source .venv/bin/activate && python -m pytest tests/test_alerts.py -q`
Expected: PASS — all new tests green AND every pre-existing `test_alerts.py`
test still green (the specific-wins-over-generic ordering is preserved).

- [ ] **Step 6: Commit**

```bash
git add src/transithub/mta/alerts.py tests/test_alerts.py
git commit -m "Fix SUSP ICE: word-boundary reason matching + verified MTA reasons"
```

---

### Task 2: End-to-end messaging tests (real feed shape -> rendered message)

Prove the fix survives the full pipeline: a real-shaped alert entity flows
through `alerts_for_trains` to the exact `tag`/`reason` the sign renders. Uses
the existing `_alert`/`_client` helpers, which build the real feed entity shape
(`informed_entity`, `active_period`, `mercury_alert`, translated `header_text`)
— so this exercises the real path without mutating the shared fixture and
risking its index-based assertions.

**Files:**
- Test: `tests/test_alerts.py`

- [ ] **Step 1: Write the failing tests**

Append to the `-- alerts_for_trains` section of `tests/test_alerts.py`:

```python
def test_full_message_real_alert_train_traffic():
    c = _client([_alert(["L"], "Delays",
        "Northbound [L] trains are delayed because of train traffic ahead of us.")])
    [a] = c.alerts_for_trains([L_N], now=NOW)
    assert a is not None and a.tag == "DLY" and a.reason == "TRAIN TRAFFIC"


def test_full_message_suspended_service_is_not_ice():
    # The exact failure the user saw: a suspension whose text only says "service"
    # must render SUSP, never SUSP ICE.
    c = _client([_alert(["M"], "Planned - Suspended",
        "[M] service is suspended. Take the [J] and free shuttle buses instead.")])
    [a] = c.alerts_for_trains([M_N], now=NOW)
    assert a is not None and a.tag == "SUSP" and a.reason == ""


def test_full_message_reduced_service_brake_problem():
    c = _client([_alert(["M"], "Reduced Service",
        "[M] trains are running with delays because of brake problems on a train.")])
    [a] = c.alerts_for_trains([M_N], now=NOW)
    assert a is not None and a.tag == "RDCD" and a.reason == "BRAKE PROBLEM"
```

- [ ] **Step 2: Run to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_alerts.py -q`
Expected: PASS — Task 1's parser change already makes these green; they lock the
end-to-end behavior. (If `test_full_message_suspended_service_is_not_ice` fails
with `reason == "ICE"`, Task 1's boundary fix was not applied.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_alerts.py
git commit -m "Test: end-to-end alert messaging on real feed shapes"
```

---

### Task 3: Plane selection — rank by slant range, not horizontal distance

`_row_to_plane` returns horizontal distance as the sort key, so a 35,000 ft jet
near-overhead beats a 2,000 ft plane slightly off-axis. Rank by true 3D slant
range so the audible (low, near) plane wins.

**Files:**
- Modify: `src/transithub/sky/planes.py` (`_row_to_plane`, the distance block ~lines 152-159)
- Test: `tests/test_sky_planes.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_sky_planes.py` after `test_nearest_plane_picks_closest_airborne`:

```python
def test_nearest_plane_ranks_by_slant_not_horizontal():
    # A high jet nearly overhead vs a low plane slightly off-axis. Horizontal
    # distance favors the high one; slant range (and audibility) favors the low one.
    data = {"aircraft": [
        {"flight": "HIGH1", "alt_baro": 35000, "track": 90.0,
         "lat": LAT + 0.002, "lon": LON},   # ~0.2 km horizontally, but 35,000 ft up
        {"flight": "LOW1", "alt_baro": 2000, "track": 90.0,
         "lat": LAT + 0.02, "lon": LON},    # ~2.2 km horizontally, but only 2,000 ft up
    ]}
    p = nearest_plane(data, LAT, LON, min_alt_ft=1000)
    assert p is not None and p.callsign == "LOW1"
```

- [ ] **Step 2: Run to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/test_sky_planes.py::test_nearest_plane_ranks_by_slant_not_horizontal -q`
Expected: FAIL — current horizontal ranking picks `HIGH1` (0.2 km), so the
assertion `callsign == "LOW1"` fails.

- [ ] **Step 3: Switch the sort key to slant range**

In `src/transithub/sky/planes.py`, replace the distance block at the end of
`_row_to_plane` (the `# planar distance in degrees...` comment through
`return dist, plane`) with:

```python
        # Rank by slant range (true 3D distance), so a low, near plane beats a high
        # one passing overhead — the low one is the one you'd actually hear. Horizontal
        # offset is planar (longitude scaled by latitude); both legs converted to metres
        # (~111,320 m per degree of latitude, 0.3048 m per foot).
        dlat = plat - lat
        dlon = (plon - lon) * math.cos(math.radians(lat))
        horizontal_m = math.hypot(dlat, dlon) * 111_320
        slant_m = math.hypot(horizontal_m, alt_ft * 0.3048)
        plane = Plane(callsign=callsign, alt_ft=int(round(alt_ft)),
                      heading_deg=heading, dir=_heading_to_compass(heading))
        return slant_m, plane
```

(`parse_aircraft`'s `found.sort(key=lambda dp: dp[0])` already sorts ascending
on this key — no change needed there.)

- [ ] **Step 4: Update the existing assertions that intentionally flip**

Under slant ranking, the fixture's 35,000 ft `BAW178` no longer wins; the
8,175 ft `UAL415` (track 218° → `SW`) does. Update these tests in
`tests/test_sky_planes.py`:

Replace `test_nearest_plane_picks_closest_airborne` with:

```python
def test_nearest_plane_picks_closest_airborne():
    # Slant-range ranking: the 8,175 ft UAL415 (the audible one) beats the
    # 35,000 ft BAW178 that is nearer in horizontal distance but inaudible overhead.
    p = nearest_plane(ADSB, LAT, LON, min_alt_ft=1000)
    assert isinstance(p, Plane)
    assert p.callsign == "UAL415"            # smallest slant range above the floor
    assert p.dir == "SW"                     # track 218 deg
    assert p.alt_ft == 8175                  # alt_baro is feet already
    assert 0 <= p.heading_deg < 360
    assert p.route is None                   # parsing alone does not add a route
```

In `test_nearest_plane_handles_adsb_lol_ac_key`, change the final assertion to:

```python
    assert p is not None and p.callsign == "UAL415"
```

In `test_fetch_overhead_primary_with_route`, change to:

```python
    assert p.callsign == "UAL415" and p.route == "JFK > LHR"
```

In `test_fetch_overhead_falls_back_to_second_feed`, change the final assertion to:

```python
    p = fetch_overhead(LAT, LON, fetcher=flaky, route_fetcher=lambda url: ROUTE)
    assert p is not None and p.callsign == "UAL415"
```

In `test_fetch_overhead_keeps_plane_when_route_unavailable`, change to:

```python
    assert p is not None and p.callsign == "UAL415" and p.route is None
```

- [ ] **Step 5: Run the full plane suite to verify it passes**

Run: `source .venv/bin/activate && python -m pytest tests/test_sky_planes.py -q`
Expected: PASS — the new slant test, the flipped assertions, and the unchanged
tests (`test_parse_skips_ground_low_and_null_alt`,
`test_max_altitude_keeps_only_audible_traffic`, etc.) all green.

- [ ] **Step 6: Commit**

```bash
git add src/transithub/sky/planes.py tests/test_sky_planes.py
git commit -m "Planes: rank by slant range so the audible plane wins, not the high cruiser"
```

---

### Task 4: Lower the audible ceiling to 10,000 ft

12,000 ft is generous for "audible". Drop the default ceiling to 10,000 ft
across the constant, the config default, and the example config.

**Files:**
- Modify: `src/transithub/sky/planes.py` (`DEFAULT_MAX_ALT_FT` + comment ~lines 38-40)
- Modify: `src/transithub/config.py` (`SkyConfig.plane_max_alt_ft` line 79)
- Modify: `config.example.yaml` (line 58)
- Test: `tests/test_sky_planes.py`

- [ ] **Step 1: Update the test to the new ceiling**

In `tests/test_sky_planes.py`, `test_max_altitude_keeps_only_audible_traffic`
currently passes `max_alt_ft=12000` in two calls. Change both to `10000`:

```python
def test_max_altitude_keeps_only_audible_traffic():
    # With an audibility ceiling, the high cruisers (BAW178 35000, DAL336 18500) drop
    # and the low climbing/descending plane (UAL415 8175) becomes the one overhead —
    # so the scene tracks a plane you could actually hear, not a jet at cruise.
    p = nearest_plane(ADSB, LAT, LON, min_alt_ft=1000, max_alt_ft=10000)
    assert p is not None and p.callsign == "UAL415" and p.alt_ft == 8175
    cs = {x.callsign for x in parse_aircraft(ADSB, LAT, LON, min_alt_ft=1000,
                                             max_alt_ft=10000)}
    assert "BAW178" not in cs and "DAL336" not in cs
```

- [ ] **Step 2: Run to confirm it still passes (UAL415 is below 10k)**

Run: `source .venv/bin/activate && python -m pytest tests/test_sky_planes.py::test_max_altitude_keeps_only_audible_traffic -q`
Expected: PASS — UAL415 at 8,175 ft is below the new 10,000 ft ceiling.

- [ ] **Step 3: Lower `DEFAULT_MAX_ALT_FT`**

In `src/transithub/sky/planes.py`, change the constant and its comment:

```python
# Only count planes low enough to actually hear, so "overhead" tracks what you'd
# notice outside — a jet at cruise (~35,000 ft) is constant but inaudible. 10,000 ft
# is a sensible ceiling for traffic you'd notice from the ground.
DEFAULT_MAX_ALT_FT = 10000
```

- [ ] **Step 4: Lower the config default**

In `src/transithub/config.py` line 79:

```python
    plane_max_alt_ft: int = 10000   # only planes below this (low, audible) count
```

- [ ] **Step 5: Lower the example config**

In `config.example.yaml` line 58:

```yaml
  plane_max_alt_ft: 10000    # only planes below this count — i.e. low enough to actually hear
```

- [ ] **Step 6: Run the full suite**

Run: `source .venv/bin/activate && python -m pytest -q`
Expected: PASS — all tests green (config + planes).

- [ ] **Step 7: Commit**

```bash
git add src/transithub/sky/planes.py src/transithub/config.py config.example.yaml tests/test_sky_planes.py
git commit -m "Planes: lower default audible ceiling 12000 -> 10000 ft"
```

---

### Task 5: Polish — fix the stale `LineAlert.reason` docstring

The docstring cites labels (`"SIGNALS"`, `"SICK PASS"`) the code never emits.

**Files:**
- Modify: `src/transithub/mta/alerts.py` (`LineAlert` docstring ~lines 181-190)

- [ ] **Step 1: Update the docstring examples to real labels**

In `src/transithub/mta/alerts.py`, change the `LineAlert` docstring's reason
examples:

```python
@dataclass(frozen=True)
class LineAlert:
    """One disruption affecting a tracked stop.

    `tag` is the glanceable badge (DLY/RDCD/SUSP); `reason` is a short cause phrase
    (e.g. "SIGNAL PROBLEM", "SICK PASSENGER") or "" when the cause isn't recognized.
    """
```

- [ ] **Step 2: Run the full suite (no behavior change expected)**

Run: `source .venv/bin/activate && python -m pytest -q`
Expected: PASS — docstring-only change; full suite green.

- [ ] **Step 3: Commit**

```bash
git add src/transithub/mta/alerts.py
git commit -m "Docs: correct LineAlert.reason examples to the labels actually emitted"
```

---

### Task 6: Final verification

- [ ] **Step 1: Run the entire suite and confirm it is fully green**

Run: `source .venv/bin/activate && python -m pytest -q`
Expected: PASS — the original 293 tests plus the new messaging-corpus and
slant tests, with the intentionally-flipped plane assertions updated.

- [ ] **Step 2: Manually sanity-check the original bug is dead**

Run:
```bash
source .venv/bin/activate && python -c "
from transithub.mta.alerts import parse_reason
for t in ['No scheduled service is running', 'Service has been suspended', 'because of train traffic ahead', 'icy conditions on the rail']:
    print(repr(t), '->', repr(parse_reason(t)))
"
```
Expected: the two `service` strings → `''`, `train traffic` → `'TRAIN TRAFFIC'`,
`icy` → `'ICE'`.

---

## Self-Review

**Spec coverage:**
- Part 1 reason word-boundary fix → Task 1 (steps 3-4). ✓
- Part 1 keyword additions (all 7) → Task 1 (step 3). ✓
- Part 1 real-result tests (corpus, false-positive guards, plurals, end-to-end) → Tasks 1 & 2. ✓
- Part 2 slant-range ranking → Task 3. ✓
- Part 2 ceiling 12000→10000 (config, example, constant, comment) → Task 4. ✓
- Part 2 flipped assertions + new slant test → Task 3 (steps 1, 4). ✓
- Part 3 docstring fix → Task 5. ✓

**Deliberate deviation from spec:** The spec proposed extending
`tests/fixtures/alerts_sample.json` with new entities. Task 2 instead uses the
existing `_alert`/`_client` helpers, which already build the exact real feed
entity shape — equally "real," but zero risk to the fixture's index-based
assertions ([1], [6], Q05, etc.). The end-to-end requirement is fully met.

**Placeholder scan:** No TBD/TODO/"handle edge cases"; every code step shows
complete code and every run step shows the exact command + expected result.

**Type/name consistency:** `parse_reason`, `_REASON_KEYWORDS`,
`_REASON_PATTERNS`, `_row_to_plane`, `nearest_plane`, `parse_aircraft`,
`fetch_overhead`, `DEFAULT_MAX_ALT_FT`, `plane_max_alt_ft`, `LineAlert` all match
the current source. UAL415 → dir `SW` (track 218°), alt 8175 — verified against
the fixture.
