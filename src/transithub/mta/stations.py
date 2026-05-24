import csv
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import List, Optional, Set, Tuple


@dataclass(frozen=True)
class Station:
    gtfs_stop_id: str
    name: str
    borough: str
    routes: List[str]
    north_label: str
    south_label: str


def _csv_path():
    return files("transithub.mta").joinpath("Stations.csv")


@lru_cache(maxsize=1)
def load_stations() -> List[Station]:
    out: List[Station] = []
    with _csv_path().open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out.append(Station(
                gtfs_stop_id=row["GTFS Stop ID"].strip(),
                name=row["Stop Name"].strip(),
                borough=row["Borough"].strip(),
                routes=row["Daytime Routes"].split(),
                north_label=row["North Direction Label"].strip(),
                south_label=row["South Direction Label"].strip(),
            ))
    return out


def search_stations(query: str) -> List[Station]:
    q = query.strip().lower()
    return [s for s in load_stations() if q in s.name.lower()]


def station_by_stop_id(stop_id: str) -> Optional[Station]:
    sid = stop_id.strip().upper()
    for s in load_stations():
        if s.gtfs_stop_id.upper() == sid:
            return s
    return None


_WORD_RE = re.compile(r"[a-z]{3,}")
# Generic words that don't identify a direction/terminal.
_GENERIC = {"and", "the", "via", "bound", "ave", "avenue", "street", "trains", "train"}


def label_terms(label: str) -> Set[str]:
    """Meaningful direction/terminal words from a label like 'Canarsie - Rockaway Parkway'."""
    return {w for w in _WORD_RE.findall(label.lower()) if w not in _GENERIC}


def direction_terms(station: Station, direction: str) -> Tuple[Set[str], Set[str]]:
    """(terms for the tracked direction, terms for the opposite direction)."""
    north, south = label_terms(station.north_label), label_terms(station.south_label)
    return (north, south) if direction.upper() == "N" else (south, north)
