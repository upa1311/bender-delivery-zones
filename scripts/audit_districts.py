#!/usr/bin/env python
"""Stage 08 — audit Bender districts and the (unmapped) Северный area.

Two things, both from the LOCAL OSM extract and the local OSRM server:

1. district-coverage-audit — every Bender place=suburb/quarter/neighbourhood
   node: is it inside the Tier A+B candidate service area, is it reachable from
   the centre by road, how far, and how many addressed residential buildings sit
   near it. Districts outside the candidate area are flagged "disconnected".

2. severny-audit — Северный is NOT an OSM place/boundary/bus_stop object; it is
   named only by four marshrutka route relations. Per the project rule we do not
   invent a coordinate: the routes' real geometry is published as route-QA, a
   single UNCONFIRMED candidate marker (the northern route extremity) is emitted
   for owner review, and no delivery polygon is fabricated.

Creates no tariffs, assigns no prices, and does not touch Direct.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import osmium
from shapely.geometry import LineString, Point, shape
from shapely.ops import unary_union

from bender_zones import jsonutil
from bender_zones.osrm import OsrmClient

BENDER_REL = 12463379
SUBURB_PLACES = {"suburb", "quarter", "neighbourhood"}
NEAR_ADDR_M = 300.0
M_PER_DEG_LAT = 111000.0


def _now():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _m_per_deg_lon(lat):
    import math
    return 111320.0 * math.cos(math.radians(lat))


def build(repo_root: Path, osrm_url: str) -> int:
    city = repo_root / "data/interim/city-extract-12463379.osm.pbf"
    if not city.is_file():
        print(f"error: Bender city extract not found: {city}", file=sys.stderr)
        return 2
    client = OsrmClient(osrm_url)
    osrm_up = client.is_up()

    cand = json.loads((repo_root / "docs/data/candidate-service-area.geojson")
                      .read_text(encoding="utf-8"))
    bender_service = unary_union([shape(f["geometry"]) for f in cand["features"]
                                  if f["properties"]["key"] in ("bender_core",
                                                                "bender_lipcani")])
    core = next(shape(f["geometry"]) for f in cand["features"]
                if f["properties"]["key"] == "bender_core")
    centre = core.representative_point()
    mlat = M_PER_DEG_LAT
    mlon = _m_per_deg_lon(centre.y)

    # --- collect suburbs, addressed residential buildings, Severny routes ---
    suburbs, addr_pts = [], []
    severny_routes = {}
    fp = osmium.FileProcessor(str(city)).with_locations()
    for obj in fp:
        tags = {k: v for k, v in obj.tags}
        kind = obj.type_str()
        if kind == "n":
            if tags.get("place") in SUBURB_PLACES and tags.get("name"):
                suburbs.append({"osm_id": obj.id, "name": tags.get("name"),
                                "name_ru": tags.get("name:ru"),
                                "place": tags.get("place"),
                                "lon": round(obj.lon, 6), "lat": round(obj.lat, 6),
                                "point": Point(obj.lon, obj.lat)})
            if tags.get("addr:housenumber") and tags.get("building"):
                addr_pts.append(Point(obj.lon, obj.lat))
        elif kind == "w":
            if tags.get("building") and tags.get("addr:housenumber"):
                cs = [(nd.lon, nd.lat) for nd in obj.nodes if nd.location.valid()]
                if len(cs) >= 3:
                    addr_pts.append(LineString(cs).centroid)
        elif kind == "r":
            name = tags.get("name") or ""
            if "Северный" in name and tags.get("type") == "route":
                severny_routes[obj.id] = {"name": name, "ref": tags.get("ref"),
                                          "member_count": len(list(obj.members))}

    from shapely.strtree import STRtree
    addr_tree = STRtree(addr_pts) if addr_pts else None

    def addresses_near(point):
        if addr_tree is None:
            return 0
        buf = point.buffer(NEAR_ADDR_M / mlat)  # rough; refined by exact check
        return sum(1 for i in addr_tree.query(buf)
                   if _dist_m(point, addr_pts[int(i)], mlat, mlon) <= NEAR_ADDR_M)

    # --- district coverage ---
    districts = []
    for s in sorted(suburbs, key=lambda x: x["name"]):
        covered = bool(bender_service.covers(s["point"]))
        nearest_m = 0.0 if covered else _dist_to_geom_m(s["point"], bender_service,
                                                        mlat, mlon)
        road_km = road_min = None
        if osrm_up:
            r = client.route((centre.x, centre.y), (s["lon"], s["lat"]))
            if r:
                road_km, road_min = round(r[0] / 1000.0, 3), round(r[1] / 60.0, 2)
        districts.append({
            "name": s["name"], "name_ru": s["name_ru"], "osm_id": s["osm_id"],
            "place": s["place"], "lon": s["lon"], "lat": s["lat"],
            "covered_by_candidate_area": covered,
            "distance_to_candidate_area_m": round(nearest_m),
            "road_distance_from_centre_km": road_km,
            "road_duration_from_centre_min": road_min,
            "addressed_buildings_within_300m": addresses_near(s["point"]),
            "status": "connected" if covered else "disconnected",
        })
    disconnected = [d for d in districts if d["status"] == "disconnected"]

    # --- Severny: real route geometry, unconfirmed candidate, no invented polygon ---
    severny = _audit_severny(city, severny_routes, mlat, mlon, centre, client, osrm_up)

    _write(repo_root, districts, disconnected, severny, osrm_up, len(addr_pts))
    print(f"districts: {len(districts)} | disconnected: {len(disconnected)} "
          f"| severny routes: {len(severny_routes)} | osrm: {osrm_up}")
    for d in disconnected:
        print(f"  disconnected: {d['name']} ({d['distance_to_candidate_area_m']} m "
              f"from candidate area)")
    return 0


def _audit_severny(city, routes, mlat, mlon, centre, client, osrm_up):
    """Build route-QA geometry and an UNCONFIRMED candidate marker for Северный."""
    want = set(routes)
    way_geoms = {}
    fp = osmium.FileProcessor(str(city)).with_locations()
    route_ways = {rid: [] for rid in want}
    for obj in fp:
        if obj.type_str() == "w":
            cs = [(nd.lon, nd.lat) for nd in obj.nodes if nd.location.valid()]
            if len(cs) >= 2:
                way_geoms[obj.id] = cs
        elif obj.type_str() == "r" and obj.id in want:
            for m in obj.members:
                if m.type == "w":
                    route_ways[obj.id].append(m.ref)

    route_lines = []
    all_coords = []
    for rid, ways in route_ways.items():
        segs = [way_geoms[w] for w in ways if w in way_geoms]
        for seg in segs:
            all_coords.extend(seg)
        if segs:
            merged = unary_union([LineString(s) for s in segs])
            route_lines.append((rid, routes[rid], merged))

    # Candidate anchor = northernmost point of the route geometry (owner review).
    anchor = None
    if all_coords:
        nlon, nlat = max(all_coords, key=lambda c: c[1])
        anchor = {"lon": round(nlon, 6), "lat": round(nlat, 6)}
        if osrm_up:
            r = client.route((centre.x, centre.y), (nlon, nlat))
            if r:
                anchor["road_distance_from_centre_km"] = round(r[0] / 1000.0, 3)
                anchor["road_duration_from_centre_min"] = round(r[1] / 60.0, 2)

    return {"routes": routes, "route_lines": route_lines, "anchor": anchor,
            "resolved": False,
            "evidence": ("Северный named only by marshrutka route relations "
                         f"{sorted(routes)}; no place=/boundary=/bus_stop object."),
            "message": "Severny landmark unresolved — owner confirmation required"}


def _dist_m(a, b, mlat, mlon):
    import math
    return math.hypot((a.x - b.x) * mlon, (a.y - b.y) * mlat)


def _dist_to_geom_m(point, geom, mlat, mlon):
    nearest = geom.boundary.interpolate(geom.boundary.project(point))
    return _dist_m(point, nearest, mlat, mlon)


def _write(repo_root, districts, disconnected, severny, osrm_up, addr_total):
    data = repo_root / "docs/data"
    reports = repo_root / "reports/stage-08"
    reports.mkdir(parents=True, exist_ok=True)
    generated = _now()

    # --- severny-service-area.geojson: UNCONFIRMED marker, never a polygon ---
    sev_feats = []
    if severny["anchor"]:
        a = severny["anchor"]
        sev_feats.append({"type": "Feature", "properties": {
            "name": "Северный", "status": "candidate_unconfirmed",
            "resolution": "owner_review_required",
            "geometry_kind": "marker_not_polygon",
            "derived_from": "northern extremity of marshrutka routes to Северный",
            "road_distance_from_centre_km": a.get("road_distance_from_centre_km"),
            "note": ("Не подтверждён как OSM-объект. Не является полигоном доставки. "
                     "Требуется решение владельца по границе/координате.")},
            "geometry": {"type": "Point", "coordinates": [a["lon"], a["lat"]]}})
    jsonutil.write(data / "severny-service-area.geojson",
                   {"type": "FeatureCollection",
                    "resolution_status": "unresolved", "features": sev_feats})

    # --- severny-route-qa.geojson: the real route geometry ---
    qa_feats = []
    for rid, meta, line in severny["route_lines"]:
        geoms = list(line.geoms) if line.geom_type == "MultiLineString" else [line]
        for g in geoms:
            qa_feats.append({"type": "Feature", "properties": {
                "route_relation": rid, "name": meta["name"], "ref": meta.get("ref"),
                "layer": "severny_route_qa"},
                "geometry": {"type": "LineString",
                             "coordinates": [[round(x, 6), round(y, 6)]
                                             for x, y in g.coords]}})
    jsonutil.write_compact(data / "severny-route-qa.geojson",
                           {"type": "FeatureCollection", "features": qa_feats})

    # --- district-coverage-audit ---
    cov_json = {
        "schema": "bender-district-coverage/8", "generated_at": generated,
        "osrm_used": osrm_up, "addressed_buildings_total": addr_total,
        "districts_total": len(districts),
        "connected": len(districts) - len(disconnected),
        "disconnected": len(disconnected),
        "districts": districts,
        "note": ("'disconnected' = the district's place node is outside the Tier "
                 "A+B candidate service area; it is not necessarily unserviceable, "
                 "but it is not covered by the current housing-density polygons."),
    }
    jsonutil.write(reports / "district-coverage-audit.json", cov_json)
    (reports / "district-coverage-audit.md").write_text(
        _cov_md(cov_json), encoding="utf-8", newline="\n")

    sev_json = {"schema": "bender-severny-audit/8", "generated_at": generated,
                "resolved": severny["resolved"], "message": severny["message"],
                "evidence": severny["evidence"], "anchor_candidate": severny["anchor"],
                "routes": severny["routes"],
                "zones_created": False, "prices_assigned": False,
                "direct_integration": False}
    jsonutil.write(reports / "severny-audit.json", sev_json)
    (reports / "severny-audit.md").write_text(_sev_md(sev_json), encoding="utf-8",
                                              newline="\n")


def _cov_md(d):
    lines = ["# Stage 08 — покрытие районов Бендер", "",
             f"- Сгенерировано (UTC): `{d['generated_at']}`",
             f"- Районов (place=suburb): **{d['districts_total']}** · "
             f"в зоне: **{d['connected']}** · вне зоны: **{d['disconnected']}**",
             f"- OSRM использован: **{d['osrm_used']}**", "",
             "> " + d["note"], "",
             "| район | place | в зоне | до зоны, м | дорога от центра, км | "
             "адресов ≤300 м | статус |",
             "|---|---|---|---:|---:|---:|---|"]
    for x in d["districts"]:
        road = x["road_distance_from_centre_km"]
        lines.append(f"| {x['name']} | {x['place']} | "
                     f"{'да' if x['covered_by_candidate_area'] else 'нет'} | "
                     f"{x['distance_to_candidate_area_m']} | "
                     f"{road if road is not None else '—'} | "
                     f"{x['addressed_buildings_within_300m']} | {x['status']} |")
    dis = [x for x in d["districts"] if x["status"] == "disconnected"]
    lines += ["", "## Отключённые районы", ""]
    lines += [f"- **{x['name']}** — вне candidate service area на "
              f"{x['distance_to_candidate_area_m']} м, адресов рядом "
              f"{x['addressed_buildings_within_300m']}" for x in dis] or ["- нет"]
    lines += [""]
    return "\n".join(lines)


def _sev_md(d):
    a = d["anchor_candidate"]
    lines = ["# Stage 08 — аудит «Северный»", "",
             f"- Сгенерировано (UTC): `{d['generated_at']}`",
             f"- Разрешён как объект OSM: **{d['resolved']}**",
             f"- Статус: **{d['message']}**",
             f"- zones_created: **{d['zones_created']}** · prices: "
             f"**{d['prices_assigned']}** · Direct: **{d['direct_integration']}**", "",
             "## Что найдено", "",
             f"- {d['evidence']}", "",
             "| relation | название | членов |", "|---|---|---:|"]
    for rid, meta in d["routes"].items():
        lines.append(f"| {rid} | {meta['name']} | {meta['member_count']} |")
    lines += ["", "## Кандидат-ориентир (не подтверждён)", ""]
    if a:
        lines += [f"- Северная оконечность маршрутов: `{a['lat']}, {a['lon']}`",
                  f"- Дорога от центра: "
                  f"{a.get('road_distance_from_centre_km', '—')} км",
                  "",
                  "Это **не** объект OSM и **не** полигон доставки. Координата "
                  "выведена из геометрии маршруток, а не из place/boundary. По "
                  "правилу проекта произвольная граница не создаётся — нужна "
                  "координата или граница от владельца."]
    else:
        lines += ["- Геометрию маршрутов собрать не удалось; ориентир не выведен."]
    lines += ["", "## Вывод", "",
              "«Северный» **не добавлен** как рабочая территория: подтверждённого "
              "OSM-объекта нет. На карту вынесен маркер `candidate_unconfirmed` для "
              "решения владельца; маршруты показаны отдельным QA-слоем.", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--osrm-url", default="http://127.0.0.1:5000")
    args = ap.parse_args(argv)
    return build(Path(args.repo_root), args.osrm_url)


if __name__ == "__main__":
    raise SystemExit(main())
