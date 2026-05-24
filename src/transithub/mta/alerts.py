import json
import re
import time
import urllib.request
from typing import Callable, List, Optional, Sequence

from ..models import TrackedTrain
from .stations import direction_terms, label_terms, station_by_stop_id

ALERTS_URL = (
    "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/camsys%2Fsubway-alerts.json"
)

# MTA "mercury" alert_type -> short, glanceable tag. Only service disruptions are
# mapped; everything else (planned reroutes, stops skipped, station notices, ...) is
# intentionally ignored so the badge stays meaningful.
_TAG_BY_TYPE = {
    "Delays": "DLY",
    "Reduced Service": "RDCD",
    "Suspended": "SUSP",
    "No Scheduled Service": "SUSP",
    "Planned - Suspended": "SUSP",
    "Planned - Part Suspended": "SUSP",
}
# Higher number = more severe; wins when one line has several active alerts.
_SEVERITY = {"SUSP": 3, "RDCD": 2, "DLY": 1}

_MERCURY_KEY = "transit_realtime.mercury_alert"

# Captures the terminal/borough named before "-bound", e.g. "Canarsie-bound",
# "Jamaica Center-bound", "Manhattan-bound".
_BOUND_RE = re.compile(r"([0-9a-z][0-9a-z.&'/ ]*?)-bound", re.IGNORECASE)


def _routes(alert: dict) -> set:
    return {ie["route_id"] for ie in alert.get("informed_entity", []) if "route_id" in ie}


def _alert_type(alert: dict) -> Optional[str]:
    return alert.get(_MERCURY_KEY, {}).get("alert_type")


def _header_text(alert: dict) -> str:
    translations = (alert.get("header_text") or {}).get("translation") or [{}]
    for t in translations:
        if t.get("language", "en").startswith("en"):
            return t.get("text", "")
    return translations[0].get("text", "")


def _alert_applies(header: str, direction: str, my_terms, opp_terms) -> bool:
    """Best-effort: does a line-level alert apply to the tracked direction?

    The MTA only encodes direction in prose, so we read it from the text and
    suppress an alert only when it clearly names the opposite direction.
    """
    low = header.lower()
    nb, sb = "northbound" in low, "southbound" in low
    if nb != sb:  # exactly one mentioned
        return ("N" if nb else "S") == direction.upper()

    phrases = _BOUND_RE.findall(header)
    bound_terms = set()
    for phrase in phrases:
        bound_terms |= label_terms(phrase)
    if not bound_terms:
        return True  # no parseable direction -> treat as line-wide
    if (bound_terms & opp_terms) and not (bound_terms & my_terms):
        return False  # clearly the opposite direction
    return True


def _is_active(alert: dict, now: int) -> bool:
    periods = alert.get("active_period") or []
    if not periods:
        return True
    for p in periods:
        start = int(p.get("start") or 0)
        end = p.get("end")
        end = int(end) if end is not None else None
        if start <= now and (end is None or now <= end):
            return True
    return False


def _default_fetch() -> dict:
    req = urllib.request.Request(ALERTS_URL, headers={"User-Agent": "transithub"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


class AlertsClient:
    """Maps the MTA subway alerts feed to a short disruption tag per line."""

    def __init__(self, fetcher: Callable[[], dict] = _default_fetch):
        self._fetch = fetcher

    def tags_for_trains(
        self, trains: Sequence[TrackedTrain], now: Optional[int] = None
    ) -> List[Optional[str]]:
        """One disruption tag (or None) per tracked stop, direction-aware.

        Returns a list aligned with `trains`. The most severe applicable alert wins.
        """
        now = int(time.time()) if now is None else now
        data = self._fetch()

        # Collect active disruption alerts per line as (tag, header).
        by_line: dict = {}
        for entity in data.get("entity", []):
            alert = entity.get("alert")
            if not alert:
                continue
            tag = _TAG_BY_TYPE.get(_alert_type(alert))
            if tag is None or not _is_active(alert, now):
                continue
            header = _header_text(alert)
            for route in _routes(alert):
                by_line.setdefault(route, []).append((tag, header))

        result: List[Optional[str]] = []
        for train in trains:
            station = station_by_stop_id(train.stop_id)
            my_terms, opp_terms = (
                direction_terms(station, train.direction) if station else (set(), set())
            )
            best: Optional[str] = None
            for tag, header in by_line.get(train.line, []):
                if station is not None and not _alert_applies(
                    header, train.direction, my_terms, opp_terms
                ):
                    continue
                if best is None or _SEVERITY[tag] > _SEVERITY[best]:
                    best = tag
            result.append(best)
        return result
