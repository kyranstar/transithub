from datetime import datetime, timedelta

from transithub.config import Config, MatrixConfig, DisplayConfig
from transithub.models import Arrival, TrackedTrain
from transithub.display.sign import (
    format_time, build_schedule, pick_page, Panel, SignRenderer,
)
from transithub.display.bullets import line_color
from transithub.mta.alerts import LineAlert

NOW = datetime(2026, 5, 23, 12, 0, 0)


def _arr(mins, dest="8 Av", line="L"):
    return Arrival(line, dest, NOW + timedelta(minutes=mins))


def _arr_s(seconds, dest="8 Av", line="L"):
    return Arrival(line, dest, NOW + timedelta(seconds=seconds))


def test_format_time_minutes():
    assert format_time(_arr(2), NOW, 20) == ("2m", False)
    assert format_time(_arr(12), NOW, 20) == ("12m", False)


def test_format_time_never_zero_minutes():
    # 20s..119s all read "1m" (never "0m")
    assert format_time(_arr_s(25), NOW, 20) == ("1m", False)
    assert format_time(_arr_s(90), NOW, 20) == ("1m", False)
    assert format_time(_arr_s(119), NOW, 20) == ("1m", False)
    assert format_time(_arr_s(120), NOW, 20) == ("2m", False)


def test_format_time_now_only_under_threshold():
    assert format_time(_arr_s(15), NOW, 20) == ("Now", True)
    assert format_time(_arr_s(25), NOW, 20)[0] == "1m"   # not "Now" yet


def test_build_schedule_weights_airtime():
    # one screen per stop; weight scales its airtime. L 18s, M 6s -> 75% / 25%
    L = Panel(rows=["L1", "L2"], weight=3)
    M = Panel(rows=["M1"], weight=1)
    sched = build_schedule([L, M], page_seconds=6)
    assert [rows for rows, _ in sched] == [["L1", "L2"], ["M1"]]
    assert [dur for _, dur in sched] == [18.0, 6.0]


def test_pick_page_follows_weighted_timeline():
    sched = [(["L1", "L2"], 18.0), (["M1"], 6.0)]
    assert pick_page(sched, 0) == ["L1", "L2"]
    assert pick_page(sched, 17_000) == ["L1", "L2"]
    assert pick_page(sched, 19_000) == ["M1"]
    assert pick_page(sched, 25_000) == ["L1", "L2"]   # wraps at 24s


def _renderer():
    cfg = Config(matrix=MatrixConfig(rows=32, cols=64),
                 display=DisplayConfig(arriving_threshold_seconds=30, page_seconds=6))
    return SignRenderer(cfg)


def test_render_returns_correct_size():
    r = _renderer()
    img = r.render([[_arr(2)], [_arr(8, "Manh", "M")]], tick_ms=0, now=NOW)
    assert img.size == (64, 32) and img.mode == "RGB"


def test_arriving_flashes_only_the_now_text():
    r = _renderer()
    a = [[Arrival("L", "8 Av", NOW + timedelta(seconds=10))]]   # arriving
    on = r.render(a, tick_ms=0, now=NOW)      # blink on
    off = r.render(a, tick_ms=300, now=NOW)   # blink off (~half a 2Hz cycle later)
    assert on.tobytes() != off.tobytes()      # the "Now" flashes
    # the row is not blanked: the L bullet stays lit on the off beat
    assert line_color("L") in {c for _, c in off.getcolors(maxcolors=100000)}


def test_no_arrivals_shows_placeholder_without_crashing():
    r = _renderer()
    img = r.render([[]], tick_ms=0, now=NOW)
    assert img.size == (64, 32)


def test_suspended_line_gets_half_weight():
    cfg = Config(matrix=MatrixConfig(rows=32, cols=64), display=DisplayConfig(),
                 trains=[TrackedTrain("L", "L16", "N", weight=2),
                         TrackedTrain("M", "M09", "N", weight=2)])
    r = SignRenderer(cfg)
    panels = r._build_panels([[_arr(2)], [_arr(5, line="M")]],
                             alerts=[None, LineAlert("M", "SUSP", "")], now=NOW)
    assert panels[0].weight == 2.0          # L running -> full weight
    assert panels[1].weight == 1.0          # M suspended -> halved


def test_no_service_row_keeps_configured_line_bullet():
    cfg = Config(matrix=MatrixConfig(rows=32, cols=64),
                 display=DisplayConfig(),
                 trains=[TrackedTrain(line="M", stop_id="M08", direction="N")])
    img = SignRenderer(cfg).render([[]], tick_ms=0, now=NOW)
    colors = {color for _, color in img.getcolors(maxcolors=100000)}
    assert (0xFF, 0x63, 0x19) in colors  # M (orange) bullet still drawn


_ALERT_RED = (240, 60, 40)
_AMBER = (255, 170, 40)


def _colors(img):
    return {color for _, color in img.getcolors(maxcolors=100000)}


def test_disrupted_row_shows_countdown_and_red_message():
    r = _renderer()
    img = r.render([[_arr(2)]], tick_ms=0, now=NOW,
                   alerts=[LineAlert("L", "DLY", "SIGNAL PROBLEM")])
    cols = _colors(img)
    assert _AMBER in cols          # countdown stays anchored on the right
    assert _ALERT_RED in cols      # the red disruption message shares the row


def test_no_alert_means_no_red():
    r = _renderer()
    img = r.render([[_arr(2)]], tick_ms=0, now=NOW)  # no alerts arg
    assert _ALERT_RED not in _colors(img)


def test_delay_message_includes_the_reason():
    r = _renderer()
    # The reason is part of the message: "DLY SIGNAL PROBLEM" differs from "DLY".
    with_reason = r.render([[_arr(2)]], tick_ms=0, now=NOW,
                           alerts=[LineAlert("L", "DLY", "SIGNAL PROBLEM")])
    no_reason = r.render([[_arr(2)]], tick_ms=0, now=NOW, alerts=[LineAlert("L", "DLY", "")])
    assert with_reason.tobytes() != no_reason.tobytes()


def test_suspended_row_shows_red_message():
    cfg = Config(matrix=MatrixConfig(rows=32, cols=64), display=DisplayConfig(),
                 trains=[TrackedTrain(line="L", stop_id="L16", direction="N")])
    img = SignRenderer(cfg).render([[]], tick_ms=0, now=NOW, alerts=[LineAlert("L", "SUSP", "")])
    assert _ALERT_RED in _colors(img)   # the SUSP message shows even with no arrivals


def test_suspended_reason_extends_the_message():
    cfg = Config(matrix=MatrixConfig(rows=32, cols=64), display=DisplayConfig(),
                 trains=[TrackedTrain(line="L", stop_id="L16", direction="N")])
    with_reason = SignRenderer(cfg).render([[]], tick_ms=0, now=NOW,
                                           alerts=[LineAlert("L", "SUSP", "SICK PASSENGER")])
    plain = SignRenderer(cfg).render([[]], tick_ms=0, now=NOW,
                                     alerts=[LineAlert("L", "SUSP", "")])
    assert with_reason.tobytes() != plain.tobytes()    # "SUSP SICK PASSENGER" vs "SUSP"
