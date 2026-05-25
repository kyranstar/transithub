import argparse
import sys
import threading
import time
from datetime import time as TimeOfDay

from .clock import now as now_eastern
from .config import load_config
from .health import HealthMonitor
from .local import parse_specs
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
from .display.scenes.local import MarketSource
from .display.scenes.sky import IssPassSource, MoonEventSource, PlaneOverheadSource
from .display.scenes.space import EarthFromSpaceSource, HumansInSpaceSource
from .display.scenes.trains import TrainScene
from .display.scenes.weather import WeatherScene
from .display.scenes.sun_event import SunEventScene

HUMANS_POLL_S = 30 * 60
EARTH_POLL_S = 3 * 60 * 60   # matches the Earth scene's ~3h cadence (each EPIC PNG is ~3 MB)
HUMANS_STALE_DAYS = 21       # hide the people-in-space count if unconfirmed this long


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
            store.set_line_alerts(client.alerts_for_trains(trains))
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


def _sky_poller(stop_event, holder, client, fetch_iss=True, fetch_plane=True):
    """Planes refresh fast (one is overhead for seconds); the ISS pass is good for
    minutes. Each feed is fetched only if its scene is enabled, and degrades to None
    on error — best-effort, never noisy."""
    iss = None
    last_iss = None
    while not stop_event.is_set():
        plane = None
        if fetch_plane:
            try:
                plane = client.plane_overhead()
            except Exception as exc:
                print(f"[sky] plane: {exc}")
        mono = time.monotonic()
        if fetch_iss and (last_iss is None or mono - last_iss >= SKY_POLL["iss"]):
            try:
                iss = client.iss_pass()
                last_iss = mono
            except Exception as exc:
                print(f"[sky] iss: {exc}")
        holder.set(SkyData(next_iss_pass=iss, plane_overhead=plane))
        stop_event.wait(SKY_POLL["plane"])


def _space_poller(stop_event, holder, client, fetch_humans=True, fetch_earth=True,
                  now_fn=now_eastern):
    """Humans-in-space + EPIC Earth, polled slowly (each only if enabled). The humans
    count holds across brief outages but is dropped once it hasn't been confirmed in
    HUMANS_STALE_DAYS, so a months-old number never lingers on screen."""
    humans = earth = None
    humans_at = None                      # wall-clock of the last good humans fetch
    last_h = last_e = None
    while not stop_event.is_set():
        mono = time.monotonic()
        if fetch_humans and (last_h is None or mono - last_h >= HUMANS_POLL_S):
            try:
                got = client.humans()
            except Exception as exc:
                print(f"[space] humans: {exc}")
                got = None
            last_h = mono
            if got is not None:
                humans, humans_at = got, now_fn()
        if humans is not None and humans_at is not None and \
                (now_fn() - humans_at).days >= HUMANS_STALE_DAYS:
            humans = None                 # unconfirmed too long -> stop showing it
        if fetch_earth and (last_e is None or mono - last_e >= EARTH_POLL_S):
            try:
                earth = client.earth()
                last_e = mono
            except Exception as exc:
                print(f"[space] earth: {exc}")
        holder.set(SpaceData(humans=humans, earth=earth))
        stop_event.wait(60)


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
    the background snapshots: weather, sky, space. See docs/scene-framework.md for
    the priority/cooldown rationale."""
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
        # ISS + planes may take over any time (cool day or night). The ISS cooldown
        # keeps one pass from replaying ~8x; the plane source already only fires for
        # low, audible traffic (see SkyClient), so a short cooldown lets it track what
        # you actually hear overhead without a 35,000-ft cruiser triggering it.
        if cfg.sky.iss:
            slots.append(Slot(IssPassSource(cols, rows), priority=90,
                              cooldown_ms=240_000, takeover=True, interjection=False))
        if cfg.sky.planes:
            slots.append(Slot(PlaneOverheadSource(cols, rows), priority=85,
                              cooldown_ms=60_000, takeover=True, interjection=False))
        if cfg.sky.moon:
            slots.append(Slot(MoonEventSource(cols, rows), priority=80,
                              cooldown_ms=12 * 3_600_000, takeover=False,
                              interjection=False, profiles=AFTER_DARK))
    # Disruptions are shown inline on the train sign (tag + reason), not as a
    # separate scene — so there's no alert slot here.
    if cfg.notifications.sunrise or cfg.notifications.sunset:
        slots.append(Slot(SunEventSource(make_sun, cfg.notifications.sunrise,
                                         cfg.notifications.sunset),
                          priority=60, interjection=False))
    if cfg.weather.enabled:
        slots.append(Slot(WeatherRundownSource(make_weather), priority=50,
                          cooldown_ms=cfg.weather.rundown_every_minutes * 60_000,
                          first_after_ms=30_000))
    market_specs = parse_specs(cfg.local.markets) if cfg.local.enabled else []
    if market_specs:
        slots.append(Slot(MarketSource(market_specs, cols, rows), priority=40,
                          cooldown_ms=120 * 60_000, first_after_ms=3 * 60_000,
                          profiles=DAY_EVENING))
    # The "weird facts" are a few-times-a-day daytime/evening thing — quiet overnight.
    if cfg.space.enabled:
        if cfg.space.humans:
            slots.append(Slot(HumansInSpaceSource(cols, rows), priority=30,
                              cooldown_ms=180 * 60_000, first_after_ms=4 * 60_000,
                              profiles=DAY_EVENING))
        if cfg.space.earth:
            slots.append(Slot(EarthFromSpaceSource(cols, rows), priority=30,
                              cooldown_ms=180 * 60_000, first_after_ms=6 * 60_000,
                              profiles=DAY_EVENING))

    def context_builder(now, mono_ms):
        w = weather_holder.get()
        return Context(now=now, mono_ms=mono_ms, profile=day_profile(now, w, bedtime),
                       weather=w, sky=holders["sky"].get(), space=holders["space"].get(),
                       health=tuple(health.warnings()))

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
                store.set_line_alerts(alerts_client.alerts_for_trains(cfg.trains))
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
    if cfg.sky.enabled and (cfg.sky.iss or cfg.sky.planes):   # the moon needs no poller
        sky_client = SkyClient(cfg.location.latitude, cfg.location.longitude,
                               radius_nm=cfg.sky.plane_radius_nm,
                               max_alt_ft=cfg.sky.plane_max_alt_ft)
        threading.Thread(target=_sky_poller, daemon=True,
                         args=(stop_event, holders["sky"], sky_client,
                               cfg.sky.iss, cfg.sky.planes)).start()
    if cfg.space.enabled and (cfg.space.humans or cfg.space.earth):
        threading.Thread(target=_space_poller, daemon=True,
                         args=(stop_event, holders["space"], SpaceClient(),
                               cfg.space.humans, cfg.space.earth)).start()

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
