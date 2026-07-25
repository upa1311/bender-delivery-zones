#!/usr/bin/env python
"""Stage 09C — Khomutyanovka brewery / Ленинский rail corridor + route №5 south.

Owner ground truth: a real car corridor centre -> пивзавод (ул. Дружбы 7,
46.80229/29.47607) -> Ленинский rail crossing -> Хомутяновка, and bus route №5's
southern loop (пл. Героев -> Пивзавод -> Ечина -> Главана -> Старого -> Юг-2 ->
Борисовский рынок). This verifies the crossing in OSM + OSRM (both directions),
force-routes it to Khomutyanovka homes, compares fastest / shortest / forced-
brewery / driver-cost, and checks whether the same south corridor shortens
Borisovka. Read-only; no OSM edit, no immutable release, no Direct, no price, no
new zone. owner_review_required.
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
    nearest,
    nearest_osm_place,
)
from stage09b_entries import build_topo  # noqa: E402
from stage09b_routes import route_detailed, validate_segments  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
CENTRAL = (ORIGINS[0]["lon"], ORIGINS[0]["lat"])
BREWERY = (29.47607, 46.80229)
BREWERY_PRIMARY_LC = (29.47836, 46.80105)  # primary level_crossing near the brewery
# Route №5 south corridor street names (OSM).
ROUTE5_SOUTH = [
    "улица Дружбы", "улица Ечина", "улица Главана", "улица Старого",
    "улица Кирова", "улица Ленина", "Кишинёвская улица",
]
CURRENT_EDGES = [2.424, 4.076, 5.577, 9.692]


def zone_of(km):
    for i, e in enumerate(CURRENT_EDGES):
        if km <= e:
            return i + 1
    return 4


def driver_cost(distance_km, duration_s):
    # provisional: distance dominates, small time term (NOT a Direct price)
    return round(distance_km + 0.3 * duration_s / 60, 3)


def route_uses_point(geometry, pt, tol_m=60):
    return any(haversine_km(lat, lon, pt[1], pt[0]) * 1000 < tol_m for lon, lat in geometry)


def brewery_crossing_facts(h):
    """All car ways sharing a level_crossing node near the brewery + OSRM presence."""
    lc = set(h.level_crossings)
    rows = []
    for wid, w in h.ways.items():
        if w["kind"] != "car":
            continue
        if not any(abs(lon - BREWERY[0]) < 0.005 and abs(lat - BREWERY[1]) < 0.005
                   for lon, lat in w["coords"]):
            continue
        shared_lc = set(w["refs"]) & lc
        if not shared_lc:
            continue
        t = w["tags"]
        node_id = next(iter(shared_lc))
        clon, clat = h.level_crossings[node_id]
        # OSRM both directions across this way
        a, b = w["coords"][0], w["coords"][-1]
        fwd = route_detailed([(a[0], a[1]), (b[0], b[1])])
        rev = route_detailed([(b[0], b[1]), (a[0], a[1])])
        rows.append({
            "osm_way_id": wid, "way_name": t.get("name") or "",
            "highway": t.get("highway"), "railway": "level_crossing",
            "level_crossing_node_id": node_id, "crossing_lon": round(clon, 6),
            "crossing_lat": round(clat, 6), "bridge": t.get("bridge") or "",
            "tunnel": t.get("tunnel") or "", "layer": t.get("layer") or "",
            "oneway": t.get("oneway") or "", "access": t.get("access") or "",
            "vehicle": t.get("vehicle") or "", "motor_vehicle": t.get("motor_vehicle") or "",
            "maxspeed": t.get("maxspeed") or "",
            "present_in_pbf": True,
            "present_in_osrm_forward": bool(fwd and fwd["distance_km"] is not None),
            "present_in_osrm_reverse": bool(rev and rev["distance_km"] is not None),
        })
    return rows


def route5_osm_match(h):
    rows, feats = [], []
    for name in ROUTE5_SOUTH:
        for wid, w in h.ways.items():
            if w["kind"] != "car":
                continue
            nm = w["tags"].get("name") or ""
            if not (nm == name or name.lower() in nm.lower()):
                continue
            t = w["tags"]
            rows.append({"corridor_street": name, "osm_way_id": wid, "way_name": nm,
                         "highway": t.get("highway"), "bridge": t.get("bridge") or "",
                         "layer": t.get("layer") or "", "oneway": t.get("oneway") or "",
                         "access": t.get("access") or "", "motor_vehicle": t.get("motor_vehicle") or "",  # noqa: E501
                         "maxspeed": t.get("maxspeed") or "", "present_in_pbf": True})
            feats.append({"type": "Feature",
                          "geometry": {"type": "LineString", "coordinates": w["coords"]},
                          "properties": {"corridor_street": name, "osm_way_id": wid,
                                         "highway": t.get("highway"), "kind": "route5_south_corridor"}})  # noqa: E501
    return rows, feats


def khomut_controls(pts):
    k = [p for p in pts if p["settlement_ru"] == "Бендеры"
         and p["service_status"] in ("standard", "low_density")
         and p["address_status"] == "verified_osm_address"
         and nearest_osm_place(p["lat"], p["lon"])[0] == "Хомутяновка"]
    k.sort(key=lambda p: haversine_km(p["lat"], p["lon"], CENTRAL[1], CENTRAL[0]))
    n = len(k)
    picks = []
    picks += k[:10]                      # near
    picks += k[n // 2 - 5:n // 2 + 5]    # middle
    picks += k[-10:]                     # far
    # explicitly include the HIGH-zone homes (the owner's concern): up to 8 per zone.
    # zone_id is an integer (1..4) in the address points.
    for z in (2, 3, 4):
        picks += [p for p in k if int(p["zone_id"]) == z][:8]
    seen, out = set(), []
    for p in picks:
        if p["uid"] not in seen:
            seen.add(p["uid"])
            out.append(p)
    return out, k


def main() -> int:
    (REPO / "reports/stage-09c").mkdir(parents=True, exist_ok=True)
    h = build_topo()
    pts = load_address_points()

    # 1. brewery crossing facts
    facts = brewery_crossing_facts(h)
    _csv("docs/data/stage-09c-khomutyanovka-crossing.csv", facts)
    primary = [f for f in facts if f["highway"] == "primary"]
    print(f"brewery car crossings (shared level_crossing node): {len(facts)}; primary: {len(primary)}; "  # noqa: E501
          f"osrm fwd&rev ok: {all(f['present_in_osrm_forward'] and f['present_in_osrm_reverse'] for f in facts)}")  # noqa: E501

    # 2. route №5 south corridor OSM match + geojson
    r5rows, r5feats = route5_osm_match(h)
    _csv("docs/data/stage-09c-route5-osm-match.csv", r5rows)
    (REPO / "docs/data/stage-09c-route5-corridor.geojson").write_text(
        json.dumps({"type": "FeatureCollection",
                    "source": {"provider": "EasyWay route №5 (owner ground truth); "
                               "easyway web bot-blocked (HTTP 403) — verified vs OSM",
                               "usage": "proof of car connectivity only; no stop loops enforced",
                               "owner_review_required": True},
                    "features": r5feats}, ensure_ascii=False),
        encoding="utf-8", newline="\n")

    # 3. Khomutyanovka control homes — A/B/C/D/E
    controls, allk = khomut_controls(pts)
    comp, mapf = [], []
    overstated = 0
    for p in controls:
        dest = (p["lon"], p["lat"])
        snap = nearest(p["lon"], p["lat"])
        fastest = route_detailed([CENTRAL, dest])
        shortest = min([fastest] + fastest["alternatives"], key=lambda r: r["distance_km"])
        forced = route_detailed([CENTRAL, BREWERY_PRIMARY_LC, dest])
        segs, flags, _ = validate_segments(fastest["nodes"], h.node_to_ways, h.ways)
        uses_brewery = route_uses_point(fastest["geometry"], BREWERY_PRIMARY_LC, 120)
        best_km = min(fastest["distance_km"], shortest["distance_km"], forced["distance_km"])
        if fastest["distance_km"] > best_km * 1.10:
            overstated += 1
        comp.append({
            "uid": p["uid"], "street": p["street_ru"], "house": p["housenumber"],
            "current_zone": p["zone_id"], "snap_distance_m": snap.get("snap_distance_m"),
            "A_fastest_km": fastest["distance_km"], "A_fastest_s": fastest["duration_s"],
            "B_shortest_km": shortest["distance_km"], "B_shortest_s": shortest["duration_s"],
            "C_forced_brewery_km": forced["distance_km"], "C_forced_brewery_s": forced["duration_s"],  # noqa: E501
            "D_n_alternatives": len(fastest["alternatives"]),
            "E_driver_cost_fastest": driver_cost(fastest["distance_km"], fastest["duration_s"]),
            "E_driver_cost_shortest": driver_cost(shortest["distance_km"], shortest["duration_s"]),
            "diff_forced_minus_fastest_km": round(forced["distance_km"] - fastest["distance_km"], 3),  # noqa: E501
            "diff_forced_minus_fastest_s": round(forced["duration_s"] - fastest["duration_s"], 1),
            "fastest_uses_brewery_crossing": uses_brewery,
            "fastest_uses_service_segment": "service" in ";".join(flags),
            "route_valid": "OWNER_REVIEW_ROUTE" if flags else "OK",
        })
        for kind, r, _c in [("fastest", fastest, 0), ("shortest", shortest, 1), ("forced_brewery", forced, 2)]:  # noqa: E501
            mapf.append({"type": "Feature",
                         "geometry": {"type": "LineString", "coordinates": r["geometry"]},
                         "properties": {"uid": p["uid"], "kind": kind,
                                        "distance_km": r["distance_km"], "duration_s": r["duration_s"]}})  # noqa: E501
        mapf.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": list(dest)},
                     "properties": {"uid": p["uid"], "kind": "home", "zone": p["zone_id"]}})
    mapf.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": list(BREWERY_PRIMARY_LC)},  # noqa: E501
                 "properties": {"kind": "brewery_primary_level_crossing"}})
    mapf.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": list(BREWERY)},
                 "properties": {"kind": "brewery_ul_druzhby_7"}})
    _csv("docs/data/stage-09c-khomutyanovka-comparison.csv", comp)
    (REPO / "docs/data/stage-09c-khomutyanovka-routes.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": mapf}, ensure_ascii=False),
        encoding="utf-8", newline="\n")

    # 4. Does the south corridor SHORTEN Borisovka? (north путепровод is shorter)
    bori = [p for p in pts if p["settlement_ru"] == "Бендеры"
            and p["service_status"] in ("standard", "low_density")
            and p["address_status"] == "verified_osm_address"
            and nearest_osm_place(p["lat"], p["lon"])[0] == "Борисовка"]
    bori.sort(key=lambda p: haversine_km(p["lat"], p["lon"], CENTRAL[1], CENTRAL[0]))
    south_rows = []
    south_helps = 0
    for p in bori[::max(1, len(bori) // 40)]:
        dest = (p["lon"], p["lat"])
        fastest = route_detailed([CENTRAL, dest])
        shortest = min([fastest] + fastest["alternatives"], key=lambda r: r["distance_km"])
        via_south = route_detailed([CENTRAL, BREWERY_PRIMARY_LC, dest])
        if via_south["distance_km"] < shortest["distance_km"] - 0.05:
            south_helps += 1
        south_rows.append({
            "uid": p["uid"], "street": p["street_ru"], "house": p["housenumber"],
            "current_zone": p["zone_id"], "fastest_km": fastest["distance_km"],
            "shortest_km": shortest["distance_km"], "via_south_brewery_km": via_south["distance_km"],  # noqa: E501
            "south_shorter_than_shortest": via_south["distance_km"] < shortest["distance_km"] - 0.05,  # noqa: E501
        })
    _csv("docs/data/stage-09c-borisovka-south-corridor.csv", south_rows)

    print("Khomutyanovka four-route (sample):")
    for r in comp[:6]:
        print(f"  {r['street']} {r['house']} z{r['current_zone']}: A {r['A_fastest_km']}km/{r['A_fastest_s']}s "  # noqa: E501
              f"B {r['B_shortest_km']}km C_brew {r['C_forced_brewery_km']}km "
              f"uses_brewery={r['fastest_uses_brewery_crossing']} valid={r['route_valid']}")
    print(f"Khomutyanovka homes with OVERSTATED current route (fastest >10% over best): {overstated}/{len(controls)}")  # noqa: E501
    print(f"Borisovka homes where the SOUTH brewery corridor is shorter than the (north) shortest: "
          f"{south_helps}/{len(south_rows)}")
    return 0


def _csv(rel, rows):
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
