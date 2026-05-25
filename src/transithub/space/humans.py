"""How many people are off the planet right now, and on which spacecraft.

The canonical source is Open Notify's ``astros.json``. As of this writing the
HTTPS endpoint refuses connections; the plain-HTTP one still answers, so we try
both. The feed is flaky and occasionally unreachable for long stretches, so the
client is built to fail gracefully: a fetch problem yields ``None`` and the scene
simply doesn't play. We never show a stale or guessed count dressed up as live.
"""
from __future__ import annotations

import json
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

# Try HTTPS first (preferred), then plain HTTP (currently the only one up).
ASTROS_URLS = (
    "https://api.open-notify.org/astros.json",
    "http://api.open-notify.org/astros.json",
)


@dataclass(frozen=True)
class HumansInSpace:
    """A snapshot of who's in orbit."""
    total: int
    by_craft: Dict[str, int] = field(default_factory=dict)

    @property
    def crafts(self) -> List[str]:
        """Craft names ordered by crew size (largest first), then alphabetically."""
        return [c for c, _ in sorted(self.by_craft.items(), key=lambda kv: (-kv[1], kv[0]))]


def _parse(payload: dict) -> Optional[HumansInSpace]:
    """Turn an astros.json body into a snapshot, or None if it isn't usable."""
    people = payload.get("people")
    if not isinstance(people, list) or not people:
        return None
    by_craft: Counter = Counter()
    for person in people:
        craft = (person.get("craft") or "").strip() if isinstance(person, dict) else ""
        if craft:
            by_craft[craft] += 1
    total = payload.get("number")
    if not isinstance(total, int) or total <= 0:
        total = sum(by_craft.values())
    if total <= 0:
        return None
    return HumansInSpace(total=total, by_craft=dict(by_craft))


def _default_fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "transithub"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


class HumansInSpaceClient:
    """Fetches the humans-in-space count from Open Notify (no API key).

    `fetcher` is injectable so tests run fully offline. `urls` defaults to the
    HTTPS-then-HTTP pair, tried in order; any failure (or an unusable body) yields
    None and the scene just doesn't play — we never present a stale count as live.
    """

    def __init__(self, fetcher: Callable[[str], dict] = _default_fetch,
                 urls=ASTROS_URLS):
        self._fetch = fetcher
        self._urls = tuple(urls)

    def fetch(self) -> Optional[HumansInSpace]:
        for url in self._urls:
            try:
                snap = _parse(self._fetch(url))
            except Exception:
                snap = None
            if snap is not None:
                return snap
        return None
