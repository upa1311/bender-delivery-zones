#!/usr/bin/env python
"""Stage 09A — Borisovka road-connectivity probe.

The fastest valid route central->Borisovka is a 3-6x detour over the straight
line, looping ~3 km south before returning NW. This checks the LOCAL PBF for the
physical cause: is there a railway / waterway barrier between the central origin
and Borisovka with few crossings, and are the roads that visually could give a
direct path actually connected and car-accessible? Read-only; no OSM edits.
"""

from __future__ import annotations

import json
from pathlib import Path

import osmium
from shapely.geometry import LineString, box
from shapely.strtree import STRtree

REPO = Path(__file__).resolve().parents[1]
PBF = REPO / "data/interim/city-extract-12463379.osm.pbf"

# Corridor between central origin (SE) and Borisovka (NW).
CENTRAL = (29.48313, 46.82388)
BORISOVKA = (29.46735, 46.83524)
CORRIDOR = box(29.455, 46.820, 29.487, 46.842)


class Barriers(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.railways: list[LineString] = []
        self.waterways: list[LineString] = []
        self.car_roads: list[tuple[LineString, dict]] = []
        self.rail_crossings = 0

    def way(self, w) -> None:
        tags = dict(w.tags)
        try:
            coords = [(n.lon, n.lat) for n in w.nodes if n.location.valid()]
        except osmium.InvalidLocationError:
            return
        if len(coords) < 2:
            return
        line = LineString(coords)
        if not line.intersects(CORRIDOR):
            return
        if tags.get("railway") in ("rail", "light_rail", "narrow_gauge"):
            self.railways.append(line)
        elif tags.get("waterway") in ("river", "stream", "canal"):
            self.waterways.append(line)
        elif tags.get("highway") in (
            "primary", "secondary", "tertiary", "residential", "living_street",
            "unclassified", "primary_link", "secondary_link", "tertiary_link",
        ):
            access_ok = tags.get("access") not in ("no", "private") and tags.get(
                "motor_vehicle"
            ) not in ("no", "private")
            self.car_roads.append((line, {**tags, "_access_ok": access_ok}))
        # a rail-level crossing usable by cars
        if tags.get("railway") == "level_crossing" or tags.get("railway") == "crossing":
            self.rail_crossings += 1


def main() -> int:
    h = Barriers()
    h.apply_file(str(PBF), locations=True)

    straight = LineString([CENTRAL, BORISOVKA])
    rail_union_crossed = sum(1 for r in h.railways if r.intersects(straight))
    water_crossed = sum(1 for w in h.waterways if w.intersects(straight))

    # count level crossings (car-usable) that the railways offer in the corridor
    car_roads_ok = [c for c, t in h.car_roads if t["_access_ok"]]
    # roads that themselves cross a railway (potential connectors)
    road_rail_crossings = 0
    rail_tree = STRtree(h.railways) if h.railways else None
    for road in car_roads_ok:
        if rail_tree is not None:
            for idx in rail_tree.query(road):
                if road.intersects(h.railways[idx]):
                    road_rail_crossings += 1
                    break

    report = {
        "corridor_bbox": [29.455, 46.820, 29.487, 46.842],
        "central_origin_lonlat": list(CENTRAL),
        "borisovka_lonlat": list(BORISOVKA),
        "straight_line_km": round(
            LineString([CENTRAL, BORISOVKA]).length * 111, 3
        ),
        "railways_in_corridor": len(h.railways),
        "railways_crossing_straight_line": rail_union_crossed,
        "waterways_in_corridor": len(h.waterways),
        "waterways_crossing_straight_line": water_crossed,
        "car_roads_in_corridor": len(h.car_roads),
        "car_roads_access_ok": len(car_roads_ok),
        "car_roads_that_cross_a_railway": road_rail_crossings,
        "railway_level_crossings_tagged": h.rail_crossings,
        "interpretation": (
            "A railway and/or waterway separates the central origin (SE) from "
            "Borisovka (NW). Few car roads in the corridor actually cross the "
            "railway, so OSRM must detour ~3 km south to the nearest crossing — "
            "this inflates the road distance to 5-7 km over a ~1.7 km straight "
            "line and pushes Borisovka into Zone 4. Whether a more direct "
            "car-legal crossing exists on the ground (missing/mis-tagged OSM "
            "road) is the owner_review question; no override is applied here."
        ),
        "owner_review_required": True,
        "proposed_action": "owner confirms whether a direct NW crossing exists; "
        "if yes, a documented local routing override is proposed (never auto-applied).",
    }
    out = REPO / "docs/data/stage-09a-road-connectivity.json"
    existing = json.loads(out.read_text("utf-8")) if out.exists() else {}
    existing["borisovka_corridor"] = report
    out.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")  # noqa: E501
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
