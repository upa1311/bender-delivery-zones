#!/usr/bin/env python
"""Stage 04 — residential demand audit + demand-based candidate service areas.

Supersedes the Stage-03 candidate builder: candidate polygons are now shaped by
*residential* demand (Tier A + Tier B) instead of every ``building=*`` footprint.
Sheds, garages, greenhouses, warehouses, industrial halls, ruins and construction
sites are classified out and never anchor geometry or count as customers.

Local-only pipeline (needs the Moldova PBF + osmium-tool). Produces:

* docs/data/source-boundaries.geojson       untouched OSM admin boundaries
* docs/data/candidate-service-area.geojson  Tier A+B residential demand areas
* docs/data/excluded-large-areas.geojson    farmland / forest / empty land
* docs/data/sparse-building-review.geojson  isolated groups below the threshold
* docs/data/tier-c-manual-review.geojson    Tier C fringe streets (manual only)
* docs/data/boundary-questions.geojson      owner-wording ambiguities
* docs/data/buildings.geojson               classified buildings (MultiPoint)
* docs/data/street-demand-audit.csv         the street-level demand table
* docs/data/demand-summary.json             before/after counts
* docs/data/k-candidates.{json,geojson}     K=4 / K=5 PREPARED, not chosen
* docs/data/service-area-diff.json          areas, reduction %, building counts
* reports/stage-04/residential-demand-audit.{json,md}

No zones, no tariffs, no OSRM routing graph, no Direct integration.
"""

from __future__ import annotations

import argparse
import csv
import heapq
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import osmium
import yaml
from shapely import voronoi_polygons
from shapely.geometry import LineString, MultiPoint, Point, Polygon, mapping, shape
from shapely.ops import linemerge, unary_union

from bender_zones import jsonutil
from bender_zones.config import load_audit, load_sources
from bender_zones.demand import (
    ABANDONED_OR_RUIN,
    CONFIRMED_RESIDENTIAL,
    CONSTRUCTION,
    NON_RESIDENTIAL,
    OUTBUILDING,
    PROBABLE_RESIDENTIAL,
    UNKNOWN,
    StreetDemand,
    TierThresholds,
    affects_zone_pricing,
    assign_tier,
    classify_building,
    counts_as_customer,
    is_apartment_building,
    is_demand_anchor,
    service_status,
    tier_weight,
)
from bender_zones.extract import extract_boundary
from bender_zones.service_area import classify_road, load_local_ru_table, resolve_ru_name
from bender_zones.service_trim import (
    EXCL_EMPTY,
    EXCL_NON_RESIDENTIAL,
    EXCL_OUTBUILDINGS,
    EXCL_OWNER_LIMIT,
    EXCL_SPARSE,
    REASON_ACCESS,
    REASON_ADDRESSED,
    REASON_DENSE,
    REASON_OWNER,
    REASON_STREET,
    TrimParams,
    area_m2,
    build_candidate_geometry,
    clip_to_side,
    count_points_within,
    drop_small_components,
    exclusion_reason_for_tags,
    local_projection,
    points_within,
    polygon_components,
    reduction_pct,
    side_of_line,
    to_degrees,
    to_metres,
)
from bender_zones.versions import tool_versions

WARNING_RU = ("Рабочая территория создана по жилой застройке (Tier A + Tier B) и "
              "указаниям владельца. Это ещё не четыре зоны доставки и не тарифы.")


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- OSM loading with demand classification ---------------------------------

class CityFeatures:
    def __init__(self):
        self.buildings = []       # dicts: geom, point, cls, tags
        self.address_points = []  # metric Points of addr:housenumber objects
        self.streets = []         # dicts: name, osm_id, geom
        self.landuse = []         # (metric polygon, tags)
        self.places = []          # (osm_id, tags, metric Point)
        self.pois = []            # metric Points of civic/commercial POIs


def load_city_features(city_pbf: Path, proj, poi_keys) -> CityFeatures:
    feats = CityFeatures()
    poi_keys = set(poi_keys)
    for obj in osmium.FileProcessor(str(city_pbf)).with_locations():
        tags = {k: v for k, v in obj.tags}
        kind = obj.type_str()

        if kind == "n":
            pt = Point(*proj.to_m(obj.lon, obj.lat))
            if tags.get("building") is not None:
                feats.buildings.append({"geom": pt, "point": pt,
                                        "cls": classify_building(tags), "tags": tags})
            if tags.get("addr:housenumber") is not None:
                feats.address_points.append(pt)
            if tags.get("place") is not None or tags.get("name"):
                feats.places.append((obj.id, tags, pt))
            if any(tags.get(k) for k in poi_keys):
                feats.pois.append(pt)
            continue

        if kind != "w":
            continue

        coords = []
        ok = True
        for nd in obj.nodes:
            if not nd.location.valid():
                ok = False
                break
            coords.append(proj.to_m(nd.lon, nd.lat))
        if not ok or len(coords) < 2:
            continue
        is_closed = len(coords) >= 4 and coords[0] == coords[-1]

        if tags.get("building") is not None:
            if not is_closed:
                continue
            try:
                poly = Polygon(coords)
            except Exception:
                continue
            if not poly.is_valid or poly.area <= 0:
                continue
            centroid = poly.centroid
            feats.buildings.append({"geom": poly, "point": centroid,
                                    "cls": classify_building(tags), "tags": tags})
            if tags.get("addr:housenumber") is not None:
                feats.address_points.append(centroid)
            if any(tags.get(k) for k in poi_keys):
                feats.pois.append(centroid)
            continue

        if is_closed and tags.get("addr:housenumber") is not None:
            try:
                feats.address_points.append(Polygon(coords).centroid)
            except Exception:
                pass

        landuse_val = tags.get("landuse") or tags.get("natural") or tags.get("leisure")
        if landuse_val and is_closed:
            try:
                poly = Polygon(coords)
                if poly.is_valid and poly.area > 0:
                    feats.landuse.append((poly, tags))
            except Exception:
                pass
            continue

        if tags.get("highway") is not None and tags.get("name"):
            _cls, is_address, _rev = classify_road(tags)
            if is_address:
                feats.streets.append({"name": tags["name"], "osm_id": obj.id,
                                      "geom": LineString(coords), "tags": tags})
    return feats


# --- street-network distance (measurement only, no routing engine) ----------

def street_graph_distances(streets, core_geom, snap_m: float = 1.0):
    """Shortest distance along street centrelines from the core, per node.

    This is an in-memory measurement over OSM centrelines with Dijkstra. It is
    NOT a routing engine: no OSRM, no persisted routing graph, no turn costs,
    no delivery routes. Used only to report how far a fringe street is.
    """
    def key(x, y):
        return (round(x / snap_m), round(y / snap_m))

    adj: dict = {}
    for st in streets:
        coords = list(st["geom"].coords)
        for (x1, y1), (x2, y2) in zip(coords, coords[1:], strict=False):
            a, b = key(x1, y1), key(x2, y2)
            if a == b:
                continue
            w = math.hypot(x2 - x1, y2 - y1)
            adj.setdefault(a, []).append((b, w))
            adj.setdefault(b, []).append((a, w))

    dist: dict = {}
    heap = []
    if not core_geom.is_empty:
        for st in streets:
            for x, y in st["geom"].coords:
                if core_geom.covers(Point(x, y)):
                    k = key(x, y)
                    if k not in dist:
                        dist[k] = 0.0
                        heap.append((0.0, k))
    heapq.heapify(heap)
    while heap:
        d, node = heapq.heappop(heap)
        if d > dist.get(node, math.inf):
            continue
        for nxt, w in adj.get(node, ()):
            nd = d + w
            if nd < dist.get(nxt, math.inf):
                dist[nxt] = nd
                heapq.heappush(heap, (nd, nxt))
    return dist, key


# --- per-street demand ------------------------------------------------------

def street_demand_rows(territory_key, streets, buildings, address_points, pois,
                       core_geom, evidence_stems, corridor_m, thresholds,
                       local_table, proj):
    """Aggregate demand evidence per distinct street name."""
    by_name: dict = {}
    for st in streets:
        by_name.setdefault(st["name"], []).append(st)

    dist_map, keyfn = street_graph_distances(streets, core_geom)
    rows = []
    for name in sorted(by_name):
        segs = by_name[name]
        merged = unary_union([s["geom"] for s in segs])
        corridor = merged.buffer(corridor_m)

        d = StreetDemand()
        for b in buildings:
            if not corridor.covers(b["point"]):
                continue
            cls = b["cls"]
            if cls == CONFIRMED_RESIDENTIAL:
                d.confirmed_residential_buildings += 1
                if is_apartment_building(b["tags"]):
                    d.apartment_buildings += 1
            elif cls == PROBABLE_RESIDENTIAL:
                d.probable_residential_buildings += 1
            elif cls == NON_RESIDENTIAL:
                d.nonresidential_buildings += 1
            elif cls == OUTBUILDING:
                d.outbuildings += 1
            elif cls in (ABANDONED_OR_RUIN, CONSTRUCTION):
                d.abandoned_or_ruin += 1
        d.confirmed_addresses = sum(1 for p in address_points if corridor.covers(p))
        d.civic_or_commercial_pois = sum(1 for p in pois if corridor.covers(p))

        ru_display, _src, _status = resolve_ru_name(segs[0]["tags"], local_table)
        haystack = f"{ru_display} {name}".casefold()
        d.official_web_evidence = any(stem.casefold() in haystack for stem in evidence_stems)

        d.connected_to_core = (not core_geom.is_empty) and merged.intersects(
            core_geom.buffer(50.0))

        best = math.inf
        for s in segs:
            for x, y in s["geom"].coords:
                best = min(best, dist_map.get(keyfn(x, y), math.inf))
        distance_km = round(best / 1000.0, 3) if best < math.inf else None

        tier, reason = assign_tier(d, thresholds)
        rows.append({
            "settlement": territory_key,
            "street_ru": ru_display or name,
            "osm_ids": ";".join(str(s["osm_id"]) for s in sorted(
                segs, key=lambda s: s["osm_id"])),
            "confirmed_addresses": d.confirmed_addresses,
            "confirmed_residential_buildings": d.confirmed_residential_buildings,
            "probable_residential_buildings": d.probable_residential_buildings,
            "apartment_buildings": d.apartment_buildings,
            "nonresidential_buildings": d.nonresidential_buildings,
            "outbuildings": d.outbuildings,
            "abandoned_or_ruin": d.abandoned_or_ruin,
            "official_web_evidence": d.official_web_evidence,
            "civic_or_commercial_pois": d.civic_or_commercial_pois,
            "connected_to_core": d.connected_to_core,
            "distance_to_core_by_road_km": distance_km,
            "demand_tier": tier,
            "affects_zone_pricing": affects_zone_pricing(tier),
            "service_status": service_status(tier),
            "reason": reason,
            "_geom": merged,
            "_name": name,
        })
    return rows


# --- deterministic weighted k-means (PREPARATION only) ----------------------

def kmeans_candidates(points, weights, k, iterations=100):
    """Deterministic weighted k-means. Prepares K candidates; chooses nothing."""
    if len(points) < k:
        return []
    order = sorted(range(len(points)), key=lambda i: (-weights[i], points[i]))
    centres = [points[order[0]]]
    while len(centres) < k:                      # deterministic farthest-point init
        best_i, best_d = None, -1.0
        for i in order:
            p = points[i]
            dmin = min((p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 for c in centres)
            if dmin > best_d:
                best_d, best_i = dmin, i
        centres.append(points[best_i])

    assign = [0] * len(points)
    for _ in range(iterations):
        moved = False
        for i, p in enumerate(points):
            best_c = min(range(k), key=lambda c: (p[0] - centres[c][0]) ** 2
                         + (p[1] - centres[c][1]) ** 2)
            if best_c != assign[i]:
                assign[i] = best_c
                moved = True
        new_centres = []
        for c in range(k):
            wsum = sum(weights[i] for i in range(len(points)) if assign[i] == c)
            if wsum <= 0:
                new_centres.append(centres[c])
                continue
            cx = sum(points[i][0] * weights[i] for i in range(len(points))
                     if assign[i] == c) / wsum
            cy = sum(points[i][1] * weights[i] for i in range(len(points))
                     if assign[i] == c) / wsum
            new_centres.append((cx, cy))
        centres = new_centres
        if not moved:
            break
    return [{"centre": centres[c], "weight": round(sum(
        weights[i] for i in range(len(points)) if assign[i] == c), 3),
        "members": sum(1 for i in range(len(points)) if assign[i] == c)}
        for c in range(k)]


# --- geojson helpers --------------------------------------------------------

def _round_geom(obj, nd: int = 5):
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, (list, tuple)):
        return [_round_geom(x, nd) for x in obj]
    if isinstance(obj, dict):
        return {k: _round_geom(v, nd) for k, v in obj.items()}
    return obj


def _feature(geom_deg, props: dict) -> dict:
    return {"type": "Feature", "properties": props,
            "geometry": _round_geom(mapping(geom_deg))}


def _out(geom_m, proj, params: TrimParams):
    if geom_m.is_empty:
        return geom_m
    simplified = geom_m.simplify(params.simplify_tolerance_m)
    return to_degrees(simplified if not simplified.is_empty else geom_m, proj)


def _lipcani_cell(feats: CityFeatures, node_id, boundary_m):
    pts = [(oid, pt) for oid, tags, pt in feats.places
           if tags.get("place") in ("suburb", "quarter", "neighbourhood", "city", "town")]
    if len(pts) < 2:
        return None
    target = next((pt for oid, pt in pts if oid == node_id), None)
    if target is None:
        return None
    cells = voronoi_polygons(MultiPoint([p for _o, p in pts]),
                            extend_to=boundary_m.envelope)
    for cell in cells.geoms:
        if cell.covers(target):
            return cell
    return None


def _street_line(streets, name):
    segs = [s["geom"] for s in streets if s["name"] == name]
    if not segs:
        return None
    merged = linemerge(segs) if len(segs) > 1 else segs[0]
    if merged.geom_type == "MultiLineString":
        merged = max(merged.geoms, key=lambda g: g.length)
    return merged


def build(pbf: Path, repo_root: Path) -> int:
    trim_cfg = yaml.safe_load(
        (repo_root / "config" / "service-trim.yml").read_text(encoding="utf-8"))
    demand_cfg = yaml.safe_load(
        (repo_root / "config" / "demand.yml").read_text(encoding="utf-8"))
    taxi_cfg = yaml.safe_load(
        (repo_root / "config" / "taxi-calibration.yml").read_text(encoding="utf-8"))
    params = TrimParams(**trim_cfg["parameters"])
    thresholds = TierThresholds(**demand_cfg["thresholds"])
    corridor_m = float(demand_cfg["street_corridor_m"])
    poi_keys = demand_cfg["poi_keys"]
    audit_cfg = load_audit(repo_root / "config" / "audit.yml")
    local_table = load_local_ru_table(repo_root / "config" / "street-names-ru.yml")
    workdir = repo_root / audit_cfg.workdir

    territories = trim_cfg["territories"]
    relations = sorted({t["source_relation"] for t in territories})

    sources = {}
    for rel in relations:
        result = extract_boundary(pbf, rel, workdir, strategy=audit_cfg.osmium_strategy)
        gj = _load_json(result.boundary_geojson)
        boundary_deg = next((shape(f["geometry"]) for f in gj.get("features", [])
                             if f["geometry"]["type"] in ("Polygon", "MultiPolygon")), None)
        if boundary_deg is None:
            print(f"error: no polygon for relation {rel}", file=sys.stderr)
            return 2
        c = boundary_deg.centroid
        proj = local_projection(c.y, c.x)
        sources[rel] = {"boundary_deg": boundary_deg, "proj": proj,
                        "boundary_m": to_metres(boundary_deg, proj),
                        "features": load_city_features(result.city_pbf, proj, poi_keys)}

    lipcani_node = next((t.get("suburb_place_node") for t in territories
                         if t.get("role") == "bender_suburb"), None)

    candidate_features, source_features, excluded_features = [], [], []
    sparse_features, question_features, tier_c_features = [], [], []
    building_layers, all_rows, diff = [], [], {}
    owner_limit_meta, notes = {}, []
    demand_points, demand_weights = [], []

    global_proj = None

    for terr in territories:
        key = terr["key"]
        rel = terr["source_relation"]
        src = sources[rel]
        proj, feats = src["proj"], src["features"]
        if global_proj is None:
            global_proj = proj
        region_m = src["boundary_m"]

        if terr.get("role") in ("bender_suburb", "bender_rest"):
            cell = _lipcani_cell(feats, lipcani_node, src["boundary_m"])
            if cell is None:
                notes.append("Lipcani suburb node not found; Bender left unsplit.")
            elif terr["role"] == "bender_suburb":
                region_m = region_m.intersection(cell)
            else:
                region_m = region_m.difference(cell)

        # --- scope features to this territory ---
        t_buildings = [b for b in feats.buildings if region_m.covers(b["point"])]
        t_addresses = [p for p in feats.address_points if region_m.covers(p)]
        t_pois = [p for p in feats.pois if region_m.covers(p)]
        t_streets = [s for s in feats.streets
                     if region_m.covers(s["geom"].interpolate(0.5, normalized=True))]

        # --- core = confirmed residential fabric (used for connectivity) ---
        confirmed = [b["geom"] for b in t_buildings if b["cls"] == CONFIRMED_RESIDENTIAL]
        core_geom = Polygon()
        if confirmed:
            comps = polygon_components(build_candidate_geometry(confirmed, [], params))
            if comps:
                core_geom = max(comps, key=lambda g: g.area)

        # Lipcani is part of Bender and the core/Lipcani split is an approximation,
        # so owner evidence for either half applies across both. Other territories
        # stay strictly scoped (e.g. Parkany's Engels must not inherit Lipcani's).
        evidence = list(demand_cfg["external_evidence"].get(key, []))
        if key.startswith("bender"):
            for other in ("bender_core", "bender_lipcani"):
                if other != key:
                    evidence += demand_cfg["external_evidence"].get(other, [])

        rows = street_demand_rows(
            key, t_streets, t_buildings, t_addresses, t_pois, core_geom,
            evidence, corridor_m, thresholds, local_table, proj)

        # --- rebuild candidate from Tier A + Tier B residential demand only ---
        ab_rows = [r for r in rows if r["demand_tier"] in ("A", "B")]
        ab_streets = [r["_geom"] for r in ab_rows]
        anchors = [b["geom"] for b in t_buildings if is_demand_anchor(b["cls"])]
        candidate_m = build_candidate_geometry(anchors, ab_streets, params)
        candidate_m = candidate_m.intersection(region_m)
        candidate_m, sparse = drop_small_components(
            candidate_m, [b["point"] for b in t_buildings if is_demand_anchor(b["cls"])],
            params)

        inclusion = {REASON_DENSE, REASON_STREET, REASON_ADDRESSED}
        exclusion = {EXCL_NON_RESIDENTIAL, EXCL_OUTBUILDINGS}
        if any(r["reason"] == "low_density_connected_to_core" for r in ab_rows):
            inclusion.add(REASON_ACCESS)
        if any(r["demand_tier"] == "C" for r in rows):
            exclusion.add(EXCL_SPARSE)

        limits = terr.get("owner_limits")
        if limits:
            candidate_m, applied, qs, meta = _apply_owner_limits(
                candidate_m, t_streets, limits, proj)
            inclusion.add(REASON_OWNER)
            if applied:
                exclusion.add(EXCL_OWNER_LIMIT)
            question_features.extend(qs)
            if meta:
                owner_limit_meta[key] = meta

        # --- Tier C published separately, never shaping the polygon ---
        for r in rows:
            if r["demand_tier"] != "C":
                continue
            tier_c_features.append(_feature(_out(r["_geom"], proj, params), {
                "settlement": key, "street_ru": r["street_ru"],
                "demand_tier": "C", "service_status": r["service_status"],
                "reason": r["reason"], "osm_ids": r["osm_ids"],
                "confirmed_addresses": r["confirmed_addresses"],
                "probable_residential_buildings": r["probable_residential_buildings"],
                "connected_to_core": r["connected_to_core"],
                "distance_to_core_by_road_km": r["distance_to_core_by_road_km"],
                "affects_zone_pricing": False,
                "note": "Ручная проверка. Не влияет на полигоны, центры зон и тарифы.",
            }))

        # --- demand points for the K=4/K=5 preparation ---
        for r in ab_rows:
            w = tier_weight(r["demand_tier"]) * max(
                r["confirmed_addresses"] + r["confirmed_residential_buildings"], 1)
            mid = r["_geom"].interpolate(0.5, normalized=True)
            lon, lat = proj.to_deg(mid.x, mid.y)
            demand_points.append((lon, lat))
            demand_weights.append(w)

        # --- stats ---
        anchor_pts = [b["point"] for b in t_buildings if is_demand_anchor(b["cls"])]
        customer_pts = [b["point"] for b in t_buildings if counts_as_customer(b["cls"])]
        inside_pts = points_within(candidate_m, anchor_pts)
        inside_ids = {id(p) for p in inside_pts}
        outside_pts = [p for p in anchor_pts if id(p) not in inside_ids]
        addr_in = count_points_within(candidate_m, t_addresses)
        src_area, cand_area = area_m2(region_m), area_m2(candidate_m)

        building_layers.append((key, True, [proj.to_deg(p.x, p.y) for p in inside_pts]))
        building_layers.append((key, False, [proj.to_deg(p.x, p.y) for p in outside_pts]))

        diff[key] = {
            "display_ru": terr["display_ru"],
            "source_relation": rel,
            "source_area_km2": round(src_area / 1e6, 4),
            "candidate_area_km2": round(cand_area / 1e6, 4),
            "reduction_pct": reduction_pct(src_area, cand_area),
            "buildings_included": len(inside_pts),
            "buildings_excluded": len(outside_pts),
            "addresses_inside": addr_in,
            "residential_customers": len(customer_pts),
            "excluded_outbuildings": sum(1 for b in t_buildings if b["cls"] == OUTBUILDING),
            "excluded_nonresidential": sum(1 for b in t_buildings
                                           if b["cls"] == NON_RESIDENTIAL),
            "excluded_abandoned_or_ruin": sum(1 for b in t_buildings
                                              if b["cls"] == ABANDONED_OR_RUIN),
            "excluded_construction": sum(1 for b in t_buildings if b["cls"] == CONSTRUCTION),
            "unknown_buildings": sum(1 for b in t_buildings if b["cls"] == UNKNOWN),
            "streets_tier_a": sum(1 for r in rows if r["demand_tier"] == "A"),
            "streets_tier_b": sum(1 for r in rows if r["demand_tier"] == "B"),
            "streets_tier_c": sum(1 for r in rows if r["demand_tier"] == "C"),
            "inclusion_reasons": sorted(inclusion),
            "exclusion_reasons": sorted(exclusion),
        }

        candidate_features.append(_feature(_out(candidate_m, proj, params), {
            "key": key, "display_ru": terr["display_ru"],
            "kind": "candidate_working_area", "basis": "tier_a_b_residential_demand",
            "source_relation": rel, "zones_created": False,
            **{k: diff[key][k] for k in (
                "source_area_km2", "candidate_area_km2", "reduction_pct",
                "buildings_included", "buildings_excluded", "addresses_inside",
                "streets_tier_a", "streets_tier_b", "streets_tier_c",
                "inclusion_reasons", "exclusion_reasons")},
        }))

        for poly, n in sparse:
            sparse_features.append(_feature(_out(poly, proj, params), {
                "territory": key, "status": "sparse_building_review",
                "buildings": n, "reason": EXCL_SPARSE,
                "note": "Изолированная группа — требует решения владельца.",
            }))

        excl, _ = _collect_excluded(region_m, candidate_m, feats, params, key)
        for item in excl:
            excluded_features.append(_feature(_out(item["geom"], proj, params), {
                "territory": key, "reason": item["reason"], "name": item["name"],
                "landuse": item["landuse"], "area_m2": round(area_m2(item["geom"])),
            }))

        for r in rows:
            r.pop("_geom", None)
            r.pop("_name", None)
        all_rows.extend(rows)

    for entry in _source_entries(repo_root, sources, params):
        source_features.append(entry)

    k_results = {}
    for k in demand_cfg["k_candidates"]:
        pts_m = [global_proj.to_m(lon, lat) for lon, lat in demand_points]
        clusters = kmeans_candidates(pts_m, demand_weights, k)
        k_results[str(k)] = [{
            "cluster": i,
            "centre_lon": round(global_proj.to_deg(*c["centre"])[0], 6),
            "centre_lat": round(global_proj.to_deg(*c["centre"])[1], 6),
            "weighted_demand": c["weight"], "member_streets": c["members"],
        } for i, c in enumerate(clusters)]

    _write_outputs(repo_root, trim_cfg, demand_cfg, taxi_cfg, params,
                   candidate_features, source_features, excluded_features,
                   sparse_features, tier_c_features, question_features,
                   building_layers, all_rows, diff, k_results, owner_limit_meta, notes)

    a = sum(d["streets_tier_a"] for d in diff.values())
    b = sum(d["streets_tier_b"] for d in diff.values())
    cc = sum(d["streets_tier_c"] for d in diff.values())
    print(f"streets: A={a} B={b} C={cc} | k-candidates: {list(k_results)}")
    for key, v in diff.items():
        print(f"  {key}: {v['source_area_km2']}->{v['candidate_area_km2']} km2 "
              f"(-{v['reduction_pct']}%) A/B/C={v['streets_tier_a']}/{v['streets_tier_b']}"
              f"/{v['streets_tier_c']} addr={v['addresses_inside']} "
              f"excl_out={v['excluded_outbuildings']} excl_nonres={v['excluded_nonresidential']}")
    return 0


def _load_json(path):
    import json
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _source_entries(repo_root, sources, params):
    from bender_zones.service_area import load_service_area
    sa = load_service_area(repo_root / "config" / "service-area.yml")
    out = []
    for entry in sa.allowed:
        rel = entry.osm_id
        if rel not in sources:
            continue
        src = sources[rel]
        out.append(_feature(_out(src["boundary_m"], src["proj"], params), {
            "key": entry.key, "display_ru": entry.display_ru,
            "kind": "source_osm_boundary", "osm_type": "relation", "osm_id": rel,
            "area_km2": round(area_m2(src["boundary_m"]) / 1e6, 4),
            "note": "Исходная административная граница OSM. Не изменялась.",
        }))
    return sorted(out, key=lambda f: f["properties"]["osm_id"])


def _collect_excluded(region_m, candidate_m, feats, params, territory):
    out = []
    leftover = region_m.difference(candidate_m)
    if leftover.is_empty:
        return out, leftover
    explained = []
    for poly, tags in feats.landuse:
        piece = poly.intersection(leftover)
        if piece.is_empty or area_m2(piece) < params.min_excluded_area_m2:
            continue
        explained.append(piece)
        out.append({"geom": piece, "reason": exclusion_reason_for_tags(tags),
                    "name": tags.get("name"), "territory": territory,
                    "landuse": tags.get("landuse") or tags.get("natural")
                    or tags.get("leisure")})
    remainder = leftover.difference(unary_union(explained)) if explained else leftover
    for comp in polygon_components(remainder):
        if area_m2(comp) >= params.min_empty_land_area_m2:
            out.append({"geom": comp, "reason": EXCL_EMPTY, "name": None,
                        "territory": territory, "landuse": None})
    return out, leftover


def _apply_owner_limits(candidate_m, streets, limits, proj):
    questions, applied, meta = [], False, {}
    left_name = limits.get("left_limit_street")
    other_names = list(limits.get("limit_streets", []))
    other_lines = [ln for ln in (_street_line(streets, n) for n in other_names)
                   if ln is not None]

    if left_name:
        line = _street_line(streets, left_name)
        if line is None:
            questions.append(_question(proj, candidate_m,
                                       f"Улица «{left_name}» не найдена — предел не применён.",
                                       kind="unresolved"))
        else:
            keep_point = (unary_union(other_lines).centroid if other_lines
                          else candidate_m.centroid)
            rule = ("сторона, на которой лежат другие названные владельцем предельные "
                    "улицы (Мунтяна, Лесовая, Первомайская)")
            clipped, applied = clip_to_side(candidate_m, line, keep_point)
            if applied:
                candidate_m = clipped
            line_deg = to_degrees(line, proj)
            meta = {"left_limit_street": left_name, "applied": applied,
                    "keep_rule": rule, "kept_side_sign": side_of_line(line, keep_point),
                    "line_lonlat": [[round(x, 6), round(y, 6)] for x, y in line_deg.coords]}
            questions.append(_question(
                proj, line,
                f"«Левее» улицы «{left_name}» невозможно свести к стороне света: улица "
                "идёт с юго-запада на северо-восток, а названные владельцем предельные "
                f"улицы Мунтяна и Лесовая лежат западнее неё. Оставлена {rule}"
                f"{'; отсечение применено' if applied else '; отсечение НЕ применено'}. "
                "Подтвердите сторону.",
                kind="interpretation" if applied else "unresolved"))
            questions.append(_feature(line_deg, {
                "layer": "protyagailovka_boundary_questions", "kind": "limit_street",
                "street": left_name, "role": "left_limit",
                "question": "Левый предел по указанию владельца."}))

    for name in other_names:
        line = _street_line(streets, name)
        if line is None:
            questions.append(_question(proj, candidate_m,
                                       f"Предельная улица «{name}» не найдена в OSM.",
                                       kind="unresolved"))
            continue
        questions.append(_feature(to_degrees(line, proj), {
            "layer": "protyagailovka_boundary_questions", "kind": "limit_street",
            "street": name, "role": "side_limit",
            "question": (f"Улица «{name}» названа владельцем как предел. Сторона "
                         "(«с одной стороны» / «с другой стороны») не задана однозначно.")}))
    return candidate_m, applied, questions, meta


def _question(proj, geom_m, text, kind="question"):
    geom = geom_m.centroid if geom_m.geom_type != "Point" else geom_m
    return _feature(to_degrees(geom, proj), {
        "layer": "protyagailovka_boundary_questions", "kind": kind, "question": text})


CSV_FIELDS = ["settlement", "street_ru", "osm_ids", "confirmed_addresses",
              "confirmed_residential_buildings", "probable_residential_buildings",
              "apartment_buildings", "nonresidential_buildings", "outbuildings",
              "abandoned_or_ruin", "official_web_evidence", "civic_or_commercial_pois",
              "connected_to_core", "distance_to_core_by_road_km", "demand_tier",
              "affects_zone_pricing", "service_status", "reason"]


def _write_outputs(repo_root, trim_cfg, demand_cfg, taxi_cfg, params,
                   candidate_features, source_features, excluded_features,
                   sparse_features, tier_c_features, question_features,
                   building_layers, all_rows, diff, k_results, owner_limit_meta, notes):
    data = repo_root / "docs" / "data"
    data.mkdir(parents=True, exist_ok=True)

    def fc(features):
        return {"type": "FeatureCollection", "features": features}

    candidate_features.sort(key=lambda f: f["properties"]["key"])
    excluded_features.sort(key=lambda f: (f["properties"]["territory"],
                                          f["properties"]["reason"],
                                          -f["properties"].get("area_m2", 0)))
    sparse_features.sort(key=lambda f: (f["properties"]["territory"],
                                        -f["properties"]["buildings"]))
    tier_c_features.sort(key=lambda f: (f["properties"]["settlement"],
                                        f["properties"]["street_ru"]))

    jsonutil.write_compact(data / "source-boundaries.geojson", fc(source_features))
    jsonutil.write_compact(data / "candidate-service-area.geojson", fc(candidate_features))
    jsonutil.write_compact(data / "excluded-large-areas.geojson", fc(excluded_features))
    jsonutil.write_compact(data / "sparse-building-review.geojson", fc(sparse_features))
    jsonutil.write_compact(data / "tier-c-manual-review.geojson", fc(tier_c_features))
    jsonutil.write(data / "boundary-questions.geojson", fc(question_features))

    building_features = []
    for key, inside, pts in sorted(building_layers, key=lambda x: (x[0], not x[1])):
        if pts:
            building_features.append({
                "type": "Feature",
                "properties": {"territory": key, "inside_candidate": inside,
                               "count": len(pts)},
                "geometry": {"type": "MultiPoint",
                             "coordinates": [[round(a, 5), round(b, 5)] for a, b in pts]}})
    jsonutil.write_compact(data / "buildings.geojson", fc(building_features))

    all_rows.sort(key=lambda r: (r["settlement"], r["street_ru"]))
    with open(data / "street-demand-audit.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS, lineterminator="\n")
        w.writeheader()
        for r in all_rows:
            w.writerow({k: r[k] for k in CSV_FIELDS})

    generated = _utc_now_iso()
    fringe = [r for r in all_rows if r["demand_tier"] == "C" and not r["connected_to_core"]]
    thin = [r for r in all_rows
            if 1 <= (r["confirmed_residential_buildings"]
                     + r["probable_residential_buildings"]) <= 2]

    summary = {
        "schema": "bender-demand-summary/4",
        "generated_at": generated,
        "warning_ru": WARNING_RU,
        "zones_created": False,
        "tariffs_created": False,
        "routing_graph_created": False,
        "direct_integration": False,
        "taxi_calibration_supplied": bool(taxi_cfg.get("calibration_supplied")),
        "streets_by_tier": {
            "A": sum(1 for r in all_rows if r["demand_tier"] == "A"),
            "B": sum(1 for r in all_rows if r["demand_tier"] == "B"),
            "C": sum(1 for r in all_rows if r["demand_tier"] == "C"),
        },
        "streets_by_tier_per_settlement": {
            k: {"A": v["streets_tier_a"], "B": v["streets_tier_b"],
                "C": v["streets_tier_c"]} for k, v in diff.items()},
        "addresses_included": sum(v["addresses_inside"] for v in diff.values()),
        "residential_customers": sum(v["residential_customers"] for v in diff.values()),
        "excluded_outbuildings": sum(v["excluded_outbuildings"] for v in diff.values()),
        "excluded_nonresidential": sum(v["excluded_nonresidential"] for v in diff.values()),
        "excluded_abandoned_or_ruin": sum(v["excluded_abandoned_or_ruin"]
                                          for v in diff.values()),
        "excluded_construction": sum(v["excluded_construction"] for v in diff.values()),
        "unknown_buildings": sum(v["unknown_buildings"] for v in diff.values()),
        "isolated_fringe_streets": [
            {"settlement": r["settlement"], "street_ru": r["street_ru"],
             "reason": r["reason"]} for r in fringe],
        "streets_with_1_2_probable_residences": [
            {"settlement": r["settlement"], "street_ru": r["street_ru"],
             "demand_tier": r["demand_tier"],
             "residences": r["confirmed_residential_buildings"]
             + r["probable_residential_buildings"]} for r in thin],
        "territories": diff,
    }
    jsonutil.write(data / "demand-summary.json", summary)

    k_doc = {
        "schema": "bender-k-candidates/4",
        "generated_at": generated,
        "status": "prepared_not_selected",
        "winner": None,
        "blocked_on": ["local routing", "taxi tariffs"],
        "taxi_calibration": taxi_cfg.get("taxi_calibration"),
        "taxi_calibration_supplied": bool(taxi_cfg.get("calibration_supplied")),
        "note": ("K=4 и K=5 подготовлены как варианты. Победитель не выбран: "
                 "нужны локальная маршрутизация и реальные тарифы такси."),
        "candidates": k_results,
    }
    jsonutil.write(data / "k-candidates.json", k_doc)
    k_feats = []
    for k, clusters in k_results.items():
        for c in clusters:
            k_feats.append({"type": "Feature",
                            "properties": {"k": int(k), "cluster": c["cluster"],
                                           "weighted_demand": c["weighted_demand"],
                                           "member_streets": c["member_streets"],
                                           "status": "prepared_not_selected"},
                            "geometry": {"type": "Point",
                                         "coordinates": [c["centre_lon"], c["centre_lat"]]}})
    jsonutil.write(data / "k-candidates.geojson", fc(k_feats))

    diff_doc = {
        "schema": "bender-service-area-diff/4",
        "generated_at": generated, "zones_created": False, "routing_created": False,
        "merged_production_polygon": False, "warning_ru": WARNING_RU,
        "basis": "tier_a_b_residential_demand", "territories": diff,
        "totals": {
            "territories": len(diff),
            "source_area_km2": round(sum(v["source_area_km2"] for v in diff.values()), 4),
            "candidate_area_km2": round(sum(v["candidate_area_km2"]
                                            for v in diff.values()), 4),
            "buildings_included": sum(v["buildings_included"] for v in diff.values()),
            "buildings_excluded": sum(v["buildings_excluded"] for v in diff.values()),
            "addresses_inside": sum(v["addresses_inside"] for v in diff.values()),
        },
    }
    jsonutil.write(data / "service-area-diff.json", diff_doc)

    reports = repo_root / "reports" / "stage-04"
    reports.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "bender-residential-demand-audit/4",
        "generated_at": generated,
        "supersedes": "reports/stage-03/service-area-trimming.json (candidate basis)",
        "zones_created": False, "tariffs_created": False,
        "routing_graph_created": False, "direct_integration": False,
        "osm_boundaries_modified": False,
        "building_classification": {
            "note": ("Every building=* object is classified; only confirmed/probable "
                     "residential may anchor geometry, and only confirmed residential "
                     "counts as a customer."),
            "never_anchors": sorted(["shed", "garage", "garages", "barn",
                                     "farm_auxiliary", "greenhouse", "warehouse",
                                     "industrial", "construction", "ruins",
                                     "abandoned:*", "disused:*"]),
        },
        "thresholds": demand_cfg["thresholds"],
        "external_evidence": demand_cfg["external_evidence"],
        "external_evidence_note": ("Validation metadata only. No scraping and no "
                                   "proprietary map coordinates were used; geometry "
                                   "comes from the local OSM extract."),
        "distance_note": ("distance_to_core_by_road_km is measured with an in-memory "
                          "Dijkstra over OSM street centrelines. No routing engine, no "
                          "OSRM graph and no routing artifact were created."),
        "summary": {k: summary[k] for k in (
            "streets_by_tier", "streets_by_tier_per_settlement", "addresses_included",
            "residential_customers", "excluded_outbuildings", "excluded_nonresidential",
            "excluded_abandoned_or_ruin", "excluded_construction", "unknown_buildings")},
        "isolated_fringe_streets": summary["isolated_fringe_streets"],
        "streets_with_1_2_probable_residences": summary["streets_with_1_2_probable_residences"],
        "territories": diff,
        "k_candidates": k_doc,
        "owner_limits": owner_limit_meta,
        "notes": notes,
        "tool_versions": tool_versions(),
        "limitations": [
            "Tier C never shapes candidate polygons, zone centres or standard tariffs; "
            "it is published as a manual-review layer only.",
            "Tier B is serviceable but carries low statistical weight (0.3); Tier A 1.0.",
            "building=yes without an address is weak evidence: it may shape a dense "
            "block but is never counted as one customer.",
            "K=4 and K=5 are PREPARED only. The winner cannot be chosen without local "
            "routing and real taxi tariffs, which are not part of this batch.",
            "Taxi calibration values are null placeholders; no tariff was computed.",
            "OSM building and address coverage is community-contributed and incomplete.",
        ],
    }
    jsonutil.write(reports / "residential-demand-audit.json", report)
    (reports / "residential-demand-audit.md").write_text(
        _render_md(report, summary), encoding="utf-8", newline="\n")


def _render_md(report, summary):
    t = summary["streets_by_tier"]
    lines = ["# Stage 04 — residential delivery-demand audit", "",
             f"- Generated (UTC): `{report['generated_at']}`",
             f"- zones: **{report['zones_created']}** · tariffs: "
             f"**{report['tariffs_created']}** · routing graph: "
             f"**{report['routing_graph_created']}** · Direct: "
             f"**{report['direct_integration']}**", "",
             "> " + WARNING_RU, "",
             "## Streets by demand tier", "",
             f"- **A (standard)**: {t['A']} · **B (low density)**: {t['B']} · "
             f"**C (manual/fringe)**: {t['C']}", "",
             "| Территория | A | B | C | адреса | Δплощадь |",
             "|---|---:|---:|---:|---:|---:|"]
    for key, v in report["territories"].items():
        lines.append(f"| {v['display_ru']} (`{key}`) | {v['streets_tier_a']} | "
                     f"{v['streets_tier_b']} | {v['streets_tier_c']} | "
                     f"{v['addresses_inside']} | {v['source_area_km2']} → "
                     f"{v['candidate_area_km2']} км² (−{v['reduction_pct']}%) |")
    s = report["summary"]
    lines += ["", "## Buildings excluded from demand", "",
              f"- outbuildings (сараи/гаражи/теплицы): **{s['excluded_outbuildings']}**",
              f"- non-residential (склады/промышленность/торговля): "
              f"**{s['excluded_nonresidential']}**",
              f"- abandoned/ruin: **{s['excluded_abandoned_or_ruin']}** · construction: "
              f"**{s['excluded_construction']}** · unknown: **{s['unknown_buildings']}**",
              f"- addresses included: **{s['addresses_included']}** · confirmed "
              f"residential customers: **{s['residential_customers']}**", "",
              "## Isolated fringe streets (Tier C, not connected to core)", ""]
    fringe = report["isolated_fringe_streets"]
    lines += [f"- {r['settlement']}: {r['street_ru']} — `{r['reason']}`"
              for r in fringe[:40]] or ["- нет"]
    if len(fringe) > 40:
        lines += [f"- … и ещё {len(fringe) - 40}"]
    lines += ["", "## Streets with only 1-2 probable residences", ""]
    thin = report["streets_with_1_2_probable_residences"]
    lines += [f"- {r['settlement']}: {r['street_ru']} — {r['residences']} "
              f"(tier {r['demand_tier']})" for r in thin[:40]] or ["- нет"]
    if len(thin) > 40:
        lines += [f"- … и ещё {len(thin) - 40}"]
    lines += ["", "## K=4 / K=5 (prepared, NOT selected)", "",
              f"- status: `{report['k_candidates']['status']}` · winner: "
              f"`{report['k_candidates']['winner']}`",
              f"- blocked on: {', '.join(report['k_candidates']['blocked_on'])}",
              f"- taxi calibration supplied: "
              f"`{report['k_candidates']['taxi_calibration_supplied']}`", ""]
    for k, clusters in report["k_candidates"]["candidates"].items():
        lines += [f"### K={k}", ""]
        for c in clusters:
            lines += [f"- cluster {c['cluster']}: центр {c['centre_lat']}/"
                      f"{c['centre_lon']}, вес {c['weighted_demand']}, "
                      f"улиц {c['member_streets']}"]
        lines += [""]
    lines += ["## Limitations", ""] + [f"- {x}" for x in report["limitations"]] + [""]
    return "\n".join(lines)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--pbf", default=None)
    p.add_argument("--source", default="osm_moldova")
    p.add_argument("--repo-root", default=".")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root)
    sources = load_sources(repo_root / "config" / "sources.yml")
    pbf = repo_root / (args.pbf or sources[args.source].destination)
    if not pbf.is_file():
        print(f"error: PBF not found: {pbf}", file=sys.stderr)
        return 2
    return build(pbf, repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
