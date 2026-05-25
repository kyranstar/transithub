"""Space interjections: humans in orbit + a recent Earth photo from NASA EPIC.

`SpaceData` is the snapshot the coordinator drops onto `Context.space`; its two
fields move on different cadences, so the client exposes `humans()` and `earth()`
separately for two pollers.

Recommended cadences (these feeds change slowly and EPIC is heavy):

- ``humans()`` — every ~30 min. First play after a few minutes so the trains lead.
- ``earth()``  — every ~60 min. EPIC publishes only a handful of frames a day and
  each PNG is ~3 MB, so polling faster wastes bandwidth for no new picture. The
  processed 64x32 frame is cached on the snapshot, so renders are free between
  polls.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .epic import EarthFrame, EpicClient
from .humans import HumansInSpace, HumansInSpaceClient

__all__ = [
    "SpaceData", "SpaceClient",
    "HumansInSpace", "HumansInSpaceClient",
    "EarthFrame", "EpicClient",
]


@dataclass
class SpaceData:
    """Latest space snapshots. Either field may be None before/around a failed poll."""
    humans: Optional[HumansInSpace] = None
    earth: Optional[EarthFrame] = None


class SpaceClient:
    """Bundles the two space feeds. `humans()` and `earth()` are polled separately
    (different cadences) by the coordinator, which folds the results into a
    `SpaceData` on `Context.space`. Each returns None on failure — never raises."""

    def __init__(self, humans_client: Optional[HumansInSpaceClient] = None,
                 epic_client: Optional[EpicClient] = None):
        self.humans_client = humans_client or HumansInSpaceClient()
        self.epic_client = epic_client or EpicClient()

    def humans(self) -> Optional[HumansInSpace]:
        return self.humans_client.fetch()

    def earth(self) -> Optional[EarthFrame]:
        return self.epic_client.fetch()
