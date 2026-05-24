#!/usr/bin/env python3
"""Find GTFS stop IDs and direction labels for a station name.

Usage: python scripts/find_station.py "dekalb"
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from transithub.mta.stations import search_stations  # noqa: E402


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 1
    results = search_stations(argv[1])
    if not results:
        print(f"No stations matching {argv[1]!r}")
        return 1
    for s in results:
        print(f"{s.gtfs_stop_id:<5} {s.name} [{'/'.join(s.routes)}]  ({s.borough})")
        print(f"        N -> {s.north_label}")
        print(f"        S -> {s.south_label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
