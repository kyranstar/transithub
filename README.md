# TransitHub

[![tests](https://github.com/kyranstar/transithub/actions/workflows/ci.yml/badge.svg)](https://github.com/kyranstar/transithub/actions/workflows/ci.yml)
![no API keys needed](https://img.shields.io/badge/API_keys-not_needed-2ea44f)

**Live NYC subway arrivals, weather, and a calm ambient layer — the sky, space, and your
neighborhood — on a Raspberry Pi LED matrix, styled like a real MTA sign.**

<p align="center">
  <img src="docs/preview.png" width="520" alt="L and M train countdowns on the LED sign">
</p>

TransitHub drives an Adafruit-bonnet 64×32 RGB LED panel as a real-time subway sign, then
quietly rotates in everything else worth a glance — animated weather, the ISS passing
overhead, a full moon, a farmers market open today — all from free, **keyless** APIs
(Open-Meteo, the MTA feeds, NASA EPIC, OpenSky, NYC Open Data). One thing on screen at a
time; the trains are always the backbone.

<p align="center">
  <img src="docs/ambient-scenes.png" width="100%" alt="A grid of scenes: weather, a GO OUTSIDE verdict, an L suspension with its reason, an ISS pass, a full moon, a farmers market, a park movie, humans in space, Earth from space, a plane overhead, and a keep-windows-closed air advisory">
</p>

## Highlights

### 🚇 Trains first
Real MTA GTFS-realtime arrivals (no key) for **any line, stop, and direction** you list,
**weighted** by screen time; **direction-aware** DLY / RDCD / SUSP badges that won't flag the
wrong way; clean countdowns that never show `0m` and flash `Now` on arrival. Disruptions now
say *why* — `SIGNALS`, `SICK PASS`, `FDNY`, `TRACK WORK` — parsed from the alert text.

### 🌦 Weather & advisories
An animated rundown matched to the **conditions and time of day** (sun, clouds, rain, snow,
fog, a night sky whose moon tracks the real lunar phase), today's high/low, a one-glance
verdict (**`GO OUTSIDE`** / **`STAY IN`**), and flags **only when they matter** — UV, AQI, a
precise **`RAIN til 2a`** window, and a **`WINDOWS / KEEP CLOSED`** nudge when the air is bad
or it's muggy — plus sunrise/sunset notices and a `TRASH TMRW` reminder.

### 🛰 Sky & space
The ISS gets a heads-up minutes before it crosses (**`ISS PASS · 8:43 · LOOK NW`**, computed
locally from a keyless TLE); a plane overhead gets an **`ABOVE YOU`** (OpenSky); the full and
new moon get a brief salute on the night they fall; and now and then — how many **humans are
in space**, or a fresh photo of **Earth from NASA's EPIC camera**.

### 🌳 Your block
A farmers market open **today** near home (**`MARKET TODAY · UNION SQ · UNTIL 6`**) and free,
outdoor events tonight or tomorrow (**`PARK MOVIE · 8 PM · TOMPKINS`**) — filtered to within a
few km of you, from NYC Open Data.

### 🌙 Calm by design, dim by night
One idea per screen on a priority + cooldown schedule, so nothing dominates and the trains
always get a breath (the [scene framework](docs/scene-framework.md) explains how). The panel
**dims gradually after sunset and a lot after bedtime**, and stale-data / offline warnings
stay invisible until something is genuinely wrong.

<p align="center">
  <img src="docs/before.gif" width="47%" alt="Before: trains and a basic weather rundown">
  <img src="docs/ambient-after.gif" width="47%" alt="After: the ambient rotation cycling weather, a suspension reason, an ISS pass, a full moon, a market, humans in space, and Earth">
</p>
<p align="center">
  <img src="docs/night-mode.gif" width="60%" alt="The panel fading from full daylight brightness down to a low night glow">
</p>
<p align="center"><sub><b>Before</b> (left) and <b>after</b> (right), then the evening dim-down.</sub></p>

### 🧩 Runs anywhere — and builds without hardware
Works on **Pi 3 / 4 / Zero 2 W**, installs and starts **headless on boot** (systemd), and
ships a PNG **simulator** that renders the exact frames on any computer — so you can develop
and preview with no Pi or panel attached. Correct NYC time even on a UTC Pi.

## Parts

| Part | Adafruit | Price |
|------|----------|-------|
| Raspberry Pi 3 Model B | [#3055](https://www.adafruit.com/product/3055) | $35.00 |
| 5V 2.5A micro-USB supply — powers the Pi | [#1995](https://www.adafruit.com/product/1995) | $8.25 |
| RGB Matrix Bonnet | [#3211](https://www.adafruit.com/product/3211) | $14.95 |
| 64×32 RGB LED matrix, 6mm pitch | [#2276](https://www.adafruit.com/product/2276) | $64.95 |
| 5V 4A power supply, UL-listed — drives the panel | [#1466](https://www.adafruit.com/product/1466) | $14.95 |
| **Total** | | **≈ $138** |

*Adafruit list prices (USD), before tax/shipping* — these are the convenient, known-good
versions, but you can spend far less by shopping around (a generic HUB75 panel, an old Pi you
already own, and any decent 5V supply). The only things you genuinely **need** are the **LED
matrix** and a **Raspberry Pi** — the bonnet is just tidy wiring (you can jumper the panel to
the Pi's GPIO by hand), and the second supply only matters once you push the panel bright.

You need **both** power supplies — the
panel pulls its 5V 4A from the bonnet's screw terminals while the Pi runs off its own
micro-USB supply. Any **Pi 3 / 4 / Pi Zero 2 W** works (Pi 5 isn't supported by the matrix
driver). Seat the bonnet on the Pi's GPIO header, plug the panel's ribbon + power into the
bonnet, and feed in the 5V 4A supply — see Adafruit's
[assembly guide](https://learn.adafruit.com/adafruit-rgb-matrix-bonnet-for-raspberry-pi). The
optional hardware-PWM jumper (see [Flicker tuning](#flicker-tuning)) is just a short wire.

## Install

On [Raspberry Pi OS Lite](https://www.raspberrypi.com/software/) **Bookworm or newer** (the
matrix binding needs Python 3.11+; enable SSH in the imager for headless):

```bash
git clone https://github.com/kyranstar/transithub.git
cd transithub && ./install.sh        # apt deps, builds the matrix binding, venv, config.yaml
sudo .venv/bin/transithub --config config.yaml   # sudo needed for GPIO timing
```

To start on every boot:

```bash
sudo cp systemd/transithub.service /etc/systemd/system/   # edit paths if not /home/pi/transithub
sudo systemctl enable --now transithub
journalctl -u transithub -f                               # logs
```

## Configure

Edit `config.yaml` (seeded from [`config.example.yaml`](config.example.yaml), which documents
every option). Stops look like:

```yaml
trains:
  - { line: "L", stop_id: "L16", direction: "N", weight: 3 }   # DeKalb Av → Manhattan
  - { line: "M", stop_id: "M08", direction: "N", weight: 1 }   # Myrtle-Wyckoff → Manhattan
```

The sign rotates between stops (each shows its next two trains); `weight` sets relative screen
time. Find IDs/directions with:

```bash
python scripts/find_station.py "dekalb"
# L16   DeKalb Av [L]  (Bk)    N -> Manhattan    S -> Canarsie - Rockaway Parkway
```

`config.example.yaml` also covers your `location`, `weather`, **`night`** dimming (bedtime +
how dim it gets), the **`sky`/`space`/`local`** ambient toggles (`local.radius_km` keeps
markets and events near home), `notifications`/`trash`, and the `matrix`/`display`/`alerts`
tuning knobs — every source stays keyless.

## Develop & preview (no hardware)

```bash
pip install -e ".[dev]"
python -m pytest                                          # all logic is hardware-independent
transithub --config config.example.yaml --simulate --once # renders one frame to preview.png
```

The code is a data layer (`mta/`, `weather/`), a rendering layer (`display/` — scenes, a
drawing kit, and pluggable backends), and a small `Director` that schedules scenes.

## Flicker tuning

**Run the helper first (all models)** — it disables on-board sound (the #1 cause) and isolates
a CPU core, then prompts to reboot:

```bash
./scripts/reduce-flicker.sh
```

Usually enough on a Pi 4. On slower boards, tune `config.yaml`'s `matrix:` block:

| Board | `gpio_slowdown` |
|-------|-----------------|
| Pi Zero / Pi 1 | `0`–`1` |
| Pi 2 / Pi 3 / Pi Zero 2 W | `1`–`2` |
| Pi 4 | `3`–`4` |

Also lower `pwm_bits` to `8`/`7` (higher refresh) and optionally `limit_refresh_rate_hz: 100`
(a steadier rate). Sweep live with the static test, then copy the winners into your config:

```bash
sudo .venv/bin/python scripts/panel-test.py --slowdown 1 --pwm-bits 8 --limit-refresh 100
```

**Definitive fix on a Pi 3 / Zero 2 W:** solder a jumper between **GPIO4 and GPIO18** on the
bonnet (see [Improving flicker](https://github.com/hzeller/rpi-rgb-led-matrix#improving-flicker)),
then set `hardware_mapping: adafruit-hat-pwm`.

## Troubleshooting

- **Nothing on the panel** — check `journalctl -u transithub -f`; confirm `sudo` and that
  `hardware_mapping` matches your bonnet.
- **A row says "No service"** — that line has no upcoming trains right now (e.g. a weekend
  service change); verify the stop/direction with `find_station.py`.
- **"No module named …" only under sudo/systemd** — run via the venv binary
  (`.venv/bin/transithub`); the app keeps root (`matrix.drop_privileges: false`) so it can read
  the venv/fonts under `$HOME`.

## Credits

**Libraries:** [hzeller/rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix)
(driver) · [Andrew-Dickinson/nyct-gtfs](https://github.com/Andrew-Dickinson/nyct-gtfs) (MTA
parsing) · [python-sgp4](https://github.com/brandon-rhodes/python-sgp4) (ISS orbit) ·
[spleen](https://github.com/fcambus/spleen) (font, BSD-2)

**Data, all keyless:** [Open-Meteo](https://open-meteo.com) (weather) ·
[MTA open data](https://www.mta.info/developers) · [Celestrak](https://celestrak.org) (ISS
TLE) · [OpenSky Network](https://opensky-network.org) (aircraft) ·
[NASA EPIC](https://epic.gsfc.nasa.gov) (Earth imagery) ·
[Open Notify](http://open-notify.org) (people in space) ·
[NYC Open Data](https://opendata.cityofnewyork.us) (markets & events)

## License

MIT — see [LICENSE](LICENSE).
