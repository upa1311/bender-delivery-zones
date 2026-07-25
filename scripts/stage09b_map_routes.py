#!/usr/bin/env python
"""Stage 09B — route geometries for the QA map: for one representative control
home per district, the global fastest-time route, the shortest-distance route,
and the route forced through each key entry, plus the original point and the OSRM
snap. Read-only; no OSM edit, no release, no Direct, no zone."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage09_engine import ORIGINS, load_address_points, nearest, nearest_osm_place  # noqa: E402
from stage09b_routes import key_entries, route_detailed  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
PICK = {
    "Борисовка": ("Кишинёвская улица", None),
    "Хомутяновка": (None, None),
    "Парканы": (None, None),
    "Гиска": (None, None),
    "Протягайловка": (None, None),
}


def representative(pts, dname):
    serv = [p for p in pts if p["service_status"] in ("standard", "low_density")
            and p["address_status"] == "verified_osm_address"]
    for p in serv:
        p["district"] = (nearest_osm_place(p["lat"], p["lon"])[0]
                         if p["settlement_ru"] == "Бендеры" else p["settlement_ru"])
    cand = [p for p in serv if p["district"] == dname]
    street, _ = PICK.get(dname, (None, None))
    if street:
        s = [p for p in cand if street in (p["street_ru"] or "")]
        if s:
            return s[0]
    return cand[0] if cand else None


def line_feat(geom, props):
    return {"type": "Feature", "geometry": {"type": "LineString", "coordinates": geom},
            "properties": props}


def main() -> int:
    pts = load_address_points()
    entries = key_entries()
    feats = []
    for dname in PICK:
        p = representative(pts, dname)
        if not p:
            continue
        dest = (p["lon"], p["lat"])
        fast = route_detailed([(ORIGINS[0]["lon"], ORIGINS[0]["lat"]), dest])
        if fast:
            feats.append(line_feat(fast["geometry"], {
                "district": dname, "uid": p["uid"], "kind": "fastest_time",
                "distance_km": fast["distance_km"], "duration_s": fast["duration_s"]}))
            shortest = min([fast] + fast["alternatives"], key=lambda r: r["distance_km"])
            feats.append(line_feat(shortest["geometry"], {
                "district": dname, "uid": p["uid"], "kind": "shortest_distance",
                "distance_km": shortest["distance_km"], "duration_s": shortest["duration_s"]}))
        for e in entries.get(dname, [])[:8]:
            via = route_detailed([(ORIGINS[0]["lon"], ORIGINS[0]["lat"]),
                                  (float(e["entry_lon"]), float(e["entry_lat"])), dest])
            if via:
                feats.append(line_feat(via["geometry"], {
                    "district": dname, "uid": p["uid"], "kind": "via_entry",
                    "entry_id": e["entry_id"], "entry_road": e["road_name"],
                    "distance_km": via["distance_km"], "duration_s": via["duration_s"]}))
        snap = nearest(p["lon"], p["lat"])
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": dest},
                      "properties": {"district": dname, "uid": p["uid"], "kind": "address_point"}})
        if snap.get("ok"):
            feats.append({"type": "Feature",
                          "geometry": {"type": "Point", "coordinates": [snap["snap_lon"], snap["snap_lat"]]},  # noqa: E501
                          "properties": {"district": dname, "uid": p["uid"], "kind": "osrm_snap",
                                         "snap_distance_m": snap["snap_distance_m"]}})
    (REPO / "docs/data/stage-09b-map-routes.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False),
        encoding="utf-8", newline="\n")
    print("wrote stage-09b-map-routes.geojson", len(feats), "features")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# silence unused-import lint (csv kept for parity with sibling scripts)
_ = csv
