import json
from pathlib import Path

from transithub.models import TrackedTrain
from transithub.mta.alerts import AlertsClient, LineAlert, parse_reason

NOW = 1_700_000_000  # fixed epoch for active_period windows

_FIXTURE = Path(__file__).parent / "fixtures" / "alerts_sample.json"


def _fixture_client():
    data = json.loads(_FIXTURE.read_text())
    return AlertsClient(fetcher=lambda: data)

# Real stops (from the vendored Stations.csv):
L_N = TrackedTrain("L", "L16", "N")  # DeKalb Av, toward Manhattan
L_S = TrackedTrain("L", "L16", "S")  # toward Canarsie - Rockaway Parkway
M_N = TrackedTrain("M", "M08", "N")  # Myrtle-Wyckoff, toward Manhattan


def _alert(routes, alert_type, header="", start=NOW - 100, end=NOW + 100):
    return {"alert": {
        "informed_entity": [{"route_id": r} for r in routes],
        "active_period": [{"start": start, "end": end}],
        "header_text": {"translation": [{"language": "en", "text": header}]},
        "transit_realtime.mercury_alert": {"alert_type": alert_type},
    }}


def _client(entities):
    return AlertsClient(fetcher=lambda: {"entity": entities})


def test_maps_disruption_types():
    c = _client([_alert(["L"], "Delays", "L trains are delayed")])
    assert c.tags_for_trains([L_N], now=NOW) == ["DLY"]


def test_ignores_non_disruption_types():
    c = _client([_alert(["L"], "Planned - Reroute", "weekend work")])
    assert c.tags_for_trains([L_N], now=NOW) == [None]


def test_ignores_inactive_periods():
    c = _client([_alert(["L"], "Delays", "delayed", start=NOW + 1000, end=NOW + 2000)])
    assert c.tags_for_trains([L_N], now=NOW) == [None]


def test_most_severe_tag_wins():
    c = _client([_alert(["L"], "Delays", "L delayed"),
                 _alert(["L"], "Reduced Service", "reduced"),
                 _alert(["L"], "Planned - Suspended", "suspended")])
    assert c.tags_for_trains([L_N], now=NOW) == ["SUSP"]


def test_direction_filter_suppresses_opposite():
    # "Canarsie-bound" = southbound; suppress for the northbound (Manhattan) stop
    c = _client([_alert(["L"], "Delays",
                        "Canarsie-bound [L] trains are running with delays")])
    assert c.tags_for_trains([L_N], now=NOW) == [None]
    assert c.tags_for_trains([L_S], now=NOW) == ["DLY"]


def test_direction_filter_keeps_matching_direction():
    c = _client([_alert(["L"], "Delays", "Manhattan-bound [L] trains are delayed")])
    assert c.tags_for_trains([L_N], now=NOW) == ["DLY"]
    assert c.tags_for_trains([L_S], now=NOW) == [None]


def test_no_direction_in_text_is_line_wide():
    c = _client([_alert(["M"], "Planned - Suspended",
                        "[M] is suspended - take the [J] and free shuttle buses")])
    assert c.tags_for_trains([M_N], now=NOW) == ["SUSP"]


def test_untracked_line_gets_none():
    c = _client([_alert(["A"], "Delays", "A delayed")])
    assert c.tags_for_trains([L_N], now=NOW) == [None]


def test_result_aligns_with_trains():
    c = _client([_alert(["L"], "Delays", "Canarsie-bound [L] delays"),
                 _alert(["M"], "Planned - Suspended", "[M] suspended")])
    assert c.tags_for_trains([L_N, M_N], now=NOW) == [None, "SUSP"]


# -- reason parsing --------------------------------------------------------

def test_parse_reason_from_header_phrases():
    assert parse_reason("trains delayed due to an NYPD investigation") == "POLICE"
    assert parse_reason("while we address a mechanical problem") == "MECHANICAL PROBLEM"
    assert parse_reason("because of a sick passenger at Bedford Av") == "SICK PASSENGER"
    assert parse_reason("delayed due to an FDNY investigation") == "FDNY"
    assert parse_reason("we are addressing signal problems") == "SIGNAL PROBLEM"


def test_parse_reason_from_whats_happening_block():
    # The description format used by maintenance alerts.
    assert parse_reason("Transfer here.\nWhat's happening?\nSignal maintenance") == "SIGNAL WORK"
    assert parse_reason("Note: ...\n\nWhat's happening?\nTrack maintenance") == "TRACK WORK"
    assert parse_reason("What's happening?\nWe're replacing tracks") == "TRACK WORK"


def test_parse_reason_unknown_and_empty_are_blank():
    assert parse_reason("We're making station improvements") == ""
    assert parse_reason("runs every 8 minutes") == ""
    assert parse_reason("") == ""
    assert parse_reason(None) == ""  # defensive


def test_parse_reason_specific_wins_over_generic():
    # "signal problem" and "signal maintenance" both map to SIGNALS; ensure the
    # ordering never accidentally returns a less-specific label first.
    assert parse_reason("a signal problem near the station") == "SIGNAL PROBLEM"


# -- alerts_for_trains (rich, from the captured fixture) -------------------

def test_alerts_for_trains_carries_tag_and_reason():
    c = _fixture_client()
    # M08 is the M at Myrtle-Wyckoff; the fixture M Delays alert cites signal problems.
    [a] = c.alerts_for_trains([M_N], now=NOW)
    assert isinstance(a, LineAlert)
    assert a.line == "M" and a.tag == "DLY" and a.reason == "SIGNAL PROBLEM"


def test_alerts_for_trains_reads_description_reason():
    # The fixture's [6] Reduced Service has its reason only in the description.
    c = _fixture_client()
    six = TrackedTrain("6", "601", "N")  # Pelham Bay Park, a real 6 stop
    [a] = c.alerts_for_trains([six], now=NOW)
    assert a is not None and a.tag == "RDCD" and a.reason == "TRACK WORK"


def test_alerts_for_trains_unknown_reason_is_blank():
    # [1] Reduced Service in the fixture is "station improvements" -> no mapped reason.
    c = _fixture_client()
    one = TrackedTrain("1", "104", "N")  # 231 St, a real 1 stop
    [a] = c.alerts_for_trains([one], now=NOW)
    assert a is not None and a.tag == "RDCD" and a.reason == ""


def test_alerts_for_trains_direction_aware_from_fixture():
    # The fixture has two [L] delays in opposite directions:
    #   * Southbound (Canarsie) -> sick passenger
    #   * Manhattan-bound (Northbound) -> FDNY
    # Each tracked direction must see only its own.
    c = _fixture_client()
    [north] = c.alerts_for_trains([L_N], now=NOW)
    assert north is not None and north.tag == "DLY" and north.reason == "FDNY"
    [south] = c.alerts_for_trains([L_S], now=NOW)
    assert south is not None and south.tag == "DLY" and south.reason == "SICK PASSENGER"


def test_alerts_for_trains_none_for_untracked_in_fixture():
    c = _fixture_client()
    q = TrackedTrain("Q", "Q05", "N")  # a Q stop, not disrupted in the fixture
    assert c.alerts_for_trains([q], now=NOW) == [None]


def test_tags_for_trains_matches_alerts_for_trains_from_fixture():
    # The string-tag view must stay consistent with the rich view.
    c = _fixture_client()
    trains = [L_N, L_S, M_N]
    rich = c.alerts_for_trains(trains, now=NOW)
    tags = c.tags_for_trains(trains, now=NOW)
    assert tags == [a.tag if a else None for a in rich]
