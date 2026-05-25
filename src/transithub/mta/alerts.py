from __future__ import annotations

import json
import re
import time
import urllib.request
from dataclasses import dataclass
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

# Reason parsing -----------------------------------------------------------
#
# The disruption reason lives in prose, in one of two places:
#   * the header ("...due to an NYPD investigation...", "...address a mechanical
#     problem..."), or
#   * a "What's happening?\n<reason>" line in the description (planned/maintenance
#     alerts), e.g. "Signal maintenance", "Track maintenance", "We're replacing tracks".
#
# We map that text to a SHORT, glanceable, factual phrase via an ordered keyword
# list. The order matters: more specific phrases come first so e.g. "signal
# problem" wins over a bare "signal". Anything unrecognized yields "" (blank) —
# we never guess, and never editorialize.
_WHATS_HAPPENING_RE = re.compile(r"what'?s happening\?\s*\n+\s*(.+)", re.IGNORECASE)

# (keyword, label). First keyword found in the text wins, so more specific phrases
# come first. Labels are plain, readable words a rider understands at a glance — no
# cryptic truncations; the sign marquees the longer ones.
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
    ("mechanical", "MECHANICAL PROBLEM"),
    ("disabled train", "STALLED TRAIN"),
    ("track maintenance", "TRACK WORK"),
    ("replacing track", "TRACK WORK"),
    ("track work", "TRACK WORK"),
    ("track condition", "TRACK CONDITION"),
    ("rubbish", "DEBRIS ON TRACK"),
    ("debris", "DEBRIS ON TRACK"),
    ("litter", "DEBRIS ON TRACK"),
    ("power", "POWER PROBLEM"),
    ("snow", "SNOW"),
    ("ice", "ICE"),
    ("weather", "WEATHER"),
    ("flooding", "FLOODING"),
    ("water condition", "FLOODING"),
]


def _routes(alert: dict) -> set:
    return {ie["route_id"] for ie in alert.get("informed_entity", []) if "route_id" in ie}


def _alert_type(alert: dict) -> Optional[str]:
    return alert.get(_MERCURY_KEY, {}).get("alert_type")


def _translation(field, language="en") -> str:
    translations = (field or {}).get("translation") or [{}]
    for t in translations:
        if t.get("language", "en").startswith(language):
            return t.get("text", "")
    return translations[0].get("text", "")


def _header_text(alert: dict) -> str:
    return _translation(alert.get("header_text"))


def _description_text(alert: dict) -> str:
    return _translation(alert.get("description_text"))


def parse_reason(text: str) -> str:
    """A short, glanceable reason phrase from alert prose, or "" if not recognized.

    Reads both the header and the "What's happening?" description line; matching is
    a curated keyword map (see `_REASON_KEYWORDS`). Defensive: any falsy/garbled
    input simply yields "".
    """
    if not text:
        return ""
    low = text.lower()
    # Prefer the explicit "What's happening?" answer when present — it's the
    # cleanest statement of the cause — then fall back to the whole text.
    m = _WHATS_HAPPENING_RE.search(text)
    haystacks = ([m.group(1).lower()] if m else []) + [low]
    for hay in haystacks:
        for keyword, label in _REASON_KEYWORDS:
            if keyword in hay:
                return label
    return ""


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
        if not isinstance(p, dict):
            continue
        try:
            start = int(p.get("start") or 0)
            end = p.get("end")
            end = int(end) if end is not None else None
        except (TypeError, ValueError):
            continue            # a malformed period just doesn't count as active
        if start <= now and (end is None or now <= end):
            return True
    return False


def _default_fetch() -> dict:
    req = urllib.request.Request(ALERTS_URL, headers={"User-Agent": "transithub"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


@dataclass(frozen=True)
class LineAlert:
    """One disruption affecting a tracked stop.

    `tag` is the glanceable badge (DLY/RDCD/SUSP); `reason` is a short cause phrase
    (e.g. "SIGNALS", "SICK PASS") or "" when the cause isn't recognized.
    """
    line: str
    tag: str
    reason: str = ""


class AlertsClient:
    """Maps the MTA subway alerts feed to a short disruption tag per line."""

    def __init__(self, fetcher: Callable[[], dict] = _default_fetch):
        self._fetch = fetcher

    def alerts_for_trains(
        self, trains: Sequence[TrackedTrain], now: Optional[int] = None
    ) -> List[Optional[LineAlert]]:
        """One `LineAlert` (or None) per tracked stop, direction-aware.

        Returns a list aligned with `trains`. The most severe applicable alert wins,
        and its parsed reason rides along.
        """
        now = int(time.time()) if now is None else now
        data = self._fetch()

        # Collect active disruption alerts per line as (tag, header, reason).
        by_line: dict = {}
        for entity in data.get("entity", []):
            try:
                alert = entity.get("alert")
                if not alert:
                    continue
                tag = _TAG_BY_TYPE.get(_alert_type(alert))
                if tag is None or not _is_active(alert, now):
                    continue
                header = _header_text(alert)
                reason = parse_reason(header) or parse_reason(_description_text(alert))
                for route in _routes(alert):
                    by_line.setdefault(route, []).append((tag, header, reason))
            except Exception:
                continue   # one malformed alert never drops the rest of the feed

        result: List[Optional[LineAlert]] = []
        for train in trains:
            station = station_by_stop_id(train.stop_id)
            my_terms, opp_terms = (
                direction_terms(station, train.direction) if station else (set(), set())
            )
            best: Optional[LineAlert] = None
            for tag, header, reason in by_line.get(train.line, []):
                if station is not None and not _alert_applies(
                    header, train.direction, my_terms, opp_terms
                ):
                    continue
                if best is None or _SEVERITY[tag] > _SEVERITY[best.tag]:
                    best = LineAlert(line=train.line, tag=tag, reason=reason)
            result.append(best)
        return result

    def tags_for_trains(
        self, trains: Sequence[TrackedTrain], now: Optional[int] = None
    ) -> List[Optional[str]]:
        """One disruption tag (or None) per tracked stop, direction-aware.

        The string-tag view of `alerts_for_trains`, kept for sign.py and the poller.
        """
        return [a.tag if a else None for a in self.alerts_for_trains(trains, now)]
