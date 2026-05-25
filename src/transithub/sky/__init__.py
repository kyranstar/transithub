"""Sky events: the moon, the ISS overhead, and the plane passing above you.

All keyless. The moon is computed locally (no network). The ISS pass is computed
locally with SGP4 from a keyless Celestrak TLE; planes come from keyless
community ADS-B feeds, with the flight route looked up from keyless hexdb.io. The
pieces here are the data shapes and the client that fills them; the scenes and
sources that *show* them live in ``display/scenes/sky.py``."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class IssPass:
    """The next overhead pass of the ISS for the configured spot.

    Times are tz-aware UTC. ``rise_dir`` is the compass point of the horizon the
    station rises from. ``visible`` is True only when we could establish the
    station is sunlit while the observer is in darkness (a naked-eye pass)."""
    start: datetime          # rises above the ~10-deg horizon mask
    peak: datetime           # highest elevation
    end: datetime            # drops back below the mask
    max_el_deg: float        # peak elevation, degrees
    rise_dir: str            # N / NE / E / SE / S / SW / W / NW
    visible: bool


@dataclass(frozen=True)
class Plane:
    """The nearest airborne aircraft currently over you.

    ``route`` is the flight's origin -> destination as a short IATA label (e.g.
    ``"JFK > LHR"``), looked up by callsign from keyless hexdb.io. It is None when
    no route is on file — we never fabricate one."""
    callsign: str
    alt_ft: int
    heading_deg: float
    dir: str                 # compass point the plane is heading toward
    route: Optional[str] = None   # e.g. "JFK > LHR"; None when unknown


@dataclass(frozen=True)
class SkyData:
    """Snapshot the coordinator places on ``ctx.sky`` for the sources to read.

    The two fields refresh on different cadences (see ``SkyClient``), so the
    coordinator may set them independently."""
    next_iss_pass: Optional[IssPass] = None
    plane_overhead: Optional[Plane] = None


from .client import SkyClient  # noqa: E402  (re-export; avoids a circular import at top)

__all__ = ["IssPass", "Plane", "SkyData", "SkyClient"]
