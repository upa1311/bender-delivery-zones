#!/usr/bin/env python
"""Probe: list OSM place=suburb/quarter/neighbourhood objects in the Bender area.

Read-only. Used to see which district names OSM actually carries (so Stage 09
labels addresses by REAL places, never invented boundaries).
"""

from __future__ import annotations

import sys

import osmium

sys.stdout.reconfigure(encoding="utf-8")

PLACES = {"suburb", "quarter", "neighbourhood", "city_block", "borough", "locality"}


class Probe(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[tuple] = []

    def node(self, n) -> None:
        tags = dict(n.tags)
        place = tags.get("place")
        if place in PLACES:
            self.rows.append(
                (
                    "node",
                    n.id,
                    place,
                    tags.get("name"),
                    tags.get("name:ru"),
                    tags.get("name:ro"),
                    round(n.location.lat, 6),
                    round(n.location.lon, 6),
                )
            )

    def area(self, a) -> None:
        tags = dict(a.tags)
        place = tags.get("place")
        if place in PLACES:
            self.rows.append(
                (
                    "area",
                    a.orig_id(),
                    place,
                    tags.get("name"),
                    tags.get("name:ru"),
                    tags.get("name:ro"),
                    None,
                    None,
                )
            )


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "data/interim/city-extract-12463379.osm.pbf"
    h = Probe()
    h.apply_file(path, locations=True)
    for r in sorted(h.rows, key=lambda x: (x[2] or "", str(x[3]))):
        print("|".join("" if v is None else str(v) for v in r))
    print(f"# total place features: {len(h.rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
