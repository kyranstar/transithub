"""Free, outdoor, general-audience happenings near home today or tomorrow.

Source: the "NYC Parks Events Listing" family on ``data.cityofnewyork.us``
(Socrata), three parallel tables joined by ``event_id``:

- Event Listing   ``fudw-fgrp`` — title, date, start/end time, ``cost_free``.
- Event Locations ``cpcm-i88g`` — lat/long, venue name (for distance + a place label).
- Event Categories``xtsw-fqvh`` — category tags (for outdoor / audience checks).

We fetch all three, join in Python, and keep events that are free, near home,
today or tomorrow, plausibly outdoors, and not children-only. Filtering is
conservative: anything we can't place or time is dropped."""
from __future__ import annotations

import json
import math
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Optional

from ..clock import now as now_eastern

DOMAIN = "https://data.cityofnewyork.us/resource"
LISTING = "fudw-fgrp"
LOCATIONS = "cpcm-i88g"
CATEGORIES = "xtsw-fqvh"

MAX_EVENTS = 6        # keep the rotation small and curated

# Explicit grown-up audience tags. Only these override a "Best for Kids" flag —
# topic tags like "Film" or "Concerts" don't, since a children's movie is still
# tagged "Film". This keeps the kids-only filter from leaking family programming.
_ADULT_AUDIENCE_CATS = {
    "city parks foundation adults", "adults", "seniors", "teens", "young adults",
}
# Tags that mark children-focused programming.
_KIDS_CATS = {
    "best for kids", "cityparks kids arts", "cityparks puppetmobile",
    "kids", "tots",
}
# Location-name keywords that signal an indoor venue (drop these).
_INDOOR_WORDS = re.compile(
    r"\b(recreation center|rec center|nature center|visitor center|"
    r"library|museum|theater|theatre|gallery|play center|"
    r"indoor|gym|building|hall|house)\b", re.I)
# Category tags that signal an indoor venue.
_INDOOR_CATS = {"historic house trust sites"}


@dataclass(frozen=True)
class Event:
    """One qualifying happening, shaped for the screen.

    ``kind`` is a short headline derived from the categories ("PARK MOVIE",
    "CONCERT", "FESTIVAL", "PARK EVENT") that the scene shows as its type line;
    ``label`` keeps the specific title (used for de-dupe / cooldown keys)."""
    label: str         # specific event title, upper-cased
    kind: str          # short type headline that fits the panel
    when_label: str    # e.g. "8 PM", "NOON"
    venue: str         # short place name, upper-cased
    dist_km: float
    start: datetime    # full start datetime (for sorting / cooldown)


def _default_fetch(url: str) -> list:
    req = urllib.request.Request(url, headers={"User-Agent": "transithub"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p = math.pi / 180
    a = (0.5 - math.cos((lat2 - lat1) * p) / 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2)
    return 2 * 6371 * math.asin(math.sqrt(a))


def when_label(start_time: str) -> Optional[str]:
    """A compact clock label from a ``HH:MM`` string: "8 PM", "8:30 PM", "NOON".

    Returns None when the time can't be parsed."""
    m = re.match(r"\s*(\d{1,2}):(\d{2})", start_time or "")
    if not m:
        return None
    h, mn = int(m.group(1)), int(m.group(2))
    if not (0 <= h <= 23 and 0 <= mn <= 59):
        return None
    if h == 12 and mn == 0:
        return "NOON"
    ampm = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12} {ampm}" if mn == 0 else f"{h12}:{mn:02d} {ampm}"


def is_kids_only(categories: set) -> bool:
    """True when the event is children-focused with no grown-up audience tag.

    "Best for Kids" (and the kids program series) mark child audiences; only an
    explicit adult/teen/senior tag rescues such an event as general-audience."""
    low = {c.strip().lower() for c in categories}
    if low & _ADULT_AUDIENCE_CATS:
        return False
    return bool(low & _KIDS_CATS)


def is_outdoor(categories: set, venue: str) -> bool:
    """Best-effort outdoor check from category tags and the venue name.

    Drops events tagged as an indoor venue type or held somewhere whose name
    reads indoor (rec/nature/visitor center, library, museum, house, …). NYC
    Parks events are otherwise outdoors by default."""
    low = {c.strip().lower() for c in categories}
    if low & _INDOOR_CATS:
        return False
    if venue and _INDOOR_WORDS.search(venue):
        return False
    return True


# Compact venue labels for the panel: drop the bit after ":"/"(", abbreviate
# "Square" -> "SQ", and strip generic suffixes so the distinctive name shows.
_VENUE_TRIM = re.compile(r"\s*[:(].*$")          # drop "Park: Bandshell" / "(...)"
_VENUE_DROP = re.compile(
    r"\b(park|playground|ballfields?|greenmarket|field|garden|center|plaza)\b", re.I)
_SQUARE = re.compile(r"\bsquare\b", re.I)
_PLACE_MAX_PX = 62               # must fit the 64px panel with a 1px margin


def short_place(name: str) -> str:
    """A panel-ready place label: ``"Tompkins Square Park"`` -> ``"TOMPKINS SQ"``.

    Drops trailing qualifiers (``Park``, ``Playground``, …), abbreviates
    ``Square`` to ``SQ``, and — if still too wide — keeps the single most
    distinctive (last) word so something legible always fits."""
    from ..display import scenery as S          # local import: keep this module UI-free at top level
    base = _VENUE_TRIM.sub("", name or "").strip()
    base = _SQUARE.sub("SQ", base)
    base = _VENUE_DROP.sub("", base)
    base = re.sub(r"\s+", " ", base).strip(" -,").upper() or (name or "").upper()
    if S.text_width(base) <= _PLACE_MAX_PX:
        return base
    words = base.split()
    return words[-1] if words else base          # the namesake word ("HERNANDEZ")


def _venue_label(name: str) -> str:
    return short_place(name)


def _title_label(title: str) -> str:
    # Keep the part after a "series:" prefix so the specific name shows.
    base = title.split(":", 1)[-1].strip() if ":" in title else title.strip()
    return base.upper()


# Category -> short type headline (checked in order; first hit wins). Each fits
# the 64px panel at scale 1, so the scene's type line never clips.
_KIND_BY_CAT = [
    ({"film", "free summer movies"}, "PARK MOVIE"),
    ({"concerts", "free summer concerts"}, "CONCERT"),
    ({"free summer theater", "theater"}, "THEATER"),
    ({"festivals", "fall festivals"}, "FESTIVAL"),
    ({"dance"}, "DANCE"),
    ({"fitness"}, "FITNESS"),
    ({"birding"}, "BIRDING"),
    ({"nature", "hiking"}, "NATURE"),
    ({"art", "arts & crafts"}, "ART"),
    ({"fireworks"}, "FIREWORKS"),
    ({"food"}, "FOOD"),
    ({"astronomy"}, "STARGAZING"),
]


def kind_label(categories: set, title: str = "") -> str:
    """A short type headline from the categories (e.g. "PARK MOVIE", "CONCERT").

    Falls back to a couple of title keywords, then a generic "PARK EVENT"."""
    low = {c.strip().lower() for c in categories}
    for cats, label in _KIND_BY_CAT:
        if low & cats:
            return label
    t = title.lower()
    if "movie" in t or "film" in t:
        return "PARK MOVIE"
    if "concert" in t:
        return "CONCERT"
    if "festival" in t:
        return "FESTIVAL"
    return "PARK EVENT"


class EventsClient:
    """Free, outdoor, general-audience events near home for today/tomorrow."""
    name = "events"

    def __init__(self, latitude: float, longitude: float, radius_km: float = 4.0,
                 fetcher: Callable[[str], list] = _default_fetch,
                 now: Callable[[], datetime] = now_eastern):
        self.lat = latitude
        self.lon = longitude
        self.radius_km = radius_km
        self._fetch = fetcher
        self._now = now

    def _url(self, resource: str, **params) -> str:
        q = urllib.parse.urlencode({"$limit": 5000, **params})
        return f"{DOMAIN}/{resource}.json?{q}"

    def _listing_url(self, today: date, day_after: date) -> str:
        # Push the today/tomorrow window + free filter to the server so the
        # response is small and current — the listing table is large.
        where = (f"date >= '{today.isoformat()}T00:00:00' "
                 f"AND date < '{day_after.isoformat()}T00:00:00' "
                 f"AND cost_free = '1'")
        return self._url(LISTING, **{"$where": where, "$order": "date"})

    def _by_id(self, resource: str, event_ids) -> List[dict]:
        url = self._url(resource)
        if event_ids:        # scope the join tables to just the events we kept
            ids = ",".join(f"'{e}'" for e in sorted(event_ids))
            url = self._url(resource, **{"$where": f"event_id in ({ids})"})
        try:
            rows = self._fetch(url)
        except Exception:
            return []
        return rows if isinstance(rows, list) else []

    def upcoming(self) -> List[Event]:
        now = self._now()
        today = now.date()
        tomorrow = today + timedelta(days=1)
        day_after = today + timedelta(days=2)
        try:
            listing = self._fetch(self._listing_url(today, day_after))
        except Exception:
            return []
        if not isinstance(listing, list) or not listing:
            return []

        # Only join locations/categories for the events the listing returned.
        ids = {str(r.get("event_id")) for r in listing if r.get("event_id") is not None}
        locs: Dict[str, dict] = {}
        for r in self._by_id(LOCATIONS, ids):
            eid = r.get("event_id")
            if eid is not None and str(eid) not in locs:   # first location per event
                locs[str(eid)] = r
        cats: Dict[str, set] = {}
        for r in self._by_id(CATEGORIES, ids):
            eid, name = r.get("event_id"), r.get("name")
            if eid is not None and name:
                cats.setdefault(str(eid), set()).add(name)

        found: List[Event] = []
        for row in listing:
            try:
                if str(row.get("cost_free")) != "1":          # free only
                    continue
                eid = str(row.get("event_id"))
                date_s = row.get("date") or ""
                day = datetime.fromisoformat(date_s.replace("Z", "")).date()
                if day not in (today, tomorrow):              # today or tomorrow
                    continue
                when = when_label(row.get("start_time") or "")
                if when is None:
                    continue
                loc = locs.get(eid)
                if not loc:                                   # need coords to place it
                    continue
                lat, lon = float(loc["lat"]), float(loc["long"])
                dist = _haversine_km(self.lat, self.lon, lat, lon)
                if dist > self.radius_km:                     # near home only
                    continue
                tags = cats.get(eid, set())
                venue = loc.get("name") or ""
                if not is_outdoor(tags, venue):               # outdoors only
                    continue
                if is_kids_only(tags):                        # not children-only
                    continue
                hh, mm = (row.get("start_time") or "0:0").split(":")[:2]
                start = datetime(day.year, day.month, day.day, int(hh), int(mm))
            except (KeyError, TypeError, ValueError):
                continue
            title = str(row.get("title") or "")
            found.append(Event(
                label=_title_label(title),
                kind=kind_label(tags, title),
                when_label=when,
                venue=_venue_label(venue),
                dist_km=round(dist, 2),
                start=start,
            ))

        found.sort(key=lambda e: e.start)
        # De-dupe identical label+venue+start (the feed can repeat rows).
        seen = set()
        unique: List[Event] = []
        for e in found:
            key = (e.label, e.venue, e.start)
            if key not in seen:
                seen.add(key)
                unique.append(e)
        return unique[:MAX_EVENTS]
