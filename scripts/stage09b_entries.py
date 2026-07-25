#!/usr/bin/env python
"""Stage 09B — catalog of REAL car entries per district/settlement.

An entry is a car-legal way that connects the district to the outside road graph
by a **shared graph node** (not a mere geometric crossing). Settlements
(Парканы/Гиска/Протягайловка) use their OSM admin boundary; Bender suburbs
(Борисовка/Хомутяновка) — which have no OSM boundary — use a buffer around their
verified addresses, and their true "entries" are the rail LEVEL_CROSSING nodes
plus car ways crossing that buffer. Северный has no OSM place object -> owner
review. Read-only; no OSM edit, no release, no Direct, no zone.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from shapely.geometry import LineString, MultiPoint, Point, shape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage09_engine import OSM_PLACES, load_address_points  # noqa: E402
from stage09b_topology import Topo, car_access_ok  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
EXTRACTS = [
    "data/interim/city-extract-12463379.osm.pbf",  # Бендеры
    "data/interim/city-extract-7431263.osm.pbf",   # Парканы
    "data/interim/city-extract-12215667.osm.pbf",  # Гиска
    "data/interim/city-extract-12463378.osm.pbf",  # Протягайловка
]
SETTLEMENTS = {"parkany": "Парканы", "giska": "Гиска", "protyagailovka": "Протягайловка"}
SUBURBS = ["Борисовка", "Хомутяновка"]


def build_topo() -> Topo:
    h = Topo()
    for e in EXTRACTS:
        p = REPO / e
        if p.exists():
            h.apply_file(str(p), locations=True)
    return h


def boundaries() -> dict:
    gj = json.loads((REPO / "docs/data/source-boundaries.geojson").read_text("utf-8"))
    return {f["properties"]["key"]: shape(f["geometry"]) for f in gj["features"]}


def suburb_area(place_name: str, pts: list[dict]):
    plat, plon = OSM_PLACES[place_name]
    near = [
        (p["lon"], p["lat"]) for p in pts
        if p["settlement_ru"] == "Бендеры"
        and abs(p["lat"] - plat) < 0.02 and abs(p["lon"] - plon) < 0.02
    ]
    # keep points whose nearest OSM place is this suburb
    from stage09_engine import nearest_osm_place
    mine = [(lon, lat) for lon, lat in near if nearest_osm_place(lat, lon)[0] == place_name]
    if len(mine) < 3:
        return Point(plon, plat).buffer(0.004)
    return MultiPoint(mine).convex_hull.buffer(0.0015)  # ~150 m halo


def entries_for(area, h: Topo, level_nodes_pts) -> list[dict]:
    """Car ways crossing the area perimeter with nodes both inside & outside."""
    perim = area.boundary
    out = []
    for wid, w in h.ways.items():
        if w["kind"] != "car":
            continue
        line = LineString(w["coords"])
        if not line.intersects(perim):
            continue
        refs_in = any(area.contains(Point(c)) for c in w["coords"])
        refs_out = any(not area.contains(Point(c)) for c in w["coords"])
        if not (refs_in and refs_out):
            continue
        t = w["tags"]
        cross = line.intersection(perim)
        pt = cross.representative_point() if not cross.is_empty else line.interpolate(0.5, True)
        # connectivity: does this way share a node with any OTHER car way (graph link)?
        shared = False
        for r in w["refs"]:
            if len(h.node_to_ways.get(r, set())) > 1:
                shared = True
                break
        out.append({
            "road_name": t.get("name") or t.get("ru_display") or "",
            "osm_way_id": wid,
            "entry_lon": round(pt.x, 6),
            "entry_lat": round(pt.y, 6),
            "highway": t.get("highway"),
            "access": t.get("access") or "",
            "vehicle": t.get("vehicle") or "",
            "motor_vehicle": t.get("motor_vehicle") or "",
            "oneway": t.get("oneway") or "",
            "maxspeed": t.get("maxspeed") or "",
            "surface": t.get("surface") or "",
            "bridge": t.get("bridge") or "",
            "tunnel": t.get("tunnel") or "",
            "layer": t.get("layer") or "",
            "car_access_ok": car_access_ok(t),
            "connected_to_city_graph": shared,
            "owner_review_required": (not car_access_ok(t)) or (not shared),
        })
    # dedup by (name, rounded coord)
    seen, dedup = set(), []
    for e in out:
        k = (e["road_name"], round(e["entry_lon"], 4), round(e["entry_lat"], 4))
        if k not in seen:
            seen.add(k)
            dedup.append(e)
    return dedup


def main() -> int:
    h = build_topo()
    bnds = boundaries()
    pts = load_address_points()
    level_pts = list(h.level_crossings.values())

    rows = []
    # settlements — real admin boundary
    for key, name in SETTLEMENTS.items():
        if key not in bnds:
            continue
        for e in entries_for(bnds[key], h, level_pts):
            rows.append({"district_or_settlement": name, "basis": "osm_admin_boundary", **e})
    # Bender suburbs — address-hull buffer; entries include rail level crossings
    for name in SUBURBS:
        area = suburb_area(name, pts)
        for e in entries_for(area, h, level_pts):
            rows.append({"district_or_settlement": name, "basis": "address_hull_buffer", **e})
        # rail level crossings inside/near the suburb area = real car access across the belt
        for lon, lat in level_pts:
            if area.buffer(0.001).contains(Point(lon, lat)):
                rows.append({
                    "district_or_settlement": name, "basis": "rail_level_crossing_node",
                    "road_name": "(railway level_crossing)", "osm_way_id": "",
                    "entry_lon": round(lon, 6), "entry_lat": round(lat, 6),
                    "highway": "level_crossing", "access": "", "vehicle": "",
                    "motor_vehicle": "", "oneway": "", "maxspeed": "", "surface": "",
                    "bridge": "", "tunnel": "", "layer": "", "car_access_ok": True,
                    "connected_to_city_graph": True, "owner_review_required": False,
                })
    # Северный — no OSM place object
    rows.append({
        "district_or_settlement": "Северный", "basis": "no_osm_place_owner_review",
        "road_name": "", "osm_way_id": "", "entry_lon": "", "entry_lat": "",
        "highway": "", "access": "", "vehicle": "", "motor_vehicle": "", "oneway": "",
        "maxspeed": "", "surface": "", "bridge": "", "tunnel": "", "layer": "",
        "car_access_ok": "", "connected_to_city_graph": "", "owner_review_required": True,
    })

    for i, r in enumerate(rows):
        r["entry_id"] = f"{r['district_or_settlement'][:3]}-{i:03d}"

    cols = ["entry_id", "district_or_settlement", "basis", "road_name", "osm_way_id",
            "entry_lon", "entry_lat", "highway", "access", "vehicle", "motor_vehicle",
            "oneway", "maxspeed", "surface", "bridge", "tunnel", "layer",
            "car_access_ok", "connected_to_city_graph", "owner_review_required"]
    out = REPO / "docs/data/stage-09b-district-entries.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    feats = [{"type": "Feature",
              "geometry": {"type": "Point", "coordinates": [r["entry_lon"], r["entry_lat"]]}
              if r["entry_lon"] != "" else None,
              "properties": {k: r.get(k) for k in cols}} for r in rows]
    (REPO / "docs/data/stage-09b-district-entries.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False),
        encoding="utf-8", newline="\n")

    from collections import Counter
    per = Counter(r["district_or_settlement"] for r in rows if r.get("osm_way_id") != "" or r["basis"].startswith("rail"))  # noqa: E501
    print("entries per district:", dict(per))
    print("wrote", out.name, len(rows), "rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
