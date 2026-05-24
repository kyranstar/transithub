# TransitHub

[![tests](https://github.com/kyranstar/transithub/actions/workflows/ci.yml/badge.svg)](https://github.com/kyranstar/transithub/actions/workflows/ci.yml)

**Live NYC subway arrivals on a Raspberry Pi LED matrix, styled like a real MTA sign.**

<p align="center">
  <img src="docs/preview.png" alt="TransitHub showing the L train to 8 Av in 2 min and the M to Manhattan in 8 min" width="560">
</p>

TransitHub turns an Adafruit RGB Matrix Bonnet and a 64×32 LED panel into a countdown
clock for the subway lines you actually take. Each line you configure gets a row — its
colored **bullet**, the **destination**, and the **minutes** to the next train — counting
down in real time and flashing **`Now`** as the train pulls in, exactly like the signs in
the station. It pulls directly from the MTA's public real-time feeds, so there's no API
key and nothing to sign up for.

---

## Features

- **Real arrivals** from the MTA GTFS-realtime feeds — no API key required.
- **Authentic sign behavior** — official bullet colors, live countdown, flashing on
  arrival, destinations that scroll when too long, and paging when you track more lines
  than fit on screen.
- **Service alerts** — when a tracked line is delayed, running reduced, or suspended, its
  row flashes a `DLY` / `RDCD` / `SUSP` badge (straight from the MTA alerts feed), and it's
  **direction-aware**: a "Canarsie-bound delays" alert won't flag your Manhattan-bound stop.
- **Weather & notifications** — every 15 min an animated weather rundown interrupts the
  trains: a scene matched to the conditions + time of day (sun/clouds/rain/snow, day/night),
  then the current temp, today's high/low, and *only-when-notable* flags (UV, AQI,
  rain/snow likelihood, and `TRASH TMRW`). Plus animated sunrise/sunset notices. Free
  [Open-Meteo](https://open-meteo.com), no key.
- **Any line, any stop** — configure trains in a few lines of YAML; a helper finds the
  stop IDs for you.
- **Runs headless** — install once and it starts on boot with no monitor attached.
- **Preview without hardware** — a built-in simulator renders frames to a PNG so you can
  tweak your config from any computer.

## Hardware

| Part | Notes |
|------|-------|
| Raspberry Pi | Pi 3 / Pi 4 / Pi Zero 2 W all work |
| [Adafruit RGB Matrix Bonnet](https://www.adafruit.com/product/3211) | the default wiring TransitHub assumes |
| One 64×32 RGB LED matrix | e.g. Adafruit #2279 |
| 5V power supply (≥3A) | powers the panel through the bonnet |

Seat the bonnet on the Pi's GPIO header, plug the panel's data ribbon and power into the
bonnet, and feed 5V in. See Adafruit's
[bonnet assembly guide](https://learn.adafruit.com/adafruit-rgb-matrix-bonnet-for-raspberry-pi)
for the one-time soldering/jumper steps.

## Install

On a fresh [Raspberry Pi OS Lite](https://www.raspberrypi.com/software/) — Bookworm or
newer, since the matrix binding needs Python 3.11+ (enable SSH in the imager for a
headless setup) — then:

```bash
git clone https://github.com/kyranstar/transithub.git
cd transithub
./install.sh
```

`install.sh` installs system packages, builds the
[rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix) bindings, creates a
virtualenv, installs TransitHub, and copies `config.example.yaml` to `config.yaml`.

## Run

```bash
sudo .venv/bin/transithub --config config.yaml
```

`sudo` is required — the matrix needs precise GPIO timing. Press `Ctrl-C` to stop.

## Configure

Edit `config.yaml`. It ships tracking the **L at DeKalb Av toward Manhattan** and the
**M at Myrtle-Wyckoff Avs**:

```yaml
trains:
  - line: "L"
    stop_id: "L16"      # DeKalb Av
    direction: "N"      # toward Manhattan (8 Av)
    destination: ""     # blank = live destination; or set a short label
    weight: 3           # ~75% of screen time
  - line: "M"
    stop_id: "M08"      # Myrtle-Wyckoff Avs
    direction: "N"      # toward Manhattan
    destination: ""
    weight: 1           # ~25% of screen time
```

The sign rotates between the stops you list; whichever is showing fills the screen with
its **next two trains**. Each stop's `weight` is its relative share of screen time —
weights of `3` and `1` give the L ~75% and the M ~25% (omit `weight` for an equal split).
Add a stop by adding a list entry. To find the `stop_id` and which direction is which
for any station:

```bash
python scripts/find_station.py "dekalb"
# L16   DeKalb Av [L]  (Bk)
#         N -> Manhattan
#         S -> Canarsie - Rockaway Parkway
```

Other settings: panel `brightness` and `gpio_slowdown`, MTA `poll_seconds`, the
`arriving_threshold_seconds` for when a train flips to flashing `Now` (under 20s by
default; it never shows `0m` — anything below two minutes reads `1m`), and `page_seconds`
(the base airtime for a weight-1 stop in the rotation). The `alerts` block (`enabled`,
`poll_seconds`) toggles the disruption badge; only delays, reduced service, and
suspensions trigger it, so routine planned work doesn't.

**Weather & notifications.** Set your `location` (lat/lon) and `weather` options
(`units`, how often the rundown plays via `rundown_every_minutes`/`rundown_seconds`).
`notifications` toggles the sunrise/sunset notices; `trash.days` lists your pickup
weekday(s) so `TRASH TMRW` shows from 3pm the day before. It's the free Open-Meteo API —
no key. Flags appear only when notable: UV at index ≥6/8/11, AQI at ≥101 (US AQI
"unhealthy"), and precipitation — the soonest (or ongoing) window at ≥30% chance with its
peak chance and total amount, e.g. `RAIN 6p-2a` / `97%  2.0in`, or `RAIN til 6p` when it's
already coming down (`SNOW …` for snow).

> TransitHub uses New York time internally, so the countdown is correct even if your Pi's
> clock is set to UTC.

## Run at startup (headless)

```bash
sudo cp systemd/transithub.service /etc/systemd/system/
sudo systemctl enable --now transithub
```

It now starts on every boot, no monitor needed. Useful commands:

```bash
journalctl -u transithub -f      # follow logs
sudo systemctl restart transithub
sudo systemctl disable --now transithub
```

Edit the paths in `systemd/transithub.service` if you cloned somewhere other than
`/home/pi/transithub`.

## Preview without hardware

On any machine (no Pi or panel needed):

```bash
pip install -e .
transithub --config config.example.yaml --simulate --once
open preview.png        # a scaled image of one frame
```

Drop `--once` to keep refreshing the PNG live.

## Recommended Pi tweaks (flicker)

**Step 1 — run the helper (all models).** It disables the on-board sound (the #1 flicker
cause — its PWM hardware fights the panel) and isolates a CPU core for the refresh thread,
then prompts to reboot:

```bash
./scripts/reduce-flicker.sh
```

On a **Pi 4** that's usually all you need. On slower boards, also tune the `matrix:` block of
`config.yaml`:

**Step 2 — `gpio_slowdown`.** How hard the library slows GPIO writes so the panel keeps up.
Too low → scattered/torn lines; too high → lower refresh. Match your board:

| Board | `gpio_slowdown` |
|-------|-----------------|
| Pi Zero / Pi 1 | `0`–`1` |
| Pi 2 / Pi 3 / Pi Zero 2 W | `1`–`2` |
| Pi 4 | `3`–`4` |

**Step 3 — refresh.** Lower `pwm_bits` to `8` or `7` (raises the refresh rate; costs a little
color smoothness — fine for text/bullets), and optionally set `limit_refresh_rate_hz: 100` to
hold a *steady* rate (a refresh that bounces flickers even when the average is high). Find a
combo live with the static test pattern (no app logic — it prints the achieved Hz):

```bash
sudo .venv/bin/python scripts/panel-test.py --slowdown 1 --pwm-bits 8 --limit-refresh 100
```
Sweep `--slowdown` / `--pwm-bits` until it's rock-steady, then copy the winners into `config.yaml`.

**Step 4 — hardware-PWM mod (the definitive fix, especially Pi 3 / Pi Zero 2 W).** If software
tuning can't fully steady it, the bonnet's *software* PWM is the limit. Solder a jumper between
**GPIO4 and GPIO18** on the bonnet (see the rpi-rgb-led-matrix
[Improving flicker](https://github.com/hzeller/rpi-rgb-led-matrix#improving-flicker) section),
then set:

```yaml
matrix:
  hardware_mapping: adafruit-hat-pwm   # was adafruit-hat
```

This moves PWM into the Pi's hardware peripheral — immune to CPU scheduling jitter — and
essentially eliminates flicker.

> **Pi 5 is not supported** by rpi-rgb-led-matrix (its new RP1 GPIO controller is incompatible
> with the library's direct GPIO access). Use a Pi 4 or earlier.

## Development

```bash
pip install -e ".[dev]"
python -m pytest
```

All display and data logic is unit-tested and hardware-independent; the LED matrix is the
only piece that needs the Pi. The code is organized as a data layer (`mta/`, `weather/`), a
rendering layer (`display/` — scenes, a drawing kit, and pluggable display backends), and a
small `Director` that schedules scenes; the simulator backend lets you develop without
hardware.

## Troubleshooting

- **Nothing on the panel** — check `journalctl -u transithub -f`; confirm you ran with
  `sudo` and that `hardware_mapping: adafruit-hat` matches your bonnet.
- **Flicker** — run `./scripts/reduce-flicker.sh` (disables on-board sound + isolates a core, then reboots); if it persists, lower `pwm_bits` and fix `gpio_slowdown` for your Pi (`scripts/panel-test.py` helps you find the combo); the hardware-PWM jumper is the definitive fix on a Pi 3.
- **A row says "No service"** — that line has no upcoming trains right now (e.g. the M on
  a weekend). Verify the stop/direction with `find_station.py`.
- **"No module named …" or font errors only under `sudo`/systemd** — the matrix library
  drops root to the `daemon` user after init by default, which then can't read the venv
  or fonts under your home directory. TransitHub disables that with
  `matrix.drop_privileges: false` so it keeps root; if you'd rather keep the drop, install
  somewhere `daemon` can read.
- **Wrong direction** — re-run `find_station.py` and swap `direction` between `N` and `S`.

## Credits

- [hzeller/rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix) — LED matrix driver
- [Andrew-Dickinson/nyct-gtfs](https://github.com/Andrew-Dickinson/nyct-gtfs) — MTA real-time parsing
- [spleen](https://github.com/fcambus/spleen) — the bitmap font (BSD-2-Clause)
- [MTA open data](https://www.mta.info/developers) — the real-time feeds and station data

## License

MIT — see [LICENSE](LICENSE).
