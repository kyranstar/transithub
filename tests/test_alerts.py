from transithub.models import TrackedTrain
from transithub.mta.alerts import AlertsClient

NOW = 1_700_000_000  # fixed epoch for active_period windows

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
