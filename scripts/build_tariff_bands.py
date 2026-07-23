#!/usr/bin/env python
"""Stage 06 — ordered OSRM tariff distance bands (K=4 / K=5).

Replaces the rejected spatial-cluster zoning. Zones are ORDERED COST BANDS over
the origin-weighted road kilometres measured by a locally built OSRM MLD car
profile: Zone 1 holds the cheapest routes, Zone N the farthest standard range.

No network Voronoi, no spatial K-means, no customer-centred seeds, no Lloyd.
No money is assigned; taxi calibration stays null. No Direct integration.

Requires a running local OSRM server (see reports/stage-06 for the build steps).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import osmium
import yaml
from shapely import set_precision
from shapely.geometry import LineString, Point, Polygon, mapping, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

from bender_zones import jsonutil
from bender_zones.bands import (
    assign_band,
    band_edges,
    dispersion,
    is_monotonic,
    make_bins,
    optimal_bands,
)
from bender_zones.config import load_audit, load_sources
from bender_zones.demand import (
    CONFIRMED_RESIDENTIAL,
    PROBABLE_RESIDENTIAL,
    classify_building,
    is_serviceable,
    tier_weight,
)
from bender_zones.demand_units import (
    UNIT_ADDRESS_NODE,
    UNIT_ADDRESSED_BUILDING,
    UNIT_UNADDRESSED_BUILDING,
    DemandUnit,
    deduplicate_address_nodes,
    summarise,
    unit_weight,
)
from bender_zones.extract import extract_boundary
from bender_zones.osrm import OsrmClient, OsrmError, expected_cost, worst_cost
from bender_zones.service_trim import (
    area_m2,
    local_projection,
    to_degrees,
    to_metres,
)

FOOD_AMENITIES = {"restaurant", "fast_food", "cafe", "food_court", "bar", "pub",
                  "ice_cream"}


def _now():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _round(o, nd=5):
    if isinstance(o, float):
        return round(o, nd)
    if isinstance(o, (list, tuple)):
        return [_round(x, nd) for x in o]
    if isinstance(o, dict):
        return {k: _round(v, nd) for k, v in o.items()}
    return o


def _feature(geom, props):
    return {"type": "Feature", "properties": props, "geometry": _round(mapping(geom))}


def _load_units_and_streets(city_pbf, proj, tier_by_id, street_by_id):
    """Extract demand units (with OSM ids) plus serviceable/Tier-C streets."""
    buildings, addr_nodes, b_polys = [], [], []
    serviceable, tier_c = [], []
    raw_buildings = raw_addresses = 0

    for obj in osmium.FileProcessor(str(city_pbf)).with_locations():
        tags = {k: v for k, v in obj.tags}
        kind = obj.type_str()

        if kind == "w" and tags.get("highway") and tags.get("name"):
            tier = tier_by_id.get(obj.id)
            if tier:
                cs = [proj.to_m(nd.lon, nd.lat) for nd in obj.nodes if nd.location.valid()]
                if len(cs) >= 2:
                    rec = (LineString(cs), street_by_id[obj.id], tier)
                    (serviceable if is_serviceable(tier) else tier_c).append(rec)
            continue

        has_building = tags.get("building") is not None
        has_addr = tags.get("addr:housenumber") is not None
        if not has_building and not has_addr:
            continue

        if kind == "n":
            pt = Point(*proj.to_m(obj.lon, obj.lat))
            lon, lat = obj.lon, obj.lat
        elif kind == "w":
            cs = [proj.to_m(nd.lon, nd.lat) for nd in obj.nodes if nd.location.valid()]
            if len(cs) < 4:
                continue
            try:
                poly = Polygon(cs)
                pt = poly.centroid
            except Exception:
                continue
            lon, lat = proj.to_deg(pt.x, pt.y)
        else:
            continue

        if has_building:
            raw_buildings += 1
            cls = classify_building(tags)
            if cls not in (CONFIRMED_RESIDENTIAL, PROBABLE_RESIDENTIAL):
                continue
            if kind == "w":
                b_polys.append(poly)
            unit_type = (UNIT_ADDRESSED_BUILDING if has_addr
                         else UNIT_UNADDRESSED_BUILDING)
            buildings.append(DemandUnit(kind, obj.id, unit_type, pt, lon, lat,
                                        housenumber=tags.get("addr:housenumber")))
        elif has_addr and kind == "n":
            raw_addresses += 1
            addr_nodes.append(DemandUnit(kind, obj.id, UNIT_ADDRESS_NODE, pt, lon, lat,
                                         housenumber=tags.get("addr:housenumber")))

    raw_addresses += sum(1 for u in buildings if u.housenumber)
    return (buildings, addr_nodes, b_polys, serviceable, tier_c,
            raw_buildings, raw_addresses)


def _resolve_origins(bender_pbf, proj, dcfg):
    """Central origin + BAM (resolved via the landmark) + other outer origins."""
    cfg = dcfg["restaurant_origins"]
    radius = float(cfg["cluster_radius_m"])
    min_outer = int(cfg["min_outer_cluster_pois"])
    landmark_name = cfg.get("bam_landmark_name")

    pois, excluded, landmark = [], [], None
    for obj in osmium.FileProcessor(str(bender_pbf)).with_locations():
        tags = {k: v for k, v in obj.tags}
        amenity = tags.get("amenity")
        if obj.type_str() == "n":
            pt = Point(*proj.to_m(obj.lon, obj.lat))
        elif obj.type_str() == "w":
            cs = [proj.to_m(nd.lon, nd.lat) for nd in obj.nodes if nd.location.valid()]
            if not cs:
                continue
            pt = Point(sum(c[0] for c in cs) / len(cs), sum(c[1] for c in cs) / len(cs))
        else:
            continue
        if tags.get("name") == landmark_name:
            landmark = pt
        takeaway = tags.get("takeaway") in ("yes", "only") or tags.get("delivery") == "yes"
        if amenity in FOOD_AMENITIES or (takeaway and amenity):
            if (tags.get("name") or "").strip():
                pois.append((pt, tags.get("name"), amenity))
            else:
                excluded.append({"reason": "unnamed_venue", "amenity": amenity})

    pts = [p[0] for p in pois]
    remaining, groups = list(range(len(pts))), []
    while remaining:
        seed = remaining.pop(0)
        comp, frontier = [seed], [seed]
        while frontier:
            cur = frontier.pop()
            for i in list(remaining):
                if pts[cur].distance(pts[i]) <= radius:
                    remaining.remove(i)
                    comp.append(i)
                    frontier.append(i)
        groups.append(sorted(comp))
    groups.sort(key=lambda g: (-len(g), g[0]))

    def centroid(idxs):
        return Point(sum(pts[i].x for i in idxs) / len(idxs),
                     sum(pts[i].y for i in idxs) / len(idxs))

    central = groups[0]
    outer = [g for g in groups[1:] if len(g) >= min_outer]
    for g in groups[1:]:
        if len(g) < min_outer:
            excluded.append({"reason": "outer_cluster_too_small",
                             "pois": [pois[i][1] for i in g]})

    bam_idx = None
    if landmark is not None and outer:
        bam_idx = min(range(len(outer)),
                      key=lambda i: centroid(outer[i]).distance(landmark))

    total_outer = sum(len(g) for g in outer) or 1
    origins = [{"key": "central_bender_origin", "role": "central",
                "point": centroid(central), "weight": cfg["central_weight"],
                "poi_count": len(central),
                "members": [pois[i][1] for i in central]}]
    for i, g in enumerate(outer):
        is_bam = (i == bam_idx)
        origins.append({
            "key": "bam_origin" if is_bam else f"outer_origin_{i + 1}",
            "role": "bam" if is_bam else "outer_other",
            "point": centroid(g),
            "weight": round(cfg["outer_total_weight"] * len(g) / total_outer, 6),
            "poi_count": len(g), "members": [pois[i2][1] for i2 in g],
            "distance_to_bam_landmark_km": (
                round(centroid(g).distance(landmark) / 1000.0, 3)
                if landmark is not None else None)})
    doc = {
        "central_weight": cfg["central_weight"],
        "outer_total_weight": cfg["outer_total_weight"],
        "bam_landmark": landmark_name,
        "bam_landmark_found": landmark is not None,
        "bam_resolution": ("the outer cluster nearest the configured BAM landmark is "
                           "labelled bam_origin; the others are outer_other and are "
                           "NOT called BAM"),
        "included_pois": [{"name": n, "amenity": a} for _p, n, a in pois],
        "excluded_pois": excluded,
        "source": "local Moldova extract (no Nominatim, no Overpass)",
    }
    return origins, doc


def build(pbf: Path, repo_root: Path, osrm_url: str) -> int:
    trim_cfg = yaml.safe_load((repo_root / "config/service-trim.yml").read_text("utf-8"))
    dcfg = yaml.safe_load((repo_root / "config/demand.yml").read_text("utf-8"))
    bcfg = yaml.safe_load((repo_root / "config/bands.yml").read_text("utf-8"))
    taxi = yaml.safe_load((repo_root / "config/taxi-calibration.yml").read_text("utf-8"))
    audit_cfg = load_audit(repo_root / "config/audit.yml")
    workdir = repo_root / audit_cfg.workdir

    client = OsrmClient(osrm_url)
    if not client.is_up():
        print(f"error: local OSRM server not reachable at {osrm_url}", file=sys.stderr)
        return 2

    territories = trim_cfg["territories"]
    relations = sorted({t["source_relation"] for t in territories})
    boundaries, city_pbfs = [], {}
    for rel in relations:
        res = extract_boundary(pbf, rel, workdir, strategy=audit_cfg.osmium_strategy)
        gj = json.loads(Path(res.boundary_geojson).read_text("utf-8"))
        boundaries.append(next(shape(f["geometry"]) for f in gj["features"]
                               if f["geometry"]["type"] in ("Polygon", "MultiPolygon")))
        city_pbfs[rel] = res.city_pbf
    centre = unary_union(boundaries).centroid
    proj = local_projection(centre.y, centre.x)

    cand = json.loads((repo_root / "docs/data/candidate-service-area.geojson")
                      .read_text("utf-8"))
    service_all = unary_union([to_metres(shape(f["geometry"]), proj)
                               for f in cand["features"]])

    tier_by_id, street_by_id = {}, {}
    for row in csv.DictReader((repo_root / "docs/data/street-demand-audit.csv")
                              .read_text("utf-8").splitlines()):
        for oid in row["osm_ids"].split(";"):
            if oid:
                tier_by_id[int(oid)] = row["demand_tier"]
                street_by_id[int(oid)] = (row["settlement"], row["street_ru"])

    all_buildings, all_addr, all_polys = [], [], []
    serviceable_streets, tier_c_streets = [], []
    raw_b = raw_a = 0
    for city in city_pbfs.values():
        b, a, polys, sv, tc, rb, ra = _load_units_and_streets(
            city, proj, tier_by_id, street_by_id)
        all_buildings += b
        all_addr += a
        all_polys += polys
        serviceable_streets += sv
        tier_c_streets += tc
        raw_b += rb
        raw_a += ra

    kept_addr, merged = deduplicate_address_nodes(all_buildings, all_addr, all_polys)
    units = all_buildings + kept_addr
    seen, unique_units = set(), []
    for u in units:
        if u.uid not in seen:
            seen.add(u.uid)
            unique_units.append(u)

    # --- attribute to streets; split serviceable vs Tier C vs outside ---
    sv_geoms = [s[0] for s in serviceable_streets]
    tc_geoms = [s[0] for s in tier_c_streets]
    sv_tree = STRtree(sv_geoms) if sv_geoms else None
    tc_tree = STRtree(tc_geoms) if tc_geoms else None
    serviceable_units, tier_c_units, outside_units = [], [], []
    for u in unique_units:
        d_sv, sv_i = float("inf"), None
        if sv_tree is not None:
            i = int(sv_tree.nearest(u.point))
            d_sv, sv_i = sv_geoms[i].distance(u.point), i
        d_tc = float("inf")
        if tc_tree is not None:
            j = int(tc_tree.nearest(u.point))
            d_tc = tc_geoms[j].distance(u.point)
        if d_tc < d_sv and d_tc <= 100.0:
            tier_c_units.append(u)
            continue
        if not service_all.covers(u.point):
            outside_units.append(u)
            continue
        if sv_i is not None and d_sv <= 150.0:
            u.settlement, u.street = serviceable_streets[sv_i][1]
            u.tier = serviceable_streets[sv_i][2]
        else:
            u.tier = "A"
        serviceable_units.append(u)

    print(f"units: raw_buildings={raw_b} raw_address_objects={raw_a} "
          f"merged_duplicates={merged} unique={len(unique_units)} "
          f"serviceable={len(serviceable_units)} tier_c={len(tier_c_units)} "
          f"outside={len(outside_units)}")

    bender_rel = next(t["source_relation"] for t in territories
                      if t["key"] == "bender_core")
    origins, origin_doc = _resolve_origins(city_pbfs[bender_rel], proj, dcfg)
    o_coords = [proj.to_deg(o["point"].x, o["point"].y) for o in origins]
    o_weights = [o["weight"] for o in origins]

    dests = [(u.lon, u.lat) for u in serviceable_units]
    try:
        dist_m, dur_s = client.table(o_coords, dests,
                                     chunk_size=int(bcfg["osrm"]["table_chunk"]))
    except OsrmError as exc:
        print(f"error: OSRM table failed: {exc}", file=sys.stderr)
        return 2

    rows, unreachable = [], []
    for idx, u in enumerate(serviceable_units):
        d_per = [dist_m[i][idx] for i in range(len(origins))]
        t_per = [dur_s[i][idx] for i in range(len(origins))]
        exp_km = expected_cost(d_per, o_weights)
        exp_min = expected_cost(t_per, o_weights)
        if exp_km is None:
            unreachable.append(u)
            continue
        central_i = next(i for i, o in enumerate(origins) if o["role"] == "central")
        bam_i = next((i for i, o in enumerate(origins) if o["role"] == "bam"), None)
        rows.append({
            "uid": u.uid, "osm_type": u.osm_type, "osm_id": u.osm_id,
            "unit_type": u.unit_type, "settlement": u.settlement or "",
            "street_ru": u.street or "", "housenumber": u.housenumber or "",
            "tier": u.tier, "lon": round(u.lon, 5), "lat": round(u.lat, 5),
            "weight": unit_weight(u, tier_weight(u.tier or "A")),
            "expected_km": round(exp_km / 1000.0, 3),
            "expected_min": round((exp_min or 0) / 60.0, 3),
            "central_km": round((d_per[central_i] or 0) / 1000.0, 3),
            "central_min": round((t_per[central_i] or 0) / 60.0, 3),
            "bam_km": (round(d_per[bam_i] / 1000.0, 4)
                       if bam_i is not None and d_per[bam_i] is not None else None),
            "bam_min": (round(t_per[bam_i] / 60.0, 3)
                        if bam_i is not None and t_per[bam_i] is not None else None),
            "worst_origin_km": round((worst_cost(d_per) or 0) / 1000.0, 3),
            "point": u.point,
        })
    print(f"routed units: {len(rows)} | unreachable: {len(unreachable)}")

    # --- ordered bands ---
    values = [r["expected_km"] for r in rows]
    weights = [r["weight"] for r in rows]
    bins = make_bins(values, weights, float(bcfg["bands"]["bin_width_km"]))
    results, band_features = {}, []
    for k in bcfg["bands"]["k_values"]:
        bounds = optimal_bands(bins, k, float(bcfg["bands"]["min_weight_share"]))
        edges = band_edges(bins, bounds)
        for r in rows:
            r[f"band_k{k}"] = assign_band(r["expected_km"], edges) + 1
        results[str(k)] = _band_metrics(k, rows, edges, origins, bcfg)
        _band_polygons(k, rows, proj, service_all, bcfg, band_features)
    _write(repo_root, rows, results, band_features, origins, origin_doc, taxi, bcfg,
           {"raw_building_objects": raw_b, "raw_address_objects": raw_a,
            "duplicates_merged": merged, "unique_units": len(unique_units),
            "serviceable_units": len(serviceable_units),
            "tier_c_units_excluded": len(tier_c_units),
            "outside_service_area": len(outside_units),
            "unreachable": len(unreachable),
            **summarise(serviceable_units)},
           tier_c_units, outside_units, unreachable, client, o_coords, origins, proj)
    return 0


def _band_metrics(k, rows, edges, origins, bcfg):
    zones = []
    per_band = {}
    for r in rows:
        per_band.setdefault(r[f"band_k{k}"], []).append(r)
    street_bands, split = {}, []
    for r in rows:
        if r["street_ru"]:
            street_bands.setdefault((r["settlement"], r["street_ru"]), set()).add(
                r[f"band_k{k}"])
    split = sorted(f"{s[0]}: {s[1]}" for s, b in street_bands.items() if len(b) > 1)

    ordered_values = []
    for zone in sorted(per_band):
        rs = per_band[zone]
        vals = [r["expected_km"] for r in rs]
        tms = [r["expected_min"] for r in rs]
        ws = [r["weight"] for r in rs]
        ordered_values.append(vals)
        vs = sorted(vals)
        pct_default = vs

        def pct(p, seq=None, _default=pct_default):
            seq = _default if seq is None else seq
            if not seq:
                return None
            ordered = sorted(seq)
            i = min(int(len(ordered) * p / 100), len(ordered) - 1)
            return round(ordered[i], 3)

        zones.append({
            "zone": zone, "name": f"Zone {zone}",
            "km": {"min": round(min(vals), 3), "p50": pct(50), "p75": pct(75),
                   "p90": pct(90), "max": round(max(vals), 3)},
            "minutes": {"min": round(min(tms), 2), "p50": pct(50, tms),
                        "p75": pct(75, tms), "p90": pct(90, tms),
                        "max": round(max(tms), 2)},
            "unique_delivery_units": len(rs),
            "address_units": sum(1 for r in rs if r["unit_type"] != UNIT_UNADDRESSED_BUILDING),
            "demand_weight": round(sum(ws), 2),
            "km_dispersion": round(dispersion(vals, ws) or 0, 4),
            "central_km_p50": pct(50, [r["central_km"] for r in rs]),
            "central_min_p50": pct(50, [r["central_min"] for r in rs]),
            "bam_km_p50": pct(50, [r["bam_km"] for r in rs if r["bam_km"] is not None]),
            "bam_min_p50": pct(50, [r["bam_min"] for r in rs if r["bam_min"] is not None]),
            "streets": sorted({f"{r['settlement']}: {r['street_ru']}"
                               for r in rs if r["street_ru"]}),
        })
    return {"k": k, "upper_edges_km": [round(e, 3) for e in edges], "zones": zones,
            "monotonic": is_monotonic(ordered_values), "split_streets": len(split),
            "split_street_list": split,
            "weighted_dispersion": round(
                sum(z["km_dispersion"] * z["demand_weight"] for z in zones)
                / max(sum(z["demand_weight"] for z in zones), 1e-9), 4)}


def _band_polygons(k, rows, proj, service_all, bcfg, out):
    buf = float(bcfg["bands"]["polygon_buffer_m"])
    per_band = {}
    for r in rows:
        per_band.setdefault(r[f"band_k{k}"], []).append(r["point"])
    covered = None
    for zone in sorted(per_band):
        geom = unary_union([p.buffer(buf) for p in per_band[zone]]).intersection(
            service_all)
        # Simplify FIRST: simplifying after the difference could push an edge back
        # across a neighbour and reintroduce overlap.
        geom = geom.simplify(3.0).buffer(0)
        if covered is not None:
            geom = geom.difference(covered)          # mutually exclusive by order
        if geom.is_empty:
            continue
        covered = geom if covered is None else unary_union([covered, geom]).buffer(0)
        # Snap to the published 5-decimal grid so the geometry is valid AS WRITTEN;
        # rounding afterwards could otherwise self-intersect.
        geom_deg = set_precision(to_degrees(geom, proj), 1e-5)
        if geom_deg.is_empty:
            continue
        if not geom_deg.is_valid:
            geom_deg = geom_deg.buffer(0)
        out.append(_feature(geom_deg, {
            "k": k, "zone": zone, "name": f"Zone {zone}", "kind": "tariff_band",
            "units": len(per_band[zone]), "area_km2": round(area_m2(geom) / 1e6, 4),
            "status": "prepared_owner_review_required"}))


def _write(repo_root, rows, results, band_features, origins, origin_doc, taxi, bcfg,
           counts, tier_c_units, outside_units, unreachable, client, o_coords,
           origin_meta, proj):
    data = repo_root / "docs/data"
    ks = sorted(results)
    fields = ["uid", "osm_type", "osm_id", "unit_type", "settlement", "street_ru",
              "housenumber", "tier", "lon", "lat", "weight", "expected_km",
              "expected_min", "central_km", "central_min", "bam_km", "bam_min",
              "worst_origin_km"] + [f"band_k{k}" for k in ks]
    rows_sorted = sorted(rows, key=lambda r: (r["expected_km"], r["uid"]))
    with open(data / "delivery-units.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for r in rows_sorted:
            w.writerow({k: r.get(k) for k in fields})

    with open(data / "delivery-exceptions.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["uid", "osm_type", "osm_id", "unit_type", "lon", "lat", "reason"])
        for u in unreachable:
            w.writerow([u.uid, u.osm_type, u.osm_id, u.unit_type,
                        round(u.lon, 6), round(u.lat, 6), "unreachable_by_osrm"])
        for u in outside_units:
            w.writerow([u.uid, u.osm_type, u.osm_id, u.unit_type,
                        round(u.lon, 6), round(u.lat, 6), "outside_service_area"])
        for u in tier_c_units:
            w.writerow([u.uid, u.osm_type, u.osm_id, u.unit_type,
                        round(u.lon, 6), round(u.lat, 6), "tier_c_no_delivery"])

    exc_feats = []
    for group, reason in ((unreachable, "unreachable_by_osrm"),
                          (outside_units, "outside_service_area"),
                          (tier_c_units, "tier_c_no_delivery")):
        for u in group:
            exc_feats.append({"type": "Feature",
                              "properties": {"uid": u.uid, "unit_type": u.unit_type,
                                             "reason": reason},
                              "geometry": {"type": "Point",
                                           "coordinates": [round(u.lon, 5),
                                                           round(u.lat, 5)]}})
    exc_feats.sort(key=lambda f: (f["properties"]["reason"], f["properties"]["uid"]))
    jsonutil.write_compact(data / "delivery-exceptions.geojson",
                           {"type": "FeatureCollection", "features": exc_feats})

    jsonutil.write_compact(data / "tariff-bands.geojson",
                           {"type": "FeatureCollection", "features": band_features})
    jsonutil.write(data / "restaurant-origins.geojson", {
        "type": "FeatureCollection", "selection": origin_doc,
        "features": [_feature(to_degrees(o["point"], proj), {
            "key": o["key"], "role": o["role"], "weight": o["weight"],
            "poi_count": o["poi_count"],
            "distance_to_bam_landmark_km": o.get("distance_to_bam_landmark_km"),
        }) for o in origins]})

    qa = _qa_routes(client, o_coords, origin_meta)
    jsonutil.write(data / "osrm-qa-routes.json", qa)

    rec = _recommend(results)
    doc = {
        "schema": "bender-tariff-bands/6",
        "generated_at": _now(),
        "model": "ordered_cost_bands_over_osrm_road_km",
        "not_used": ["network Voronoi", "spatial K-means", "customer-centred seeds",
                     "Lloyd clustering"],
        "routing_engine": {"name": "OSRM", "algorithm": "MLD", "profile": "car.lua",
                           "source_pbf": "moldova-latest.osm.pbf",
                           "handles": ["node topology", "one-way", "turn restrictions",
                                       "bridges/tunnels", "barriers",
                                       "motor_vehicle/vehicle/access", "maxspeed"]},
        "prices_assigned": False, "tariffs_created": False,
        "direct_integration": False,
        "taxi_calibration": taxi.get("taxi_calibration"),
        "taxi_calibration_supplied": bool(taxi.get("calibration_supplied")),
        "recommendation_status": "owner_review_required",
        "recommendation": rec,
        "unit_counts": counts,
        "origins": origin_doc,
        "candidates": results,
        "qa_routes": qa,
        "limitations": [
            "Bands are cost ranges, not geographic clusters; a band polygon is only "
            "a drawing of which units fall in that price range.",
            "Tier C units are no_delivery and appear in no band or matrix.",
            "Travel times come from the OSRM car profile without live traffic.",
            "No money is assigned; taxi calibration fields remain null.",
        ],
    }
    jsonutil.write(data / "tariff-band-metrics.json", doc)
    reports = repo_root / "reports/stage-06"
    reports.mkdir(parents=True, exist_ok=True)
    jsonutil.write(reports / "tariff-bands.json", doc)
    (reports / "tariff-bands.md").write_text(_md(doc), encoding="utf-8", newline="\n")


def _qa_routes(client, o_coords, origins):
    targets = {"Parkany": (29.5174, 46.8372), "Giska": (29.4414, 46.7814),
               "Protyagailovka": (29.4421, 46.8256), "Lipcani": (29.4802, 46.8462)}
    out = {"routes": [], "probes": {}}
    for o, coord in zip(origins, o_coords, strict=False):
        if o["role"] not in ("central", "bam"):
            continue
        for name, t in targets.items():
            r = client.route(coord, t)
            out["routes"].append({
                "origin": o["key"], "origin_role": o["role"], "target": name,
                "distance_km": round(r[0] / 1000.0, 3) if r else None,
                "duration_min": round(r[1] / 60.0, 2) if r else None})
    a, b = (29.4828, 46.8242), (29.4869, 46.8206)
    fwd, rev = client.route(a, b), client.route(b, a)
    out["probes"]["directionality"] = {
        "note": ("forward and reverse road distance between the same pair; a "
                 "difference proves one-way/turn handling, identical values would "
                 "suggest an undirected graph"),
        "forward_km": round(fwd[0] / 1000.0, 3) if fwd else None,
        "reverse_km": round(rev[0] / 1000.0, 3) if rev else None,
        "asymmetric": bool(fwd and rev and abs(fwd[0] - rev[0]) > 1.0)}
    br = client.route((29.4732, 46.8360), (29.4600, 46.8365))
    out["probes"]["bridge_crossing"] = {
        "note": ("route across the Dniester bridge area; distance must be a real "
                 "road distance, not a straight-line jump between crossing ways"),
        "distance_km": round(br[0] / 1000.0, 3) if br else None,
        "duration_min": round(br[1] / 60.0, 2) if br else None,
        "plausible": bool(br and br[0] > 900)}
    return out


def _recommend(results):
    """Composite, transparent comparison. The owner still decides."""
    scored = {}
    for k, res in results.items():
        zones = res["zones"]
        weights = [z["demand_weight"] for z in zones]
        units = [z["unique_delivery_units"] for z in zones]
        total_units = sum(units) or 1
        scored[k] = {
            "weighted_km_dispersion": res["weighted_dispersion"],
            "split_streets": res["split_streets"],
            "monotonic": res["monotonic"],
            "demand_balance_min_over_max": round(
                min(weights) / max(weights), 3) if weights and max(weights) else 0,
            "smallest_zone_units": min(units, default=0),
            "smallest_zone_unit_share": round(min(units, default=0) / total_units, 3),
        }

    ks = sorted(scored)

    def norm(key, lower_is_better):
        vals = [scored[k][key] for k in ks]
        lo, hi = min(vals), max(vals)
        out = {}
        for k in ks:
            if hi == lo:
                out[k] = 1.0
            else:
                frac = (scored[k][key] - lo) / (hi - lo)
                out[k] = 1.0 - frac if lower_is_better else frac
        return out

    disp = norm("weighted_km_dispersion", True)
    splits = norm("split_streets", True)
    balance = norm("demand_balance_min_over_max", False)
    smallest = norm("smallest_zone_unit_share", False)
    weights_used = {"km_dispersion": 0.40, "split_streets": 0.20,
                    "demand_balance": 0.30, "smallest_zone_share": 0.10}
    for k in ks:
        scored[k]["composite_score"] = round(
            disp[k] * weights_used["km_dispersion"]
            + splits[k] * weights_used["split_streets"]
            + balance[k] * weights_used["demand_balance"]
            + smallest[k] * weights_used["smallest_zone_share"], 4)
    best = max(ks, key=lambda k: (scored[k]["composite_score"], -int(k)))
    return {
        "status": "owner_review_required",
        "suggested_k": int(best),
        "criteria_weights": weights_used,
        "why": ("composite of kilometre dispersion, split streets, demand balance and "
                "smallest-zone share. Finer bands always lower dispersion, so balance "
                "and economic interpretability are weighted too. This is a suggestion "
                "only: the owner must confirm before any price is attached."),
        "comparison": scored,
    }


def _md(doc):
    lines = ["# Stage 06 — ordered OSRM tariff distance bands", "",
             f"- Generated (UTC): `{doc['generated_at']}`",
             f"- model: **{doc['model']}** (не пространственная кластеризация)",
             f"- routing: **OSRM {doc['routing_engine']['algorithm']}**, профиль "
             f"`{doc['routing_engine']['profile']}`",
             f"- recommendation_status: **{doc['recommendation_status']}** · "
             f"suggested K: **{doc['recommendation']['suggested_k']}**",
             f"- prices assigned: **{doc['prices_assigned']}**", "",
             "## Demand units", ""]
    c = doc["unit_counts"]
    lines += [f"- raw building objects: **{c['raw_building_objects']}**",
              f"- raw address objects: **{c['raw_address_objects']}**",
              f"- duplicates merged (address node on its building): "
              f"**{c['duplicates_merged']}**",
              f"- unique serviceable delivery units: **{c['serviceable_units']}** "
              f"(из них адресных: {c['address_units']})",
              f"- Tier C units excluded (no_delivery): **{c['tier_c_units_excluded']}**",
              f"- outside service area: **{c['outside_service_area']}** · unreachable: "
              f"**{c['unreachable']}** (см. delivery-exceptions.csv)", ""]
    for k, res in doc["candidates"].items():
        lines += [f"## K={k} ordered bands", "",
                  f"- monotonic: **{res['monotonic']}** · split streets: "
                  f"{res['split_streets']} · weighted km dispersion: "
                  f"{res['weighted_dispersion']}", "",
                  "| Зона | км min/p50/p75/p90/max | мин p50/p90 | единиц | вес | "
                  "центр км | БАМ км |", "|---|---|---|---:|---:|---:|---:|"]
        for z in res["zones"]:
            km, mn = z["km"], z["minutes"]
            lines.append(f"| {z['name']} | {km['min']}/{km['p50']}/{km['p75']}/"
                         f"{km['p90']}/{km['max']} | {mn['p50']}/{mn['p90']} | "
                         f"{z['unique_delivery_units']} | {z['demand_weight']} | "
                         f"{z['central_km_p50']} | {z['bam_km_p50']} |")
        lines += [""]
    lines += ["## QA routes (OSRM)", "", "| origin | target | км | мин |", "|---|---|---:|---:|"]
    for r in doc["qa_routes"]["routes"]:
        lines.append(f"| {r['origin']} | {r['target']} | {r['distance_km']} | "
                     f"{r['duration_min']} |")
    p = doc["qa_routes"]["probes"]
    lines += ["", f"- directionality probe: forward {p['directionality']['forward_km']} км, "
              f"reverse {p['directionality']['reverse_km']} км, asymmetric="
              f"**{p['directionality']['asymmetric']}**",
              f"- bridge crossing probe: {p['bridge_crossing']['distance_km']} км, "
              f"plausible=**{p['bridge_crossing']['plausible']}**", "",
              "## Limitations", ""] + [f"- {x}" for x in doc["limitations"]] + [""]
    return "\n".join(lines)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--pbf", default=None)
    p.add_argument("--source", default="osm_moldova")
    p.add_argument("--repo-root", default=".")
    p.add_argument("--osrm-url", default="http://127.0.0.1:5000")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root)
    sources = load_sources(repo_root / "config/sources.yml")
    pbf = repo_root / (args.pbf or sources[args.source].destination)
    if not pbf.is_file():
        print(f"error: PBF not found: {pbf}", file=sys.stderr)
        return 2
    return build(pbf, repo_root, args.osrm_url)


if __name__ == "__main__":
    raise SystemExit(main())
