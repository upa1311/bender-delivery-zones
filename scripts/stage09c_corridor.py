#!/usr/bin/env python
"""Stage 09C — VERIFIED BORISOVKA CORRIDOR.

Owner ground-truth: bus route №5 reaches Borisovka over the Кишинёв–Тирасполь
ПУТЕПРОВОД (a bridge / grade-separated interchange), NOT a level crossing. This
proves the corridor in OSM (ways + nodes + bridge/layer/oneway), confirms it is
in the local PBF and the OSRM graph, force-routes it to Borisovka homes, and
compares four routes: unrestricted OSRM fastest, the owner corridor (forced over
the путепровод), the shortest-distance route, and the current zoning route
(fastest). It CORRECTS the Stage 09A "railway barrier forces a southern loop"
wording. Read-only; no OSM edit, no immutable release, no Direct, no price, no
new zone.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage09_engine import (  # noqa: E402
    ORIGINS,
    haversine_km,
    load_address_points,
    nearest_osm_place,
)
from stage09b_entries import build_topo  # noqa: E402
from stage09b_routes import route_detailed, validate_segments  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
CENTRAL = (ORIGINS[0]["lon"], ORIGINS[0]["lat"])
# Owner-named route-5 / access corridor streets (OSM names).
CORRIDOR_STREETS = [
    "Кишинёв-Тирасполь", "улица Ермакова", "улица Петровского",
    "Тираспольская улица", "улица Титова", "улица Богдана Хмельницкого",
    "улица 50 лет ВЛКСМ", "улица Осипенко", "улица Дружбы", "Кишинёвская улица",
]
PUTEPROVOD = (29.477691, 46.840768)  # midpoint of bridge way 28796004 (layer 2)
CURRENT_EDGES = [2.424, 4.076, 5.577, 9.692]


def zone_of(km):
    for i, e in enumerate(CURRENT_EDGES):
        if km <= e:
            return i + 1
    return 4


def osm_match(h):
    rows = []
    for name in CORRIDOR_STREETS:
        ws = [(wid, w) for wid, w in h.ways.items()
              if w["kind"] == "car" and (w["tags"].get("name") == name
              or name.lower() in (w["tags"].get("name") or "").lower())]
        for wid, w in ws:
            t = w["tags"]
            # OSRM-graph presence: route two points on this way
            cs = w["coords"]
            a, b = cs[0], cs[-1]
            r = route_detailed([(a[0], a[1]), (b[0], b[1])])
            in_osrm = bool(r and r["distance_km"] is not None)
            rows.append({
                "corridor_street": name, "osm_way_id": wid,
                "way_name": t.get("name") or "", "highway": t.get("highway"),
                "bridge": t.get("bridge") or "", "tunnel": t.get("tunnel") or "",
                "layer": t.get("layer") or "", "oneway": t.get("oneway") or "",
                "maxspeed": t.get("maxspeed") or "", "access": t.get("access") or "",
                "motor_vehicle": t.get("motor_vehicle") or "",
                "n_nodes": len(w["refs"]), "first_node": w["refs"][0], "last_node": w["refs"][-1],
                "present_in_pbf": True, "present_in_osrm_graph": in_osrm,
            })
    return rows


def control_homes(pts):
    bori = [p for p in pts if p["settlement_ru"] == "Бендеры"
            and p["service_status"] in ("standard", "low_density")
            and p["address_status"] == "verified_osm_address"
            and nearest_osm_place(p["lat"], p["lon"])[0] == "Борисовка"]
    bori.sort(key=lambda p: haversine_km(p["lat"], p["lon"], CENTRAL[1], CENTRAL[0]))
    kish1 = next((p for p in bori if "ишин" in (p["street_ru"] or "") and p["housenumber"] == "1"), bori[0])  # noqa: E501
    return {
        "Кишинёвская_1": kish1,
        "Борисовка_start": bori[0],
        "Борисовка_mid": bori[len(bori) // 2],
        "Борисовка_far": bori[-1],
    }, bori


def four_routes(dest):
    fastest = route_detailed([CENTRAL, dest])
    corridor = route_detailed([CENTRAL, PUTEPROVOD, dest])
    shortest = min([fastest] + fastest["alternatives"], key=lambda r: r["distance_km"]) if fastest else None  # noqa: E501
    return fastest, corridor, shortest


def main() -> int:
    (REPO / "reports/stage-09c").mkdir(parents=True, exist_ok=True)
    h = build_topo()
    pts = load_address_points()

    # 1. OSM match for the corridor
    match = osm_match(h)
    _write_csv("docs/data/stage-09c-corridor-osm-match.csv", match)
    putep = [m for m in match if m["corridor_street"] == "Кишинёв-Тирасполь" and m["bridge"] == "yes"]  # noqa: E501
    print(f"corridor OSM ways matched: {len(match)}; путепровод bridge ways: {len(putep)}; "
          f"all present_in_osrm={all(m['present_in_osrm_graph'] for m in match)}")

    # 2. four-route comparison for the control homes
    controls, bori = control_homes(pts)
    comp_rows, map_feats = [], []
    for label, p in controls.items():
        dest = (p["lon"], p["lat"])
        fastest, corridor, shortest = four_routes(dest)
        segs, flags, _ = validate_segments(fastest["nodes"], h.node_to_ways, h.ways)
        cseg, cflags, _ = validate_segments(corridor["nodes"], h.node_to_ways, h.ways)
        comp_rows.append({
            "home": label, "street": p["street_ru"], "house": p["housenumber"],
            "current_zone": p["zone_id"],
            "unrestricted_fastest_km": fastest["distance_km"], "unrestricted_fastest_s": fastest["duration_s"],  # noqa: E501
            "owner_corridor_km": corridor["distance_km"], "owner_corridor_s": corridor["duration_s"],  # noqa: E501
            "shortest_distance_km": shortest["distance_km"], "shortest_distance_s": shortest["duration_s"],  # noqa: E501
            "current_zoning_route_km": fastest["distance_km"],  # zoning used fastest-by-duration
            "corridor_minus_fastest_km": round(corridor["distance_km"] - fastest["distance_km"], 3),
            "corridor_minus_fastest_s": round(corridor["duration_s"] - fastest["duration_s"], 1),
            "fastest_uses_service_segment": "service" in ";".join(flags),
            "corridor_uses_service_segment": "service" in ";".join(cflags),
            "zone_by_fastest_km": zone_of(fastest["distance_km"]),
            "zone_by_shortest_km": zone_of(shortest["distance_km"]),
        })
        for kind, r, _col in [("unrestricted_fastest", fastest, "#d62828"),
                             ("owner_corridor", corridor, "#2563eb"),
                             ("shortest_distance", shortest, "#16a34a")]:
            map_feats.append({"type": "Feature",
                              "geometry": {"type": "LineString", "coordinates": r["geometry"]},
                              "properties": {"home": label, "kind": kind,
                                             "distance_km": r["distance_km"], "duration_s": r["duration_s"]}})  # noqa: E501
        map_feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": list(dest)},  # noqa: E501
                          "properties": {"home": label, "kind": "home"}})
    _write_csv("docs/data/stage-09c-corridor-route-comparison.csv", comp_rows)
    map_feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": list(PUTEPROVOD)},  # noqa: E501
                      "properties": {"kind": "putepovod_bridge_layer2"}})
    map_feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": list(CENTRAL)},  # noqa: E501
                      "properties": {"kind": "central_origin"}})
    (REPO / "docs/data/stage-09c-corridor-routes.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": map_feats}, ensure_ascii=False),
        encoding="utf-8", newline="\n")

    # 3. zone impact: Борисовка homes changing zone if the shortest-distance km is used
    changed = same = 0
    detail = []
    for p in bori:
        f = route_detailed([CENTRAL, (p["lon"], p["lat"])])
        if not f:
            continue
        s = min([f] + f["alternatives"], key=lambda r: r["distance_km"])
        zf, zs = zone_of(f["distance_km"]), zone_of(s["distance_km"])
        if zf != zs:
            changed += 1
            detail.append({"street": p["street_ru"], "house": p["housenumber"],
                           "fastest_km": f["distance_km"], "shortest_km": s["distance_km"],
                           "zone_by_fastest": zf, "zone_by_shortest": zs})
        else:
            same += 1
    (REPO / "docs/data/stage-09c-borisovka-zone-impact.json").write_text(
        json.dumps({
            "basis": "current v1.1 edges on CENTRAL-origin road km (proxy); not a republish",
            "edges_km": CURRENT_EDGES,
            "borisovka_homes": len(bori),
            "zone_changes_fastest_vs_shortest": changed, "unchanged": same,
            "note": "If the km tariff used the shortest valid (corridor) route instead of the "
                    "fastest-by-duration route, this many Borisovka homes move to a cheaper zone. "
                    "owner_review; no zone is republished.",
            "owner_review_required": True,
            "sample": detail[:40],
        }, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    # 4. origin position vs the развязка
    origin_note = {
        "central_origin_lonlat": list(CENTRAL),
        "putepovod_lonlat": list(PUTEPROVOD),
        "origin_is_south_of_rail_belt": CENTRAL[1] < PUTEPROVOD[1],
        "straight_km_origin_to_putepovod": round(haversine_km(CENTRAL[1], CENTRAL[0], PUTEPROVOD[1], PUTEPROVOD[0]), 3),  # noqa: E501
        "interpretation": "Central origin sits SOUTH of the rail belt in the city core "
                          "(demand centre), on the correct city side; Borisovka is NW across "
                          "the belt and is reached over the путепровод. The origin is NOT east "
                          "of the interchange nor on the wrong side of the tracks.",
    }
    (REPO / "docs/data/stage-09c-corridor-routes.geojson")  # already written
    print("four-route comparison:")
    for r in comp_rows:
        print(f"  {r['home']:16s} fastest {r['unrestricted_fastest_km']}km/{r['unrestricted_fastest_s']}s "  # noqa: E501
              f"corridor {r['owner_corridor_km']}km/{r['owner_corridor_s']}s "
              f"shortest {r['shortest_distance_km']}km  "
              f"zone f{r['zone_by_fastest_km']}->s{r['zone_by_shortest_km']}")
    print(f"Borisovka zone changes (fastest->shortest km): {changed}/{len(bori)}")
    (REPO / "reports/stage-09c/_origin.json").write_text(
        json.dumps(origin_note, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    return 0


def _write_csv(rel, rows):
    p = REPO / rel
    if not rows:
        p.write_text("", encoding="utf-8")
        return
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
