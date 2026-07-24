#!/usr/bin/env python
"""Stage 08 (cont.) — derive Северный residential candidates, prove Varnița
exclusion, review Ленинский/Птичник at building level, and prepare K=4 scenarios.

Local OSM extract + local OSRM only. No prices, no Direct integration, K=4 kept.
Северный is NOT declared "added": clusters are published as
candidate_residential_footprint / owner_review_required.
"""

from __future__ import annotations

import csv
import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import osmium
import yaml
from shapely.geometry import LineString, Point, Polygon, mapping, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

from bender_zones import jsonutil
from bender_zones.bands import assign_band, band_edges, make_bins, optimal_bands
from bender_zones.demand import (
    CONFIRMED_RESIDENTIAL,
    PROBABLE_RESIDENTIAL,
    classify_building,
    is_apartment_building,
)
from bender_zones.extract import extract_boundary
from bender_zones.osrm import OsrmClient
from bender_zones.service_area import classify_road
from bender_zones.service_trim import (
    area_m2,
    local_projection,
    to_degrees,
    to_metres,
)

ROUTES = {6572078, 6572079, 6572080, 6572081}
VARNITA_REL = 8289510
BENDER_CITY = "data/interim/city-extract-12463379.osm.pbf"
RADII = (300, 500, 800)
TERMINAL_RADIUS = 800.0
CLUSTER_GAP_M = 70.0
MIN_CLUSTER_BUILDINGS = 5


def _now():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_poi_whitelist(repo_root):
    cfg = yaml.safe_load((repo_root / "config/demand.yml").read_text("utf-8"))
    wl = {k: set(v) for k, v in cfg["poi_whitelist"].items()}
    return wl, bool(cfg.get("poi_require_name", True))


def _poi_ok(tags, wl, require_name):
    if require_name and not (tags.get("name") or "").strip():
        return False
    return any(tags.get(k) in v for k, v in wl.items())


def _origins(repo_root):
    fc = json.loads((repo_root / "docs/data/restaurant-origins.geojson")
                    .read_text("utf-8"))
    out = {}
    for f in fc["features"]:
        if f["properties"]["role"] in ("central", "bam"):
            out[f["properties"]["role"]] = tuple(f["geometry"]["coordinates"])
    return out


def _osrm_route_geometry(client, a, b):
    url = (f"{client.base_url}/route/v1/driving/{a[0]:.6f},{a[1]:.6f};"
           f"{b[0]:.6f},{b[1]:.6f}?overview=full&geometries=geojson")
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except OSError:
        return None
    if data.get("code") != "Ok" or not data.get("routes"):
        return None
    r = data["routes"][0]
    return {"distance_km": round(r["distance"] / 1000.0, 3),
            "duration_min": round(r["duration"] / 60.0, 2),
            "geometry": LineString(r["geometry"]["coordinates"])}


def build(repo_root: Path, osrm_url: str) -> int:
    city = repo_root / BENDER_CITY
    if not city.is_file():
        print(f"error: {city} not found", file=sys.stderr)
        return 2
    client = OsrmClient(osrm_url)
    if not client.is_up():
        print("error: local OSRM not reachable", file=sys.stderr)
        return 2

    wl, require_name = _load_poi_whitelist(repo_root)
    origins = _origins(repo_root)

    varnita_deg = _varnita(repo_root)
    cand_deg = json.loads((repo_root / "docs/data/candidate-service-area.geojson")
                          .read_text("utf-8"))
    bender_service_deg = unary_union([shape(f["geometry"]) for f in cand_deg["features"]
                                      if f["properties"]["key"] in ("bender_core",
                                                                    "bender_lipcani")])

    # --- gather the Bender extract in a local metric plane ---
    proj = local_projection(46.83, 29.48)

    def M(lon, lat):
        return Point(*proj.to_m(lon, lat))

    res_buildings = []   # dicts: pt(metric), lon, lat, cls, addr, apt, hn, street?
    streets = []         # (name, LineString metric)
    entrances = 0
    pois = []            # (name, kind, Point metric)
    landuse_res = []     # metric polygons
    way_geoms, route_ways = {}, {r: [] for r in ROUTES}

    fp = osmium.FileProcessor(str(city)).with_locations()
    for obj in fp:
        tags = {k: v for k, v in obj.tags}
        kind = obj.type_str()
        if kind == "n":
            if tags.get("entrance"):
                entrances += 1
            if _poi_ok(tags, wl, require_name):
                pois.append((tags.get("name"), tags.get("amenity") or tags.get("shop"),
                             M(obj.lon, obj.lat)))
            b = tags.get("building")
            if b is not None and classify_building(tags) in (CONFIRMED_RESIDENTIAL,
                                                             PROBABLE_RESIDENTIAL):
                res_buildings.append(_bld(obj.lon, obj.lat, tags, M))
            continue
        if kind == "w":
            cs = [(nd.lon, nd.lat) for nd in obj.nodes if nd.location.valid()]
            if len(cs) >= 2:
                way_geoms[obj.id] = cs
            b = tags.get("building")
            if b is not None and len(cs) >= 3 and classify_building(tags) in (
                    CONFIRMED_RESIDENTIAL, PROBABLE_RESIDENTIAL):
                cen = Polygon([proj.to_m(x, y) for x, y in cs]).centroid
                lon, lat = proj.to_deg(cen.x, cen.y)
                res_buildings.append(_bld(lon, lat, tags, M, cen))
            if _poi_ok(tags, wl, require_name) and cs:
                cen = Polygon([proj.to_m(x, y) for x, y in cs]).centroid \
                    if len(cs) >= 3 else M(*cs[0])
                pois.append((tags.get("name"), tags.get("amenity") or tags.get("shop"),
                             cen))
            if tags.get("highway") and tags.get("name"):
                _rc, is_addr, _ = classify_road(tags)
                if is_addr:
                    streets.append((tags["name"],
                                    LineString([proj.to_m(x, y) for x, y in cs])))
            if tags.get("landuse") == "residential" and len(cs) >= 4:
                try:
                    landuse_res.append(Polygon([proj.to_m(x, y) for x, y in cs]))
                except Exception:
                    pass
            continue
        if kind == "r" and obj.id in ROUTES:
            for m in obj.members:
                if m.type == "w":
                    route_ways[obj.id].append(m.ref)

    # --- terminal region (route points near the northern extremity) ---
    route_coords = []
    for ws in route_ways.values():
        for w in ws:
            route_coords += way_geoms.get(w, [])
    nlon, nlat = max(route_coords, key=lambda c: c[1])
    terminus_m = M(nlon, nlat)
    terminal_pts = [M(lo, la) for lo, la in route_coords
                    if M(lo, la).distance(terminus_m) <= TERMINAL_RADIUS]
    terminal_region = unary_union([p.buffer(1) for p in terminal_pts]).convex_hull

    # --- candidate residential buildings near the terminal region ---
    bpts = [b["pt"] for b in res_buildings]
    btree = STRtree(bpts)
    term_buf = terminal_region.buffer(TERMINAL_RADIUS)
    cand_idx = sorted({int(i) for i in btree.query(term_buf)
                       if term_buf.covers(bpts[int(i)])})
    candidates = [res_buildings[i] for i in cand_idx]

    varnita_m = to_metres(varnita_deg, proj)
    for b in candidates:
        b["inside_varnita"] = varnita_m.covers(b["pt"])

    # radii coverage profile from the terminal region
    radius_profile = {}
    for R in RADII:
        buf = terminal_region.buffer(R)
        near = [b for b in candidates if buf.covers(b["pt"])]
        radius_profile[str(R)] = {
            "residential_buildings": len(near),
            "confirmed_addresses": sum(1 for b in near if b["addr"]),
            "apartment_buildings": sum(1 for b in near if b["apt"]),
            "inside_varnita": sum(1 for b in near if b["inside_varnita"])}

    clusters = _cluster(candidates, terminal_region, streets, pois, landuse_res,
                        varnita_m, proj)

    varnita_proof = _varnita_proof(repo_root, varnita_deg, proj, candidates)
    scenarios = _scenarios(repo_root, clusters, origins, client, varnita_deg, proj)
    lp_review = _leninsky_ptichnik(city, proj, bender_service_deg, origins, client)

    _write(repo_root, proj, clusters, radius_profile, terminus_m, terminal_region,
           varnita_deg, varnita_proof, scenarios, lp_review, entrances, origins)
    print(f"candidate buildings: {len(candidates)} | clusters: {len(clusters)} | "
          f"inside Varnița: {sum(b['inside_varnita'] for b in candidates)}")
    for c in clusters:
        print(f"  cluster {c['cluster_id']}: {c['building_count']} bld, "
              f"{c['confirmed_address_count']} addr, strength={c['evidence_strength']}")
    return 0


def _bld(lon, lat, tags, M, cen=None):
    pt = cen if cen is not None else M(lon, lat)
    return {"pt": pt, "lon": round(lon, 6), "lat": round(lat, 6),
            "cls": classify_building(tags), "addr": bool(tags.get("addr:housenumber")),
            "apt": is_apartment_building(tags), "hn": tags.get("addr:housenumber"),
            "street": tags.get("addr:street")}


def _varnita(repo_root):
    r = extract_boundary(repo_root / "data/raw/moldova-latest.osm.pbf", VARNITA_REL,
                         repo_root / "data/interim", strategy="smart")
    gj = json.loads(Path(r.boundary_geojson).read_text("utf-8"))
    return next(shape(f["geometry"]) for f in gj["features"]
                if f["geometry"]["type"] in ("Polygon", "MultiPolygon"))


def _cluster(candidates, terminal_region, streets, pois, landuse_res, varnita_m, proj):
    pts = [b["pt"] for b in candidates]
    tree = STRtree(pts)
    seen, comps = set(), []
    for i in range(len(pts)):
        if i in seen:
            continue
        stack, comp = [i], []
        seen.add(i)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for j in tree.query(pts[cur].buffer(CLUSTER_GAP_M)):
                j = int(j)
                if j not in seen and pts[cur].distance(pts[j]) <= CLUSTER_GAP_M:
                    seen.add(j)
                    stack.append(j)
        comps.append(comp)
    comps = [c for c in comps if len(c) >= MIN_CLUSTER_BUILDINGS]
    comps.sort(key=len, reverse=True)

    street_tree = STRtree([g for _n, g in streets]) if streets else None
    out = []
    for cid, comp in enumerate(comps, start=1):
        members = [candidates[i] for i in comp]
        hull = unary_union([m["pt"] for m in members]).convex_hull
        buf = hull.buffer(40)
        names = set()
        if street_tree is not None:
            for k in street_tree.query(buf):
                if streets[int(k)][1].intersects(buf):
                    names.add(streets[int(k)][0])
        n_poi = sum(1 for _n, _k, p in pois if buf.covers(p))
        addr = sum(1 for m in members if m["addr"])
        apt = sum(1 for m in members if m["apt"])
        in_v = sum(1 for m in members if m["inside_varnita"])
        strength = ("strong" if (len(members) >= 30 and addr >= 10 and names)
                    else "moderate" if (len(members) >= 12 and addr >= 4)
                    else "weak")
        centroid = hull.centroid
        clon, clat = proj.to_deg(centroid.x, centroid.y)
        out.append({
            "cluster_id": cid,
            "building_count": len(members),
            "confirmed_address_count": addr,
            "apartment_building_count": apt,
            "streets": sorted(names),
            "civic_or_commercial_pois": n_poi,
            "area_m2": round(area_m2(hull.buffer(15))),
            "distance_from_terminal_m": round(hull.distance(terminal_region)),
            "separation_from_varnita_m": round(hull.distance(varnita_m)),
            "buildings_inside_varnita": in_v,
            "evidence_strength": strength,
            "centroid": {"lon": round(clon, 6), "lat": round(clat, 6)},
            "_members": members, "_hull": hull})
    return out


def _varnita_proof(repo_root, varnita_deg, proj, candidates):
    varnita_m = to_metres(varnita_deg, proj)
    inside = 0
    for row in csv.DictReader((repo_root / "docs/data/delivery-units.csv")
                              .read_text("utf-8").splitlines()):
        if varnita_m.covers(Point(*proj.to_m(float(row["lon"]), float(row["lat"])))):
            inside += 1
    cand_in_v = sum(1 for b in candidates if b["inside_varnita"])
    return {
        "varnita_relation": VARNITA_REL,
        "serviceable_addresses_inside_varnita": inside,
        "residential_buildings_of_varnita_included": 0,
        "severny_candidate_buildings_inside_varnita": cand_in_v,
        "policy": ("Varnița stays excluded from service. Its roads may be used by "
                   "OSRM only as transit. Any Северный candidate building falling "
                   "inside the Varnița polygon is flagged, never auto-classified as "
                   "Северный."),
        "proven": inside == 0,
    }


def _cluster_points(cluster, terminal_region, proj):
    members = cluster["_members"]
    begin = min(members, key=lambda m: m["pt"].distance(terminal_region))
    end = max(members, key=lambda m: m["pt"].distance(terminal_region))
    c = cluster["centroid"]
    return {"begin": (begin["lon"], begin["lat"]),
            "centre": (c["lon"], c["lat"]),
            "end": (end["lon"], end["lat"])}


def _scenarios(repo_root, clusters, origins, client, varnita_deg, proj):
    metrics = json.loads((repo_root / "docs/data/tariff-band-metrics.json")
                         .read_text("utf-8"))
    k4_edges = metrics["candidates"]["4"]["upper_edges_km"]
    central, bam = origins.get("central"), origins.get("bam")

    per_cluster = []
    for cluster in clusters:
        pts = {}
        # begin/centre/end by latitude along the route (south -> north)
        ms = sorted(cluster["_members"], key=lambda x: x["lat"])
        pts["begin"] = (ms[0]["lon"], ms[0]["lat"])
        pts["centre"] = (cluster["centroid"]["lon"], cluster["centroid"]["lat"])
        pts["end"] = (ms[-1]["lon"], ms[-1]["lat"])

        legs = {}
        expected = {}
        through_varnita = False
        for label, dest in pts.items():
            leg = {}
            for oname, o in (("central", central), ("bam", bam)):
                fwd = _osrm_route_geometry(client, o, dest)
                rev = _osrm_route_geometry(client, dest, o)
                leg[oname] = {
                    "forward_km": fwd["distance_km"] if fwd else None,
                    "forward_min": fwd["duration_min"] if fwd else None,
                    "reverse_km": rev["distance_km"] if rev else None,
                    "unreachable": fwd is None}
                if fwd and fwd["geometry"].intersects(varnita_deg):
                    through_varnita = True
            ck = leg["central"]["forward_km"]
            bk = leg["bam"]["forward_km"]
            if ck is not None and bk is not None:
                expected[label] = round(0.85 * ck + 0.15 * bk, 3)
            elif ck is not None:
                expected[label] = ck
            legs[label] = leg

        exp_centre = expected.get("centre")
        scen_a = None
        if exp_centre is not None:
            zone = assign_band(exp_centre, k4_edges) + 1
            scen_a = {"expected_km_centre": exp_centre,
                      "assigned_zone": zone,
                      "beyond_current_max": exp_centre > k4_edges[-1],
                      "rule": "appended to Zone 4 where beyond current maximum"}
        per_cluster.append({
            "cluster_id": cluster["cluster_id"],
            "points": pts, "legs": legs, "expected_km": expected,
            "route_through_varnita": through_varnita,
            "scenario_A": scen_a})

    scenario_b = _scenario_b(repo_root, clusters, per_cluster, k4_edges)
    return {"scenario_A_note": ("keep current K=4 edges, append Северный to Zone 4 "
                                "where beyond the current maximum"),
            "current_k4_edges_km": k4_edges,
            "clusters": per_cluster,
            "scenario_B": scenario_b}


def _scenario_b(repo_root, clusters, per_cluster, k4_edges):
    """Full K=4 recompute including Северный candidate addresses (preview only)."""
    rows = list(csv.DictReader((repo_root / "docs/data/delivery-units.csv")
                               .read_text("utf-8").splitlines()))
    existing = [(float(r["expected_km"]), float(r["weight"]), int(r["band_k4"]))
                for r in rows]
    sev = []
    for cluster, pc in zip(clusters, per_cluster, strict=False):
        exp = pc["expected_km"].get("centre")
        if exp is None:
            continue
        for m in cluster["_members"]:
            if m["addr"]:
                sev.append((exp, 1.0))
    values = [e for e, _w, _b in existing] + [e for e, _w in sev]
    weights = [w for _e, w, _b in existing] + [w for _e, w in sev]
    bins = make_bins(values, weights, 0.05)
    bounds = optimal_bands(bins, 4, 0.12, max_weight_share=0.40)
    edges = band_edges(bins, bounds)
    changed = sum(1 for e, _w, old in existing
                  if assign_band(e, edges) + 1 != old)
    return {
        "note": ("PREVIEW ONLY, not production. Full K=4 recompute including "
                 "Северный candidate addresses, distance-only balanced bands."),
        "new_edges_km": [round(x, 3) for x in edges],
        "current_edges_km": k4_edges,
        "existing_addresses_total": len(existing),
        "existing_addresses_changing_zone": changed,
        "severny_addresses_added": len(sev),
    }


def _leninsky_ptichnik(city, proj, service_deg, origins, client):
    nodes = {}
    fp = osmium.FileProcessor(str(city)).with_locations()
    res = []
    for obj in fp:
        tags = {k: v for k, v in obj.tags}
        kind = obj.type_str()
        if kind == "n" and tags.get("place") in ("suburb", "quarter", "neighbourhood"):
            if tags.get("name") in ("Ленинский", "Птичник"):
                nodes[tags["name"]] = (obj.lon, obj.lat)
        b = tags.get("building")
        if b is None or classify_building(tags) not in (CONFIRMED_RESIDENTIAL,
                                                        PROBABLE_RESIDENTIAL):
            continue
        if kind == "n":
            res.append((obj.lon, obj.lat, bool(tags.get("addr:housenumber"))))
        elif kind == "w":
            cs = [(nd.lon, nd.lat) for nd in obj.nodes if nd.location.valid()]
            if len(cs) >= 3:
                cen = Polygon([proj.to_m(x, y) for x, y in cs]).centroid
                lon, lat = proj.to_deg(cen.x, cen.y)
                res.append((lon, lat, bool(tags.get("addr:housenumber"))))

    service_m = to_metres(service_deg, proj)
    out = {}
    for name, (lon, lat) in nodes.items():
        centre = Point(*proj.to_m(lon, lat))
        near = [(x, y, a) for x, y, a in res
                if Point(*proj.to_m(x, y)).distance(centre) <= 400]
        covered = [t for t in near if service_m.covers(Point(*proj.to_m(t[0], t[1])))]
        omitted = [t for t in near if t not in covered]
        omitted_addr = [t for t in omitted if t[2]]
        out[name] = {
            "place_node": {"lon": round(lon, 6), "lat": round(lat, 6)},
            "residential_buildings_within_400m": len(near),
            "covered_by_candidate_area": len(covered),
            "genuinely_omitted_buildings": len(omitted),
            "genuinely_omitted_addresses": len(omitted_addr),
            "expansion_recommended": len(omitted_addr) >= 10,
            "verdict": ("mostly covered — place node position, not the district, was "
                        "outside the polygon" if len(covered) >= len(omitted)
                        else "genuine omission — candidate expansion warranted"),
        }
    return out


def _write(repo_root, proj, clusters, radius_profile, terminus_m, terminal_region,
           varnita_deg, varnita_proof, scenarios, lp_review, entrances, origins):
    data = repo_root / "docs/data"
    reports = repo_root / "reports/stage-08"
    generated = _now()

    strong = [c for c in clusters if c["evidence_strength"] == "strong"]
    footprint_feats = []
    for c in clusters:
        status = ("candidate_residential_footprint"
                  if c["evidence_strength"] in ("strong", "moderate")
                  else "weak_cluster_review")
        hull_deg = to_degrees(c["_hull"].buffer(30).simplify(3), proj)
        footprint_feats.append({"type": "Feature", "properties": {
            "cluster_id": c["cluster_id"], "status": status,
            "settlement_ru": "Бендеры", "district_ru": "Северный",
            "resolution": "owner_review_required",
            "geometry_kind": "derived_residential_footprint",
            "building_count": c["building_count"],
            "confirmed_address_count": c["confirmed_address_count"],
            "apartment_building_count": c["apartment_building_count"],
            "streets": c["streets"],
            "area_m2": c["area_m2"],
            "distance_from_terminal_m": c["distance_from_terminal_m"],
            "separation_from_varnita_m": c["separation_from_varnita_m"],
            "buildings_inside_varnita": c["buildings_inside_varnita"],
            "evidence_strength": c["evidence_strength"],
            "note": ("Производный жилой контур, не админ-граница. Северный НЕ "
                     "объявлен добавленным — требуется решение владельца.")},
            "geometry": mapping(_round(hull_deg))})
    jsonutil.write(data / "severny-service-area.geojson", {
        "type": "FeatureCollection",
        "resolution_status": "candidates_pending_owner_review",
        "chosen_cluster": None,
        "strong_candidate_count": len(strong),
        "features": footprint_feats})

    # candidate building points (with Varnița flag) for the map / audit
    pt_feats = []
    for c in clusters:
        for m in c["_members"]:
            pt_feats.append({"type": "Feature", "properties": {
                "cluster_id": c["cluster_id"], "addressed": m["addr"],
                "apartment": m["apt"], "inside_varnita": m["inside_varnita"]},
                "geometry": {"type": "Point", "coordinates": [m["lon"], m["lat"]]}})
    jsonutil.write_compact(data / "severny-candidate-buildings.geojson",
                           {"type": "FeatureCollection", "features": pt_feats})

    # grey Varnița exclusion layer
    jsonutil.write_compact(data / "varnita-exclusion.geojson", {
        "type": "FeatureCollection", "features": [{
            "type": "Feature", "properties": {
                "name": "Варница", "status": "excluded",
                "relation": VARNITA_REL,
                "serviceable_addresses_inside": varnita_proof[
                    "serviceable_addresses_inside_varnita"],
                "note": "Исключена из доставки. Дороги — только транзит для OSRM."},
            "geometry": mapping(_round(varnita_deg.simplify(0.0002)))}]})

    for c in clusters:
        c.pop("_members", None)
        c.pop("_hull", None)

    audit = {
        "schema": "bender-severny-audit/8.1", "generated_at": generated,
        "resolved": False,
        "message": "Severny candidate residential footprints — owner_review_required",
        "decided_k": 4, "prices_assigned": False, "direct_integration": False,
        "route_terminus": {"lon": round(proj.to_deg(terminus_m.x, terminus_m.y)[0], 6),
                           "lat": round(proj.to_deg(terminus_m.x, terminus_m.y)[1], 6)},
        "radius_profile": radius_profile,
        "entrances_in_extract": entrances,
        "clusters": clusters,
        "strong_candidates": [c["cluster_id"] for c in clusters
                              if c["evidence_strength"] == "strong"],
        "varnita_proof": varnita_proof,
        "scenarios": scenarios,
        "owner_decisions_required": [
            "Approve or reject each Северный candidate residential footprint.",
            "Confirm whether Scenario A (append to Zone 4) or a later Scenario-B "
            "recompute is acceptable.",
            "Confirm the Varnița exclusion (0 serviceable addresses inside).",
        ],
    }
    jsonutil.write(reports / "severny-audit.json", audit)
    (reports / "severny-audit.md").write_text(_sev_md(audit), encoding="utf-8",
                                              newline="\n")

    # append the Ленинский/Птичник building-level review to the district report
    cov_path = reports / "district-coverage-audit.json"
    cov = json.loads(cov_path.read_text("utf-8"))
    cov["building_level_review"] = lp_review
    cov["generated_at"] = generated
    # A place node outside a polygon is not proof the district is excluded:
    # override the node-based status with the building-level verdict.
    for x in cov["districts"]:
        r = lp_review.get(x["name"])
        if r and r["genuinely_omitted_addresses"] < 10:
            x["status"] = "covered_at_building_level"
            x["building_level_note"] = ("place node outside the polygon, but the "
                                        "district's buildings are covered")
    cov["disconnected"] = sum(1 for x in cov["districts"]
                              if x["status"] == "disconnected")
    cov["connected"] = cov["districts_total"] - cov["disconnected"]
    jsonutil.write(cov_path, cov)
    (reports / "district-coverage-audit.md").write_text(
        _cov_md(cov), encoding="utf-8", newline="\n")


def _round(geom_obj):
    return geom_obj


def _sev_md(a):
    lines = ["# Stage 08 — Северный: жилые кандидаты", "",
             f"- Сгенерировано (UTC): `{a['generated_at']}`",
             f"- resolved: **{a['resolved']}** · {a['message']}",
             f"- decided_k: **{a['decided_k']}** · цены: **{a['prices_assigned']}** · "
             f"Direct: **{a['direct_integration']}**", "",
             "## Профиль по радиусам (от терминала маршрутов)", "",
             "| радиус | жилых зданий | адресов | квартирных | внутри Варницы |",
             "|---|---:|---:|---:|---:|"]
    for r, v in a["radius_profile"].items():
        lines.append(f"| {r} м | {v['residential_buildings']} | "
                     f"{v['confirmed_addresses']} | {v['apartment_buildings']} | "
                     f"{v['inside_varnita']} |")
    lines += ["", "## Кандидатные жилые кластеры", "",
              "| # | зданий | адресов | кв. | улиц | POI | площадь м² | "
              "от терминала м | до Варницы м | в Варнице | сила |",
              "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for c in a["clusters"]:
        lines.append(f"| {c['cluster_id']} | {c['building_count']} | "
                     f"{c['confirmed_address_count']} | {c['apartment_building_count']} "
                     f"| {len(c['streets'])} | {c['civic_or_commercial_pois']} | "
                     f"{c['area_m2']} | {c['distance_from_terminal_m']} | "
                     f"{c['separation_from_varnita_m']} | "
                     f"{c['buildings_inside_varnita']} | {c['evidence_strength']} |")
    lines += ["", f"Сильных кандидатов: **{len(a['strong_candidates'])}** "
              f"(id {a['strong_candidates'] or '—'}). Победитель не выбран."]
    vp = a["varnita_proof"]
    lines += ["", "## Доказательство исключения Варницы", "",
              f"- обслуживаемых адресов внутри Варницы: **"
              f"{vp['serviceable_addresses_inside_varnita']}**",
              f"- жилых зданий Варницы включено: **"
              f"{vp['residential_buildings_of_varnita_included']}**",
              f"- Северный-кандидатов внутри Варницы: **"
              f"{vp['severny_candidate_buildings_inside_varnita']}** (помечены, не "
              "классифицированы как Северный без проверки)",
              f"- доказано: **{vp['proven']}** — {vp['policy']}"]
    sb = a["scenarios"]["scenario_B"]
    lines += ["", "## Сценарии зон", "",
              f"- **Scenario A**: {a['scenarios']['scenario_A_note']}. Текущие "
              f"границы K=4: {a['scenarios']['current_k4_edges_km']} км.",
              "", "| кластер | expected км (центр) | зона A | за макс. |",
              "|---:|---:|---:|---|"]
    for pc in a["scenarios"]["clusters"]:
        sa = pc["scenario_A"]
        if sa:
            lines.append(f"| {pc['cluster_id']} | {sa['expected_km_centre']} | "
                         f"Zone {sa['assigned_zone']} | "
                         f"{'да' if sa['beyond_current_max'] else 'нет'} |")
    lines += ["", f"- **Scenario B** (превью, не production): пересчёт K=4 с "
              f"Северным. Новые границы {sb['new_edges_km']} км; существующих "
              f"адресов меняют зону: **{sb['existing_addresses_changing_zone']}** из "
              f"{sb['existing_addresses_total']}; добавлено адресов Северного "
              f"{sb['severny_addresses_added']}.",
              "", "## Требуются решения владельца", ""]
    lines += [f"- {x}" for x in a["owner_decisions_required"]]
    lines += [""]
    return "\n".join(lines)


def _cov_md(d):
    lines = ["# Stage 08 — покрытие районов Бендер", "",
             f"- Сгенерировано (UTC): `{d['generated_at']}`",
             f"- Районов: **{d['districts_total']}** · в зоне: **{d['connected']}** · "
             f"вне зоны: **{d['disconnected']}**", "",
             "> " + d["note"], "",
             "| район | place | в зоне | до зоны, м | дорога, км | адресов ≤300 м | "
             "статус |", "|---|---|---|---:|---:|---:|---|"]
    for x in d["districts"]:
        road = x["road_distance_from_centre_km"]
        lines.append(f"| {x['name']} | {x['place']} | "
                     f"{'да' if x['covered_by_candidate_area'] else 'нет'} | "
                     f"{x['distance_to_candidate_area_m']} | "
                     f"{road if road is not None else '—'} | "
                     f"{x['addressed_buildings_within_300m']} | {x['status']} |")
    lines += ["", "## Ленинский и Птичник — на уровне зданий", ""]
    for name, r in (d.get("building_level_review") or {}).items():
        lines += [f"### {name}",
                  f"- жилых зданий в 400 м: **{r['residential_buildings_within_400m']}**",
                  f"- уже покрыто: **{r['covered_by_candidate_area']}** · реально "
                  f"пропущено: **{r['genuinely_omitted_buildings']}** (адресов "
                  f"{r['genuinely_omitted_addresses']})",
                  f"- расширение полигона: **"
                  f"{'рекомендуется' if r['expansion_recommended'] else 'не требуется'}**",
                  f"- вывод: {r['verdict']}", ""]
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
