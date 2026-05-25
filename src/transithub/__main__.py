import argparse
import sys
import threading
import time

from .clock import now as now_eastern
from .config import load_config
from .health import HealthMonitor
from .mta.alerts import AlertsClient
from .mta.feed import FeedClient, feed_dependency_available
from .profile import day_profile
from .store import ArrivalStore, WeatherHolder
from .weather.client import WeatherClient
from .display.sign import SignRenderer
from .display.simulator import SimulatorDisplay
from .display.director import Context, Director, Slot
from .display.dimmer import Dimmer
from .display.sources import HealthSource, SunEventSource, WeatherRundownSource
from .display.scenes.trains import TrainScene
from .display.scenes.weather import WeatherScene
from .display.scenes.sun_event import SunEventScene


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
            store.set_alerts(client.tags_for_trains(trains))
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


def _make_display(cfg, args):
    if args.simulate:
        return SimulatorDisplay(args.simulate_out, scale=args.scale)
    try:
        from .display.matrix import RGBMatrixDisplay
        return RGBMatrixDisplay(cfg.matrix)
    except Exception as exc:
        print(f"[display] matrix unavailable ({exc}); using simulator")
        return SimulatorDisplay(args.simulate_out, scale=args.scale)


def _build_director(cfg, renderer, store, weather_holder, health):
    """Assemble the Director: the train sign as the default, plus weather/sun/health
    sources. Feature sources (sky, space, neighborhood) register here too."""
    train_scene = TrainScene(renderer, store)

    def make_weather(w, now):
        return WeatherScene(w, now, rundown_seconds=cfg.weather.rundown_seconds,
                            cols=cfg.matrix.cols, rows=cfg.matrix.rows,
                            trash_days=cfg.trash.days)

    def make_sun(kind, t):
        return SunEventScene(kind, t, cfg.matrix.cols, cfg.matrix.rows)

    slots = [
        Slot(HealthSource(cfg.matrix.cols, cfg.matrix.rows), priority=100,
             cooldown_ms=120_000, takeover=True, interjection=False),
    ]
    if cfg.notifications.sunrise or cfg.notifications.sunset:
        slots.append(Slot(
            SunEventSource(make_sun, cfg.notifications.sunrise, cfg.notifications.sunset),
            priority=60, interjection=False))
    if cfg.weather.enabled:
        slots.append(Slot(
            WeatherRundownSource(make_weather), priority=50,
            cooldown_ms=cfg.weather.rundown_every_minutes * 60_000,
            first_after_ms=30_000))

    def context_builder(now, mono_ms):
        w = weather_holder.get()
        return Context(now=now, mono_ms=mono_ms, profile=day_profile(now, w),
                       weather=w, health=tuple(health.warnings()))

    return Director(train_scene, slots, context_builder=context_builder, dimmer=Dimmer())


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
    weather_holder = WeatherHolder()
    weather_client = WeatherClient(cfg.location.latitude, cfg.location.longitude,
                                   units=cfg.weather.units)
    health = HealthMonitor()
    director = _build_director(cfg, renderer, store, weather_holder, health)

    if args.once:
        for i, train in enumerate(cfg.trains):
            try:
                store.set(i, client.get_next_arrivals(train, count=2))
            except Exception as exc:
                print(f"[poll] {train.line}: {exc}")
        if alerts_client:
            try:
                store.set_alerts(alerts_client.tags_for_trains(cfg.trains))
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
                         args=(stop_event, weather_holder, weather_client,
                               cfg.weather.poll_seconds, health)).start()

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
