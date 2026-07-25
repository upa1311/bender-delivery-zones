#!/usr/bin/env python
"""Stage 09B — real OSM road/rail topology (nodes + ways + relations).

Fixes the Stage 09A shortcut that treated a *geometric* line crossing as a
connection. Here connectivity is proven by a **shared graph node** (or correct
bridge/tunnel/layer grade separation), reading OSM **nodes** (so
`railway=level_crossing` on a node is counted), ways and relations (turn
restrictions). Every road/rail crossing is classified:

  LEVEL_CROSSING              shared node tagged railway=level_crossing (car may cross)
  BRIDGE / TUNNEL             road grade-separated over/under the rail (no crossing needed)
  GEOMETRY_ONLY_NO_CONNECTION lines cross on the map but share no node & no grade sep
  BROKEN_CONNECTIVITY         shared node exists but access/barrier blocks cars
  UNKNOWN_OWNER_REVIEW        ambiguous -> owner review

Read-only. No OSM edit, no immutable release, no Direct, no prices, no new zone.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import osmium
from shapely.geometry import LineString
from shapely.strtree import STRtree

REPO = Path(__file__).resolve().parents[1]

CAR_HIGHWAYS = {
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
    "residential", "living_street", "service", "road",
    "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
}
RAIL = {"rail", "light_rail", "narrow_gauge", "tram", "subway"}


class Topo(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.ways: dict[int, dict] = {}
        self.node_to_ways: dict[int, set[int]] = {}
        self.level_crossings: dict[int, tuple[float, float]] = {}  # node id -> lon,lat
        self.barriers: dict[int, dict] = {}
        self.turn_restrictions = 0

    def node(self, n) -> None:
        tags = dict(n.tags)
        if tags.get("railway") in ("level_crossing", "crossing") or tags.get(
            "railway"
        ) == "crossing":
            if n.location.valid():
                self.level_crossings[n.id] = (n.location.lon, n.location.lat)
        if tags.get("barrier"):
            if n.location.valid():
                self.barriers[n.id] = {
                    "lon": n.location.lon, "lat": n.location.lat, "barrier": tags["barrier"],
                    "access": tags.get("access"),
                }

    def way(self, w) -> None:
        tags = dict(w.tags)
        hw = tags.get("highway")
        rw = tags.get("railway")
        if hw not in CAR_HIGHWAYS and rw not in RAIL:
            return
        try:
            refs = [n.ref for n in w.nodes]
            coords = [(n.lon, n.lat) for n in w.nodes if n.location.valid()]
        except osmium.InvalidLocationError:
            return
        if len(coords) < 2:
            return
        kind = "rail" if rw in RAIL else "car"
        self.ways[w.id] = {
            "id": w.id, "kind": kind, "tags": tags, "refs": refs, "coords": coords,
        }
        for r in refs:
            self.node_to_ways.setdefault(r, set()).add(w.id)

    def relation(self, r) -> None:
        tags = dict(r.tags)
        if tags.get("type") == "restriction" or "restriction" in tags:
            self.turn_restrictions += 1


def car_access_ok(tags: dict) -> bool:
    if tags.get("access") in ("no", "private", "customers"):
        return False
    if tags.get("motor_vehicle") in ("no", "private"):
        return False
    if tags.get("vehicle") in ("no", "private"):
        return False
    return True


def classify_crossing(car: dict, rail: dict, level_nodes: set[int]) -> str:
    shared = set(car["refs"]) & set(rail["refs"])
    ct, rt = car["tags"], rail["tags"]
    car_bridge = ct.get("bridge") not in (None, "no")
    car_tunnel = ct.get("tunnel") not in (None, "no")
    rail_bridge = rt.get("bridge") not in (None, "no")
    rail_tunnel = rt.get("tunnel") not in (None, "no")
    car_layer = ct.get("layer")
    rail_layer = rt.get("layer")
    graded = (
        car_bridge or car_tunnel or rail_bridge or rail_tunnel
        or (car_layer is not None and car_layer != rail_layer)
    )
    if shared & level_nodes:
        return "BROKEN_CONNECTIVITY" if not car_access_ok(ct) else "LEVEL_CROSSING"
    if shared:
        # shared node but not tagged as a crossing — unmarked; car may or may not pass
        return "UNKNOWN_OWNER_REVIEW"
    if graded:
        return "BRIDGE" if (car_bridge or rail_tunnel) else "TUNNEL" if (car_tunnel or rail_bridge) else "BRIDGE"  # noqa: E501
    return "GEOMETRY_ONLY_NO_CONNECTION"


def build(pbf: Path) -> Topo:
    h = Topo()
    h.apply_file(str(pbf), locations=True)
    return h


def crossings_report(h: Topo) -> list[dict]:
    rails = [(wid, w) for wid, w in h.ways.items() if w["kind"] == "rail"]
    cars = [(wid, w) for wid, w in h.ways.items() if w["kind"] == "car"]
    rail_lines = [LineString(w["coords"]) for _, w in rails]
    rail_tree = STRtree(rail_lines)
    level_nodes = set(h.level_crossings)
    out = []
    for cid, cw in cars:
        cline = LineString(cw["coords"])
        for idx in rail_tree.query(cline):
            rid, rw = rails[idx]
            if not cline.intersects(rail_lines[idx]):
                continue
            cls = classify_crossing(cw, rw, level_nodes)
            inter = cline.intersection(rail_lines[idx])
            pt = inter.representative_point() if not inter.is_empty else cline.interpolate(0.5, normalized=True)  # noqa: E501
            out.append({
                "car_way_id": cid,
                "car_name": cw["tags"].get("name") or cw["tags"].get("ru_display") or "",
                "car_highway": cw["tags"].get("highway"),
                "rail_way_id": rid,
                "classification": cls,
                "car_access": cw["tags"].get("access") or "",
                "car_motor_vehicle": cw["tags"].get("motor_vehicle") or "",
                "car_bridge": cw["tags"].get("bridge") or "",
                "car_tunnel": cw["tags"].get("tunnel") or "",
                "car_layer": cw["tags"].get("layer") or "",
                "lon": round(pt.x, 6),
                "lat": round(pt.y, 6),
            })
    return out


def main() -> int:
    pbf = REPO / (sys.argv[1] if len(sys.argv) > 1 else "data/interim/city-extract-12463379.osm.pbf")  # noqa: E501
    h = build(pbf)
    rows = crossings_report(h)
    from collections import Counter
    cls_counts = Counter(r["classification"] for r in rows)
    print(f"extract={pbf.name}")
    print(f"car ways={sum(1 for w in h.ways.values() if w['kind']=='car')} "
          f"rail ways={sum(1 for w in h.ways.values() if w['kind']=='rail')} "
          f"level_crossing nodes={len(h.level_crossings)} "
          f"barrier nodes={len(h.barriers)} turn_restrictions={h.turn_restrictions}")
    print("road/rail crossing classes:", dict(cls_counts))
    real_car_cross = sum(v for k, v in cls_counts.items()
                         if k in ("LEVEL_CROSSING", "BRIDGE", "TUNNEL"))
    print(f"REAL car crossings (level/bridge/tunnel): {real_car_cross}")
    print(f"geometry-only (NOT a crossing): {cls_counts.get('GEOMETRY_ONLY_NO_CONNECTION', 0)}")

    out = REPO / "docs/data/stage-09b-road-rail-crossings.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        cols = ["car_way_id", "car_name", "car_highway", "rail_way_id", "classification",
                "car_access", "car_motor_vehicle", "car_bridge", "car_tunnel", "car_layer",
                "lon", "lat"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print("wrote", out.name, len(rows), "crossings")

    # level-crossing node coords for the QA map / entries
    (REPO / "docs/data/stage-09b-level-crossings.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
             "properties": {"node_id": nid, "railway": "level_crossing"}}
            for nid, (lon, lat) in h.level_crossings.items()]}, ensure_ascii=False),
        encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
