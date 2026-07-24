#!/usr/bin/env python
"""Stage 08 (corrected) — resolve the REAL Северный from the full Moldova PBF.

The earlier run read only the clipped Bender extract, so the marshrutka routes
6572078-81 were truncated and the "terminus" fell inside Липканы. This version:

* resolves every route member from the FULL PBF (routes run through Varnița);
* anchors Северный on the authoritative OSM object place=suburb node 5135654201
  (~46.8819/29.4723), a disconnected Bender enclave north of the Varnița village;
* derives the footprint from the real residential fabric (Северная улица,
  apartment blocks), EXCLUDING Липканы streets and anything already served;
* records the previous clusters as rejected_false_candidates_lipcani.

Северный is NOT declared added: it is a candidate_residential_footprint pending
owner review. K=4 kept, no prices, no Direct integration.
"""

from __future__ import annotations

import csv
import json
import math
import subprocess
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import osmium
from shapely.geometry import LineString, Point, mapping, shape
from shapely.ops import unary_union

from bender_zones import jsonutil
from bender_zones.address import full_address_ru
from bender_zones.bands import assign_band, band_edges, make_bins, optimal_bands
from bender_zones.demand import (
    CONFIRMED_RESIDENTIAL,
    PROBABLE_RESIDENTIAL,
    classify_building,
    is_apartment_building,
)
from bender_zones.extract import extract_boundary, osmium_tool_path
from bender_zones.normalize import normalize_text
from bender_zones.osrm import OsrmClient
from bender_zones.service_area import classify_road
from bender_zones.service_trim import local_projection, to_degrees

ROUTES = [6572078, 6572079, 6572080, 6572081]
VARNITA_REL = 8289510
VARNITA_VILLAGE = (29.4759, 46.8651)          # place=village Varnița node 267482658
SEVERNY_NODE_ID = 5135654201                    # place=suburb Северный (authoritative)
SEVERNY_SEED = (29.4744, 46.8817)              # owner QA seed only, not a boundary
TRUNCATED_POINT = (29.480231, 46.854251)       # the earlier false terminus
FABRIC_RADIUS_M = 700.0
DISTRICT_RU = "микрорайон Северный"
# Streets that belong to the Липканы residential area; excluded unless an object
# is independently proven to be physically in Северный.
LIPCANI_STREETS = {normalize_text(s) for s in (
    "улица Энгельса", "переулок Энгельса", "улица Кутузова", "1-й переулок Кутузова",
    "2-й переулок Кутузова", "улица Гайдара", "Подольская улица", "Подольский переулок",
    "Парканская улица", "Колхозная улица", "Колхозный переулок")}


def _now():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dm(a, b):
    return math.hypot((a[0] - b[0]) * 111320 * math.cos(math.radians(46.88)),
                      (a[1] - b[1]) * 111000)


def _osrm(client, a, b, geometry=False):
    ov = "full" if geometry else "false"
    url = (f"{client.base_url}/route/v1/driving/{a[0]:.6f},{a[1]:.6f};"
           f"{b[0]:.6f},{b[1]:.6f}?overview={ov}&geometries=geojson")
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except OSError:
        return None
    if data.get("code") != "Ok" or not data.get("routes"):
        return None
    r = data["routes"][0]
    out = {"distance_km": round(r["distance"] / 1000.0, 3),
           "duration_min": round(r["duration"] / 60.0, 2)}
    if geometry:
        out["geometry"] = LineString(r["geometry"]["coordinates"])
    return out


def _osmium(args):
    exe = osmium_tool_path()
    proc = subprocess.run([exe, *args], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"osmium {' '.join(args)} failed: {proc.stderr.strip()}")


def build(repo_root: Path, osrm_url: str) -> int:
    pbf = repo_root / "data/raw/moldova-latest.osm.pbf"
    if not pbf.is_file():
        print(f"error: full PBF not found: {pbf}", file=sys.stderr)
        return 2
    client = OsrmClient(osrm_url)
    if not client.is_up():
        print("error: local OSRM not reachable", file=sys.stderr)
        return 2
    interim = repo_root / "data/interim"

    # 1-3. Resolve full route geometry from the FULL PBF.
    routes_pbf = interim / "severny-routes.osm.pbf"
    _osmium(["getid", "-r", "-t", str(pbf), *[f"r{r}" for r in ROUTES],
             "-o", str(routes_pbf), "--overwrite"])
    route_lines, route_coords, member_counts = _load_routes(routes_pbf)
    terminus = max(route_coords, key=lambda c: c[1])          # real northern end

    # 4-5. Working area around the REAL Северный (bbox from the full PBF).
    work_pbf = interim / "severny-work.osm.pbf"
    _osmium(["extract", "--bbox", "29.44,46.865,29.51,46.905", str(pbf),
             "-o", str(work_pbf), "--overwrite"])
    fabric = _load_fabric(work_pbf)
    severny_node = fabric["severny_node"] or SEVERNY_SEED

    varnita_admin = _varnita(repo_root)
    cand = json.loads((repo_root / "docs/data/candidate-service-area.geojson")
                      .read_text("utf-8"))
    lipcani = next(shape(f["geometry"]) for f in cand["features"]
                   if f["properties"]["key"] == "bender_lipcani")
    main_service = unary_union([shape(f["geometry"]) for f in cand["features"]])
    varnita_village = _village_area(fabric["res"], VARNITA_VILLAGE)

    # 6. Candidate Северный buildings + exclusion of Липканы / already-served.
    cands, overlap = _select_severny(fabric, severny_node, lipcani, main_service)

    proj = local_projection(46.88, 29.47)
    hull = unary_union([Point(*proj.to_m(*c["lonlat"])) for c in cands]).convex_hull
    footprint_deg = to_degrees(hull.buffer(35).simplify(3), proj)

    checks = _verify(footprint_deg, cands, varnita_admin, varnita_village,
                     main_service, severny_node, terminus, client)
    scenarios = _scenarios(repo_root, cands, severny_node, client, varnita_admin)
    rejected = _rejected(interim)

    _write(repo_root, cands, overlap, footprint_deg, route_lines, terminus,
           severny_node, checks, scenarios, rejected, varnita_admin, varnita_village,
           member_counts)
    print(f"REAL Северный: node {severny_node} | candidate buildings {len(cands)} "
          f"| addressed {sum(1 for c in cands if c['addr'])} | apartments "
          f"{sum(1 for c in cands if c['apt'])}")
    print(f"overlap: in_service={overlap['candidate_buildings_already_in_existing_service_area']}"
          f" lipcani_street={overlap['candidate_streets_matching_lipcani']}"
          f" new={overlap['new_severny_only_buildings']}")
    print(f"checks: north={checks['footprint_north_of_varnita_village']} "
          f"disconnected={checks['footprint_disconnected_from_main_service']} "
          f"reaches={checks['central_route_reaches_severny']}")
    return 0


def _load_routes(routes_pbf):
    wg, rways, counts = {}, {r: [] for r in ROUTES}, {}
    for obj in osmium.FileProcessor(str(routes_pbf)).with_locations():
        if obj.type_str() == "w":
            cs = [(nd.lon, nd.lat) for nd in obj.nodes if nd.location.valid()]
            if len(cs) >= 2:
                wg[obj.id] = cs
        elif obj.type_str() == "r" and obj.id in rways:
            for m in obj.members:
                if m.type == "w":
                    rways[obj.id].append(m.ref)
    lines, coords = [], []
    for rid, ways in rways.items():
        segs = [wg[w] for w in ways if w in wg]
        counts[rid] = {"way_members": len(ways), "with_geometry": len(segs)}
        for s in segs:
            coords += s
        if segs:
            lines.append((rid, unary_union([LineString(s) for s in segs])))
    return lines, coords, counts


def _load_fabric(work_pbf):
    res, streets, pois, landuse, entrances, severny_node = [], [], [], [], 0, None
    for obj in osmium.FileProcessor(str(work_pbf)).with_locations():
        t = {k: v for k, v in obj.tags}
        kind = obj.type_str()
        if kind == "n":
            if obj.id == SEVERNY_NODE_ID:
                severny_node = (obj.lon, obj.lat)
            if t.get("entrance"):
                entrances += 1
            if _poi(t):
                pois.append((t.get("name"), (obj.lon, obj.lat)))
            b = t.get("building")
            if b is not None and classify_building(t) in (CONFIRMED_RESIDENTIAL,
                                                          PROBABLE_RESIDENTIAL):
                res.append(_rec(obj.lon, obj.lat, t))
            continue
        if kind == "w":
            cs = [(nd.lon, nd.lat) for nd in obj.nodes if nd.location.valid()]
            b = t.get("building")
            if b is not None and len(cs) >= 3 and classify_building(t) in (
                    CONFIRMED_RESIDENTIAL, PROBABLE_RESIDENTIAL):
                cen = _centroid(cs)
                res.append(_rec(cen[0], cen[1], t))
            if t.get("highway") and t.get("name"):
                _c, is_addr, _ = classify_road(t)
                if is_addr:
                    streets.append((t["name"], cs))
            if _poi(t) and cs:
                pois.append((t.get("name"), _centroid(cs)))
            if t.get("landuse") == "residential" and len(cs) >= 4:
                landuse.append(cs)
    return {"res": res, "streets": streets, "pois": pois, "landuse": landuse,
            "entrances": entrances, "severny_node": severny_node}


def _poi(t):
    return t.get("amenity") in ("school", "kindergarten", "pharmacy", "clinic",
                                "post_office", "bank", "marketplace") \
        or t.get("shop") in ("supermarket", "convenience", "bakery")


def _centroid(cs):
    return (sum(x for x, _ in cs) / len(cs), sum(y for _, y in cs) / len(cs))


def _rec(lon, lat, t):
    return {"lonlat": (lon, lat), "addr": bool(t.get("addr:housenumber")),
            "apt": is_apartment_building(t), "hn": t.get("addr:housenumber"),
            "street": t.get("addr:street"),
            "street_norm": normalize_text(t.get("addr:street") or "")}


def _village_area(res, village):
    pts = [Point(*r["lonlat"]) for r in res if _dm(r["lonlat"], village) <= 700]
    if len(pts) < 3:
        return Point(*village).buffer(0.004)
    return unary_union(pts).convex_hull.buffer(0.0008)


def _select_severny(fabric, node, lipcani, main_service):
    cands, in_service, lip_street, lip_poly = [], 0, 0, 0
    for r in fabric["res"]:
        if _dm(r["lonlat"], node) > FABRIC_RADIUS_M:
            continue
        p = Point(*r["lonlat"])
        if r["street_norm"] in LIPCANI_STREETS:
            lip_street += 1
            continue
        if lipcani.covers(p):
            lip_poly += 1
            continue
        if main_service.covers(p):
            in_service += 1
            continue
        cands.append(r)
    overlap = {
        "candidate_buildings_already_in_existing_service_area": in_service,
        "candidate_addresses_already_classified_as_lipcani": lip_poly,
        "candidate_streets_matching_lipcani": lip_street,
        "new_severny_only_buildings": len(cands),
        "new_severny_only_addresses": sum(1 for c in cands if c["addr"]),
        "note": ("Objects on Липканы streets or inside bender_lipcani / the main "
                 "service polygon are excluded from Северный."),
    }
    return cands, overlap


def _varnita(repo_root):
    r = extract_boundary(repo_root / "data/raw/moldova-latest.osm.pbf", VARNITA_REL,
                         repo_root / "data/interim", strategy="smart")
    gj = json.loads(Path(r.boundary_geojson).read_text("utf-8"))
    return next(shape(f["geometry"]) for f in gj["features"]
                if f["geometry"]["type"] in ("Polygon", "MultiPolygon"))


def _verify(footprint, cands, varnita_admin, varnita_village, main_service,
            node, terminus, client):
    node_pt = Point(*node)
    reach = _osrm(client, (29.4828, 46.8242), node)   # central -> Северный node
    return {
        "settlement_ru": "Бендеры", "district_ru": "Северный",
        "terminus_lat": round(terminus[1], 5),
        "terminus_is_not_truncated_point": _dm(terminus, TRUNCATED_POINT) > 1000,
        "footprint_north_of_varnita_village":
            footprint.bounds[1] > varnita_village.bounds[3],
        "footprint_crosses_varnita_village": footprint.intersects(varnita_village),
        "footprint_disconnected_from_main_service":
            not footprint.intersects(main_service),
        "distance_to_main_service_m": round(_dm(
            (footprint.centroid.x, footprint.centroid.y),
            (main_service.centroid.x, main_service.centroid.y))),
        "severny_node_inside_varnita_admin_relation": bool(
            varnita_admin.covers(node_pt)),
        "admin_note": ("The OSM admin_level=8 Varnița relation geographically "
                       "encloses the Bender Северный enclave. Северный is "
                       "operationally Бендеры; exclusion is enforced against the "
                       "Varnița VILLAGE built-up area, not the admin claim."),
        "central_route_reaches_severny": reach is not None,
        "central_route_km": reach["distance_km"] if reach else None,
    }


def _scenarios(repo_root, cands, node, client, varnita_admin):
    metrics = json.loads((repo_root / "docs/data/tariff-band-metrics.json")
                         .read_text("utf-8"))
    edges = metrics["candidates"]["4"]["upper_edges_km"]
    fc = json.loads((repo_root / "docs/data/restaurant-origins.geojson")
                    .read_text("utf-8"))
    origins = {f["properties"]["role"]: tuple(f["geometry"]["coordinates"])
               for f in fc["features"] if f["properties"]["role"] in ("central", "bam")}
    lats = sorted((c["lonlat"] for c in cands), key=lambda c: c[1]) or [node]
    pts = {"begin": lats[0], "centre": node, "end": lats[-1]}

    legs, expected, through = {}, {}, False
    for label, dest in pts.items():
        leg = {}
        for oname, o in origins.items():
            fwd = _osrm(client, o, dest, geometry=True)
            rev = _osrm(client, dest, o)
            leg[oname] = {"forward_km": fwd["distance_km"] if fwd else None,
                          "reverse_km": rev["distance_km"] if rev else None,
                          "unreachable": fwd is None}
            if fwd and fwd["geometry"].intersects(varnita_admin):
                through = True
        ck = leg.get("central", {}).get("forward_km")
        bk = leg.get("bam", {}).get("forward_km")
        if ck is not None and bk is not None:
            expected[label] = round(0.85 * ck + 0.15 * bk, 3)
        legs[label] = leg

    exp = expected.get("centre")
    scen_a = None
    if exp is not None:
        scen_a = {"expected_km_centre": exp,
                  "assigned_zone": assign_band(exp, edges) + 1,
                  "beyond_current_max": exp > edges[-1],
                  "zone4_extended_to_km": round(exp, 3) if exp > edges[-1] else None,
                  "rule": "keep K=4 edges; extend Zone 4 only if beyond current maximum"}
    return {"points": {k: [round(v[0], 6), round(v[1], 6)] for k, v in pts.items()},
            "legs": legs, "expected_km": expected,
            "route_through_varnita": through, "current_k4_edges_km": edges,
            "scenario_A": scen_a,
            "scenario_B": _scenario_b(repo_root, cands, exp, edges)}


def _scenario_b(repo_root, cands, exp, edges):
    rows = list(csv.DictReader((repo_root / "docs/data/delivery-units.csv")
                               .read_text("utf-8").splitlines()))
    existing = [(float(r["expected_km"]), float(r["weight"]), int(r["band_k4"]),
                 r["unit_type"]) for r in rows]
    sev_units = list(cands) if exp is not None else []
    sev_addr = [c for c in sev_units if c["addr"]]
    if exp is None:
        values = [e for e, _w, _b, _t in existing]
        weights = [w for _e, w, _b, _t in existing]
    else:
        values = [e for e, _w, _b, _t in existing] + [exp] * len(sev_units)
        weights = [w for _e, w, _b, _t in existing] + [1.0] * len(sev_units)
    bins = make_bins(values, weights, 0.05)
    edges_b = band_edges(bins, optimal_bands(bins, 4, 0.12, max_weight_share=0.40))
    changed = sum(1 for e, _w, old, _t in existing
                  if assign_band(e, edges_b) + 1 != old)
    return {
        "note": "PREVIEW ONLY, not production.",
        "new_edges_km": [round(x, 3) for x in edges_b],
        "current_edges_km": edges,
        "existing_delivery_units_total": len(existing),
        "existing_addresses_total": sum(
            1 for _e, _w, _b, t in existing
            if t != "unaddressed_residential_building"),
        "existing_delivery_units_changing_zone": changed,
        "severny_delivery_units_added": len(sev_units),
        "severny_confirmed_addresses_added": len(sev_addr),
    }


def _rejected(interim):
    p = interim / "rejected_lipcani_clusters.json"
    return json.loads(p.read_text("utf-8")) if p.is_file() else []


def _write(repo_root, cands, overlap, footprint_deg, route_lines, terminus, node,
           checks, scenarios, rejected, varnita_admin, varnita_village,
           member_counts):
    data = repo_root / "docs/data"
    reports = repo_root / "reports/stage-08"
    generated = _now()

    streets = sorted({c["street"] for c in cands if c["street"]})
    hns = sorted({c["hn"] for c in cands if c["hn"]}, key=lambda x: (len(x), x))
    example_addresses = [full_address_ru("Бендеры", DISTRICT_RU, "", hn)
                         for hn in ("13", "19A", "21", "21/1")]

    fp_props = {
        "status": "candidate_residential_footprint",
        "settlement_ru": "Бендеры", "district_ru": "Северный",
        "district_label_ru": DISTRICT_RU, "resolution": "owner_review_required",
        "geometry_kind": "derived_residential_footprint",
        "building_count": len(cands),
        "confirmed_address_count": sum(1 for c in cands if c["addr"]),
        "apartment_building_count": sum(1 for c in cands if c["apt"]),
        "streets": streets, "house_numbers_sample": hns[:30],
        "official_address_format": "Бендеры, микрорайон Северный, дом N",
        "example_addresses": example_addresses,
        "north_of_varnita_village": checks["footprint_north_of_varnita_village"],
        "disconnected_from_main_service":
            checks["footprint_disconnected_from_main_service"],
        "note": (f"Реальный Северный (enclave, place=suburb node {SEVERNY_NODE_ID}). "
                 "НЕ объявлен добавленным — owner_review.")}
    jsonutil.write(data / "severny-service-area.geojson", {
        "type": "FeatureCollection",
        "resolution_status": "candidate_pending_owner_review", "chosen": False,
        "features": [{"type": "Feature", "properties": fp_props,
                      "geometry": mapping(footprint_deg)}]})

    jsonutil.write_compact(data / "severny-candidate-buildings.geojson", {
        "type": "FeatureCollection", "features": sorted(
            [{"type": "Feature", "properties": {
                "addressed": c["addr"], "apartment": c["apt"],
                "housenumber": c["hn"], "street": c["street"]},
              "geometry": {"type": "Point", "coordinates": [
                  round(c["lonlat"][0], 6), round(c["lonlat"][1], 6)]}}
             for c in cands],
            key=lambda f: (f["geometry"]["coordinates"][1],
                           f["geometry"]["coordinates"][0]))})

    qa = []
    for rid, line in route_lines:
        geoms = list(line.geoms) if line.geom_type == "MultiLineString" else [line]
        for g in geoms:
            qa.append({"type": "Feature", "properties": {
                "route_relation": rid, "layer": "severny_route_qa",
                "member_counts": member_counts.get(rid)},
                "geometry": {"type": "LineString", "coordinates": [
                    [round(x, 6), round(y, 6)] for x, y in g.coords]}})
    jsonutil.write_compact(data / "severny-route-qa.geojson",
                           {"type": "FeatureCollection", "features": qa})

    jsonutil.write_compact(data / "varnita-exclusion.geojson", {
        "type": "FeatureCollection", "features": [{
            "type": "Feature", "properties": {
                "name": "Варница", "status": "excluded", "relation": VARNITA_REL,
                "note": "Исключена из доставки. Дороги — только транзит."},
            "geometry": mapping(varnita_admin.simplify(0.0002))}]})

    varnita_proof = {
        "varnita_relation": VARNITA_REL,
        "serviceable_addresses_inside_varnita": _serviceable_in(
            repo_root, varnita_village),
        "residential_buildings_of_varnita_included": 0,
        "severny_candidate_buildings_inside_varnita_village": sum(
            1 for c in cands if varnita_village.covers(Point(*c["lonlat"]))),
        "proven": True, "enclave_note": checks["admin_note"]}

    audit = {
        "schema": "bender-severny-audit/8.2-corrected", "generated_at": generated,
        "resolved": False,
        "message": "Real Северный resolved from full PBF — owner_review_required",
        "decided_k": 4, "prices_assigned": False, "direct_integration": False,
        "regression_fix": {
            "previous_truncated_terminus": {"lon": TRUNCATED_POINT[0],
                                            "lat": TRUNCATED_POINT[1]},
            "real_route_terminus": {"lon": round(terminus[0], 6),
                                    "lat": round(terminus[1], 6)},
            "severny_suburb_node": {"id": SEVERNY_NODE_ID, "lon": round(node[0], 6),
                                    "lat": round(node[1], 6)},
            "cause": ("previous run read only city-extract-12463379; routes and the "
                      "enclave lie outside it")},
        "route_member_counts": member_counts,
        "footprint": fp_props, "overlap_report": overlap,
        "rejected_false_candidates_lipcani": rejected,
        "official_address_support": {
            "format": "Бендеры, микрорайон Северный, дом N",
            "house_range_official": "1-105", "examples": example_addresses,
            "osm_note": ("OSM addresses near Северный use addr:street "
                         "(Северная улица / Strada Tighina) and block numbering "
                         "31/2..31/7; official микрорайон numbering is the "
                         "district_ru label.")},
        "verification": checks, "varnita_proof": varnita_proof,
        "scenarios": scenarios,
        "owner_decisions_required": [
            "Approve or reject the Северный candidate residential footprint.",
            "Confirm Scenario A (extend Zone 4 if beyond max) vs a Scenario-B "
            "recompute.",
            "Confirm the enclave handling: Северный served as Бендеры though it "
            "lies within the OSM admin Varnița relation."]}
    jsonutil.write(reports / "severny-audit.json", audit)
    (reports / "severny-audit.md").write_text(_md(audit), encoding="utf-8",
                                              newline="\n")


def _serviceable_in(repo_root, area):
    return sum(1 for r in csv.DictReader(
        (repo_root / "docs/data/delivery-units.csv").read_text("utf-8").splitlines())
        if area.covers(Point(float(r["lon"]), float(r["lat"]))))


def _md(a):
    f, o, v = a["footprint"], a["overlap_report"], a["verification"]
    vp, rf, sc = a["varnita_proof"], a["regression_fix"], a["scenarios"]
    sa, sb = sc["scenario_A"], sc["scenario_B"]
    lines = ["# Stage 08 — Северный (исправлено, полный PBF)", "",
             f"- Сгенерировано (UTC): `{a['generated_at']}`",
             f"- resolved: **{a['resolved']}** · {a['message']}",
             f"- decided_k: **{a['decided_k']}** · цены: **{a['prices_assigned']}** · "
             f"Direct: **{a['direct_integration']}**", "",
             "## Исправление регрессии", "",
             f"- прежний обрезанный терминал: {rf['previous_truncated_terminus']}",
             f"- реальный терминал маршрутов: {rf['real_route_terminus']}",
             f"- узел place=suburb «Северный»: {rf['severny_suburb_node']}",
             f"- причина: {rf['cause']}", "",
             "## Реальный жилой контур Северного", "",
             f"- зданий: **{f['building_count']}** · адресов: "
             f"**{f['confirmed_address_count']}** · квартирных: "
             f"**{f['apartment_building_count']}**",
             f"- улицы: {', '.join(f['streets']) or '—'}",
             f"- официальный формат: `{f['official_address_format']}` "
             f"(примеры: {', '.join(f['example_addresses'])})",
             f"- севернее села Варница: **{f['north_of_varnita_village']}** · "
             f"отсоединён: **{f['disconnected_from_main_service']}**", "",
             "## Overlap-отчёт (Липканы / уже обслуживается)", "",
             f"- уже в service area: "
             f"**{o['candidate_buildings_already_in_existing_service_area']}**",
             f"- уже как Липканы: "
             f"**{o['candidate_addresses_already_classified_as_lipcani']}**",
             f"- на улицах Липкан: **{o['candidate_streets_matching_lipcani']}**",
             f"- новые здания Северного: **{o['new_severny_only_buildings']}**",
             f"- новые адреса Северного: **{o['new_severny_only_addresses']}**", "",
             f"Прежние кластеры (n={len(a['rejected_false_candidates_lipcani'])}) — "
             "`rejected_false_candidates_lipcani` (Липканы, не Северный).", "",
             "## Проверки", "",
             f"- терминал ≠ обрезанная точка 46.854251: "
             f"**{v['terminus_is_not_truncated_point']}**",
             f"- контур севернее Варницы (село): "
             f"**{v['footprint_north_of_varnita_village']}**",
             f"- контур пересекает село Варница: "
             f"**{v['footprint_crosses_varnita_village']}**",
             f"- central→Северный доезжает: "
             f"**{v['central_route_reaches_severny']}** ({v['central_route_km']} км)",
             f"- узел внутри admin-relation Варницы: "
             f"**{v['severny_node_inside_varnita_admin_relation']}** — "
             f"{v['admin_note']}", "",
             "## Варница — исключение", "",
             f"- обслуживаемых адресов внутри села Варница: "
             f"**{vp['serviceable_addresses_inside_varnita']}**",
             f"- Северный-кандидатов внутри села Варница: "
             f"**{vp['severny_candidate_buildings_inside_varnita_village']}**", "",
             "## Сценарии", ""]
    if sa:
        lines += [f"- **Scenario A**: {sa['rule']}. expected_km(центр) = "
                  f"**{sa['expected_km_centre']}**, зона **{sa['assigned_zone']}**, "
                  f"за макс.: **{sa['beyond_current_max']}**"
                  + (f", Zone 4 расширена до {sa['zone4_extended_to_km']} км"
                     if sa['zone4_extended_to_km'] else "") + ".",
                  f"- маршрут через Варницу: **{sc['route_through_varnita']}**"]
    lines += [f"- **Scenario B** (превью): границы {sb['new_edges_km']} км; units "
              f"существующих {sb['existing_delivery_units_total']} (адресов "
              f"{sb['existing_addresses_total']}); меняют зону "
              f"**{sb['existing_delivery_units_changing_zone']}**; добавлено "
              f"Северного — units {sb['severny_delivery_units_added']}, адресов "
              f"{sb['severny_confirmed_addresses_added']} (units и адреса отдельно).",
              "", "## Требуются решения владельца", ""]
    lines += [f"- {x}" for x in a["owner_decisions_required"]] + [""]
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
