import argparse
import sys
import threading
import time
from datetime import time as TimeOfDay

from .clock import now as now_eastern
from .config import load_config
from .health import HealthMonitor
from .local import EventsClient, LocalHolder, MarketsClient
from .mta.alerts import AlertsClient
from .mta.feed import FeedClient, feed_dependency_available
from .profile import Profile, day_profile
from .sky import SkyClient, SkyData
from .sky.client import POLL_INTERVALS as SKY_POLL
from .space import SpaceClient, SpaceData
from .store import ArrivalStore, Holder, WeatherHolder
from .weather.client import WeatherClient
from .display.sign import SignRenderer
from .display.simulator import SimulatorDisplay
from .display.director import Context, Director, Slot
from .display.dimmer import Dimmer
from .display.sources import HealthSource, SunEventSource, WeatherRundownSource
from .display.scenes.alert import AlertSource
from .display.scenes.local import EventSource, MarketSource
from .display.scenes.sky import IssPassSource, MoonEventSource, PlaneOverheadSource
from .display.scenes.space import EarthFromSpaceSource, HumansInSpaceSource
from .display.scenes.trains import TrainScene
from .display.scenes.weather import WeatherScene
from .display.scenes.sun_event import SunEventScene

HUMANS_POLL_S = 30 * 60
EARTH_POLL_S = 60 * 60
LOCAL_POLL_S = 6 * 3600


def _poller(stop_event, store, client, trains, poll_seconds, health=None):
    while not stop_event.is_set():
        ok = False
        for i, train in enumerate(trains):
            try:
                store.set(i, client.get_next_arrivals(train, count=2))
                ok = True
            except Exception as exc:  # keep last good data, keep running
                print(f"[poll] {train.line} {train.gtfs_stop_id}: {exc}")
        if health is not None:
            (health.ok if ok else health.fail)("arrivals")
        stop_event.wait(poll_seconds)


def _alerts_poller(stop_event, store, client, trains, poll_seconds, health=None):
    while not stop_event.is_set():
        try:
            line_alerts = client.alerts_for_trains(trains)
            store.set_line_alerts(line_alerts)
            store.set_alerts([a.tag if a else None for a in line_alerts])
            if health is not None:
                health.ok("alerts")
        except Exception as exc:  # keep last good tags, keep running
            print(f"[alerts] {exc}")
            if health is not None:
                health.fail("alerts")
        stop_event.wait(poll_seconds)


def _weather_poller(stop_event, holder, client, poll_seconds, health=None):
    while not stop_event.is_set():
        try:
            holder.set(client.fetch())
            if health is not None:
                health.ok("weather")
        except Exception as exc:  # keep last good weather, keep running
            print(f"[weather] {exc}")
            if health is not None:
                health.fail("weather")
        stop_event.wait(poll_seconds)


def _sky_poller(stop_event, holder, client):
    """Planes refresh fast (one is overhead for seconds); the ISS pass is good for
    minutes. Both degrade to None on error — best-effort, never noisy."""
    iss = None
    last_iss = None
    while not stop_event.is_set():
        try:
            plane = client.plane_overhead()
        except Exception as exc:
            print(f"[sky] plane: {exc}")
            plane = None
        mono = time.monotonic()
        if last_iss is None or mono - last_iss >= SKY_POLL["iss"]:
            try:
                iss = client.iss_pass()
                last_iss = mono
            except Exception as exc:
                print(f"[sky] iss: {exc}")
        holder.set(SkyData(next_iss_pass=iss, plane_overhead=plane))
        stop_event.wait(SKY_POLL["plane"])


def _space_poller(stop_event, holder, client):
    humans = earth = None
    last_h = last_e = None
    while not stop_event.is_set():
        mono = time.monotonic()
        if last_h is None or mono - last_h >= HUMANS_POLL_S:
            try:
                humans = client.humans()
                last_h = mono
            except Exception as exc:
                print(f"[space] humans: {exc}")
        if last_e is None or mono - last_e >= EARTH_POLL_S:
            try:
                earth = client.earth()
                last_e = mono
            except Exception as exc:
                print(f"[space] earth: {exc}")
        holder.set(SpaceData(humans=humans, earth=earth))
        stop_event.wait(60)


def _local_poller(stop_event, holder):
    while not stop_event.is_set():
        try:
            holder.poll()
        except Exception as exc:
            print(f"[local] {exc}")
        stop_event.wait(LOCAL_POLL_S)


def _make_display(cfg, args):
    if args.simulate:
        return SimulatorDisplay(args.simulate_out, scale=args.scale)
    try:
        from .display.matrix import RGBMatrixDisplay
        return RGBMatrixDisplay(cfg.matrix)
    except Exception as exc:
        print(f"[display] matrix unavailable ({exc}); using simulator")
        return SimulatorDisplay(args.simulate_out, scale=args.scale)


def _bedtime(cfg) -> TimeOfDay:
    try:
        hh, mm = cfg.night.bedtime.split(":")
        return TimeOfDay(int(hh), int(mm))
    except Exception:
        return TimeOfDay(21, 30)


def _build_director(cfg, renderer, store, holders, health):
    """Assemble the whole schedule in one readable place. `holders` is a dict of
    the background snapshots: weather, sky, space, local. See docs/scene-framework.md
    for the priority/cooldown rationale."""
    cols, rows = cfg.matrix.cols, cfg.matrix.rows
    bedtime = _bedtime(cfg)
    weather_holder = holders["weather"]
    DAY_EVENING = frozenset({Profile.DAY, Profile.EVENING})
    AFTER_DARK = frozenset({Profile.EVENING, Profile.NIGHT})

    def make_weather(w, now, lean):
        return WeatherScene(w, now, rounds=cfg.weather.rundown_rounds, lean=lean,
                            cols=cols, rows=rows, trash_days=cfg.trash.days)

    def make_sun(kind, t):
        return SunEventScene(kind, t, cols, rows)

    # Highest priority first; see the priority bands in docs/scene-framework.md.
    slots = [Slot(HealthSource(cols, rows), priority=100, cooldown_ms=120_000,
                  takeover=True, interjection=False)]
    if cfg.sky.enabled:
        slots += [
            Slot(IssPassSource(cols, rows), priority=90, cooldown_ms=75_000,
                 takeover=True, interjection=False),
            Slot(PlaneOverheadSource(cols, rows), priority=85, cooldown_ms=45_000,
                 takeover=True, interjection=False),
            Slot(MoonEventSource(cols, rows), priority=80, cooldown_ms=12 * 3_600_000,
                 takeover=False, interjection=False, profiles=AFTER_DARK),
        ]
    if cfg.alerts.enabled:
        slots.append(Slot(AlertSource(store.line_alerts, cols, rows),
                          priority=70, cooldown_ms=90_000))
    if cfg.notifications.sunrise or cfg.notifications.sunset:
        slots.append(Slot(SunEventSource(make_sun, cfg.notifications.sunrise,
                                         cfg.notifications.sunset),
                          priority=60, interjection=False))
    if cfg.weather.enabled:
        slots.append(Slot(WeatherRundownSource(make_weather), priority=50,
                          cooldown_ms=cfg.weather.rundown_every_minutes * 60_000,
                          first_after_ms=30_000))
    if cfg.local.enabled:
        slots += [
            Slot(MarketSource(cols, rows), priority=40, cooldown_ms=30 * 60_000,
                 first_after_ms=3 * 60_000, profiles=DAY_EVENING),
            Slot(EventSource(cols, rows), priority=40, cooldown_ms=30 * 60_000,
                 first_after_ms=5 * 60_000, profiles=DAY_EVENING),
        ]
    if cfg.space.enabled:
        slots += [
            Slot(HumansInSpaceSource(cols, rows), priority=30,
                 cooldown_ms=45 * 60_000, first_after_ms=4 * 60_000),
            Slot(EarthFromSpaceSource(cols, rows), priority=30,
                 cooldown_ms=60 * 60_000, first_after_ms=6 * 60_000),
        ]

    def context_builder(now, mono_ms):
        w = weather_holder.get()
        return Context(now=now, mono_ms=mono_ms, profile=day_profile(now, w, bedtime),
                       weather=w, sky=holders["sky"].get(), space=holders["space"].get(),
                       local=holders["local"].current, health=tuple(health.warnings()))

    dimmer = Dimmer(evening_floor=cfg.night.evening_brightness,
                    night_floor=cfg.night.night_brightness, bedtime=bedtime)
    return Director(TrainScene(renderer, store), slots,
                    context_builder=context_builder, dimmer=dimmer)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="transithub")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--simulate", action="store_true",
                        help="force the PNG simulator instead of the matrix")
    parser.add_argument("--simulate-out", default="preview.png")
    parser.add_argument("--scale", type=int, default=10)
    parser.add_argument("--fps", type=int, default=20)
    parser.add_argument("--once", action="store_true",
                        help="poll once, render a single frame, then exit")
    args = parser.parse_args(argv)

    if not feed_dependency_available():
        print(
            "ERROR: 'nyct_gtfs' is not installed in this Python environment, so no "
            "arrivals can be fetched.\nRun TransitHub from its virtualenv so it finds "
            "its dependencies, e.g.:\n"
            "  sudo /path/to/transithub/.venv/bin/transithub --config config.yaml\n"
            "or reinstall with ./install.sh.",
            file=sys.stderr,
        )
        return 1

    cfg = load_config(args.config)
    client = FeedClient()
    store = ArrivalStore(len(cfg.trains))
    renderer = SignRenderer(cfg)
    display = _make_display(cfg, args)
    alerts_client = AlertsClient() if cfg.alerts.enabled else None
    health = HealthMonitor()

    holders = {
        "weather": WeatherHolder(),
        "sky": Holder(SkyData()),
        "space": Holder(SpaceData()),
        "local": LocalHolder(
            markets=MarketsClient(cfg.location.latitude, cfg.location.longitude,
                                  cfg.local.radius_km),
            events=EventsClient(cfg.location.latitude, cfg.location.longitude,
                                cfg.local.radius_km),
        ),
    }
    weather_client = WeatherClient(cfg.location.latitude, cfg.location.longitude,
                                   units=cfg.weather.units)
    director = _build_director(cfg, renderer, store, holders, health)

    if args.once:
        for i, train in enumerate(cfg.trains):
            try:
                store.set(i, client.get_next_arrivals(train, count=2))
            except Exception as exc:
                print(f"[poll] {train.line}: {exc}")
        if alerts_client:
            try:
                line_alerts = alerts_client.alerts_for_trains(cfg.trains)
                store.set_line_alerts(line_alerts)
                store.set_alerts([a.tag if a else None for a in line_alerts])
            except Exception as exc:
                print(f"[alerts] {exc}")
        display.render(director.render(now_eastern(), 0))
        display.close()
        return 0

    stop_event = threading.Event()
    threading.Thread(target=_poller, daemon=True,
                     args=(stop_event, store, client, cfg.trains,
                           cfg.mta.poll_seconds, health)).start()
    if alerts_client:
        threading.Thread(target=_alerts_poller, daemon=True,
                         args=(stop_event, store, alerts_client, cfg.trains,
                               cfg.alerts.poll_seconds, health)).start()
    if cfg.weather.enabled:
        threading.Thread(target=_weather_poller, daemon=True,
                         args=(stop_event, holders["weather"], weather_client,
                               cfg.weather.poll_seconds, health)).start()
    if cfg.sky.enabled:
        threading.Thread(target=_sky_poller, daemon=True,
                         args=(stop_event, holders["sky"],
                               SkyClient(cfg.location.latitude, cfg.location.longitude))).start()
    if cfg.space.enabled:
        threading.Thread(target=_space_poller, daemon=True,
                         args=(stop_event, holders["space"], SpaceClient())).start()
    if cfg.local.enabled:
        threading.Thread(target=_local_poller, daemon=True,
                         args=(stop_event, holders["local"])).start()

    frame_dt = 1.0 / max(1, args.fps)
    start = time.monotonic()
    try:
        while True:
            tick_ms = int((time.monotonic() - start) * 1000)
            display.render(director.render(now_eastern(), tick_ms))
            time.sleep(frame_dt)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        display.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
