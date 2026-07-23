#!/usr/bin/env python
"""Stage 05 — routing-based candidate delivery zones for K=4 and K=5.

Uses the local OSM road graph and ACTUAL travel distance/time (never
straight-line distance, never polygon area). Restaurant-origin demand is modelled
with representative origin clusters (central Bender 0.85 / BAM + other outer
Bender 0.15) discovered from the local extract — no Nominatim, no Overpass.

Tier C fringe streets are NOT serviceable: they are excluded from the service
area, from zone centres, from clustering and from every percentile.

Produces:
* docs/data/restaurant-origins.geojson   representative origins + how chosen
* docs/data/zone-candidates.geojson      K=4 and K=5 zone polygons + metrics
* docs/data/zone-metrics.json            full comparison table
* reports/stage-05/zoning-candidates.{json,md}

No monetary prices, no tariffs (taxi calibration stays null), no Direct
integration, and neither K is chosen automatically.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import osmium
import yaml
from shapely.geometry import Point, mapping, shape
from shapely.ops import unary_union

from bender_zones import jsonutil
from bender_zones.config import load_audit, load_sources
from bender_zones.demand import (
    CONFIRMED_RESIDENTIAL,
    classify_building,
    is_serviceable,
    tier_weight,
)
from bender_zones.extract import extract_boundary, osmium_tool_path
from bender_zones.routing import (
    build_graph,
    dijkstra,
    snap_nodes,
    weighted_percentile,
)
from bender_zones.service_trim import (
    area_m2,
    local_projection,
    polygon_components,
    to_degrees,
    to_metres,
)
from bender_zones.zoning import (
    assign_all_nodes,
    build_zones,
    is_uncertain,
    polsby_popper,
    zone_graph_components,
)

FOOD_AMENITIES = {"restaurant", "fast_food", "cafe", "food_court", "bar", "pub",
                  "ice_cream"}
NOTE_RU = ("Кандидаты зон построены по реальному дорожному времени. Победитель "
           "K не выбран, денежные тарифы не назначались.")


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _round(obj, nd=5):
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, (list, tuple)):
        return [_round(x, nd) for x in obj]
    if isinstance(obj, dict):
        return {k: _round(v, nd) for k, v in obj.items()}
    return obj


def _feature(geom_deg, props):
    return {"type": "Feature", "properties": props,
            "geometry": _round(mapping(geom_deg))}


def _build_routing_extract(pbf: Path, boundaries_deg, workdir: Path, pad_deg: float):
    """Clip one routing area covering all territories so roads stay connected."""
    union = unary_union(boundaries_deg).buffer(pad_deg)
    poly_path = workdir / "routing-area.geojson"
    jsonutil.write_compact(poly_path, {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": mapping(union)}]})
    out = workdir / "routing-area.osm.pbf"
    exe = osmium_tool_path()
    proc = subprocess.run([exe, "extract", "--polygon", str(poly_path),
                           "--strategy=complete_ways", str(pbf), "-o", str(out),
                           "--overwrite"], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"osmium extract failed: {proc.stderr.strip()}")
    return out


def _load_drivable_ways(routing_pbf: Path, proj, drivable):
    ways = []
    drivable = set(drivable)
    for obj in osmium.FileProcessor(str(routing_pbf)).with_locations():
        if obj.type_str() != "w":
            continue
        tags = {k: v for k, v in obj.tags}
        if tags.get("highway") not in drivable:
            continue
        if tags.get("access") in ("private", "no"):
            continue
        coords = []
        ok = True
        for nd in obj.nodes:
            if not nd.location.valid():
                ok = False
                break
            coords.append(proj.to_m(nd.lon, nd.lat))
        if ok and len(coords) >= 2:
            ways.append((coords, tags))
    return ways


def _load_food_pois(city_pbf: Path, proj):
    pts = []
    for obj in osmium.FileProcessor(str(city_pbf)).with_locations():
        tags = {k: v for k, v in obj.tags}
        amenity = tags.get("amenity")
        takeaway = tags.get("takeaway") in ("yes", "only") or tags.get("delivery") == "yes"
        if amenity not in FOOD_AMENITIES and not (takeaway and amenity):
            continue
        if obj.type_str() == "n":
            pts.append((Point(*proj.to_m(obj.lon, obj.lat)), tags.get("name"), amenity))
        elif obj.type_str() == "w":
            cs = [proj.to_m(nd.lon, nd.lat) for nd in obj.nodes if nd.location.valid()]
            if cs:
                pts.append((Point(sum(c[0] for c in cs) / len(cs),
                                  sum(c[1] for c in cs) / len(cs)),
                            tags.get("name"), amenity))
    return pts


def _cluster(points, radius_m):
    """Single-link clustering; returns index groups sorted largest-first."""
    remaining = list(range(len(points)))
    groups = []
    while remaining:
        seed = remaining.pop(0)
        comp, frontier = [seed], [seed]
        while frontier:
            cur = frontier.pop()
            for i in list(remaining):
                if points[cur].distance(points[i]) <= radius_m:
                    remaining.remove(i)
                    comp.append(i)
                    frontier.append(i)
        groups.append(sorted(comp))
    groups.sort(key=lambda g: (-len(g), g[0]))
    return groups


def build(pbf: Path, repo_root: Path) -> int:
    trim_cfg = yaml.safe_load(
        (repo_root / "config/service-trim.yml").read_text(encoding="utf-8"))
    zcfg = yaml.safe_load((repo_root / "config/zoning.yml").read_text(encoding="utf-8"))
    dcfg = yaml.safe_load((repo_root / "config/demand.yml").read_text(encoding="utf-8"))
    taxi = yaml.safe_load(
        (repo_root / "config/taxi-calibration.yml").read_text(encoding="utf-8"))
    audit_cfg = load_audit(repo_root / "config/audit.yml")
    workdir = repo_root / audit_cfg.workdir

    territories = trim_cfg["territories"]
    relations = sorted({t["source_relation"] for t in territories})

    boundaries_deg, city_pbfs = [], {}
    for rel in relations:
        res = extract_boundary(pbf, rel, workdir, strategy=audit_cfg.osmium_strategy)
        gj = json.loads(Path(res.boundary_geojson).read_text(encoding="utf-8"))
        geom = next((shape(f["geometry"]) for f in gj["features"]
                     if f["geometry"]["type"] in ("Polygon", "MultiPolygon")), None)
        boundaries_deg.append(geom)
        city_pbfs[rel] = res.city_pbf

    centre = unary_union(boundaries_deg).centroid
    proj = local_projection(centre.y, centre.x)

    # --- service area (Tier A+B only, from Stage 04) ---
    cand = json.loads((repo_root / "docs/data/candidate-service-area.geojson")
                      .read_text(encoding="utf-8"))
    service_m = {f["properties"]["key"]: to_metres(shape(f["geometry"]), proj)
                 for f in cand["features"]}
    service_all = unary_union(list(service_m.values()))

    # --- road graph ---
    pad_deg = zcfg["routing"]["buffer_around_boundaries_m"] / 111320.0
    routing_pbf = _build_routing_extract(pbf, boundaries_deg, workdir, pad_deg)
    ways = _load_drivable_ways(routing_pbf, proj, zcfg["drivable_highways"])
    graph = build_graph(ways, zcfg["speeds_kmh"], zcfg["default_speed_kmh"],
                        snap_m=zcfg["routing"]["node_snap_m"])
    print(f"road graph: {graph.node_count} nodes, {graph.edge_count} edges")

    # --- street tiers from the Stage-04 audit ---
    tier_by_osm_id, street_by_osm_id = {}, {}
    for row in csv.DictReader((repo_root / "docs/data/street-demand-audit.csv")
                              .read_text(encoding="utf-8").splitlines()):
        for oid in row["osm_ids"].split(";"):
            if oid:
                tier_by_osm_id[int(oid)] = row["demand_tier"]
                street_by_osm_id[int(oid)] = (row["settlement"], row["street_ru"])

    # --- customers + serviceable streets ---
    customers, serviceable_streets = [], []
    village_food = {}
    bender_rel = next(t["source_relation"] for t in territories
                      if t["key"] == "bender_core")
    for rel, city in city_pbfs.items():
        for obj in osmium.FileProcessor(str(city)).with_locations():
            tags = {k: v for k, v in obj.tags}
            kind = obj.type_str()
            if kind == "w" and tags.get("highway") and tags.get("name"):
                tier = tier_by_osm_id.get(obj.id)
                if tier and is_serviceable(tier):
                    cs = [proj.to_m(nd.lon, nd.lat) for nd in obj.nodes
                          if nd.location.valid()]
                    if len(cs) >= 2:
                        from shapely.geometry import LineString
                        serviceable_streets.append(
                            (LineString(cs), street_by_osm_id[obj.id], tier))
                continue
            if tags.get("building") is None:
                continue
            if classify_building(tags) != CONFIRMED_RESIDENTIAL:
                continue
            if kind == "n":
                pt = Point(*proj.to_m(obj.lon, obj.lat))
            elif kind == "w":
                cs = [proj.to_m(nd.lon, nd.lat) for nd in obj.nodes
                      if nd.location.valid()]
                if len(cs) < 4:
                    continue
                from shapely.geometry import Polygon as _P
                try:
                    pt = _P(cs).centroid
                except Exception:
                    continue
            else:
                continue
            if service_all.covers(pt):
                customers.append(pt)
        if rel != bender_rel:
            village_food[rel] = len(_load_food_pois(city, proj))
    print(f"customers (confirmed residential inside service area): {len(customers)}")

    # --- attribute each customer to a serviceable street (for splits/weights) ---
    from shapely.strtree import STRtree
    street_geoms = [s[0] for s in serviceable_streets]
    stree = STRtree(street_geoms) if street_geoms else None
    cust_street, cust_weight = [], []
    for pt in customers:
        chosen, w = None, 1.0
        if stree is not None:
            idx = stree.nearest(pt)
            if idx is not None:
                i = int(idx)
                if street_geoms[i].distance(pt) <= 100.0:
                    chosen = serviceable_streets[i][1]
                    w = tier_weight(serviceable_streets[i][2])
        cust_street.append(chosen)
        cust_weight.append(w)

    # --- restaurant origins ---
    origins, origin_doc = _build_origins(city_pbfs[bender_rel], proj, dcfg, village_food)

    # --- snap to graph ---
    snap_r = zcfg["routing"]["snap_radius_m"]
    cust_nodes = snap_nodes(customers, graph, snap_r)
    origin_nodes = snap_nodes([o["point"] for o in origins], graph, snap_r)
    for o, n in zip(origins, origin_nodes, strict=False):
        o["node"] = n
    origins = [o for o in origins if o["node"] is not None]
    if not origins:
        print("error: no restaurant origin could be snapped to the road graph",
              file=sys.stderr)
        return 2

    exceptions_unsnapped = sum(1 for n in cust_nodes if n is None)

    # --- travel distance/time from each origin ---
    origin_tables = {o["key"]: dijkstra(graph, [o["node"]], minimise="time")
                     for o in origins}

    routable_idx = [i for i, n in enumerate(cust_nodes)
                    if n is not None and any(n in t for t in origin_tables.values())]
    exceptions_unreachable = sum(
        1 for i, n in enumerate(cust_nodes)
        if n is not None and not any(n in t for t in origin_tables.values()))

    # --- K candidates ---
    results = {}
    zone_features = []
    for k in zcfg["k_values"]:
        nodes = [cust_nodes[i] for i in routable_idx]
        weights = [cust_weight[i] for i in routable_idx]
        assignment, seeds = build_zones(graph, nodes, weights, k,
                                        iterations=zcfg["zoning"]["iterations"])
        node_zone = assign_all_nodes(graph, seeds)
        results[str(k)] = _zone_metrics(
            k, routable_idx, customers, cust_street, cust_weight, cust_nodes,
            assignment, seeds, graph, origins, origin_tables, zcfg, proj,
            service_all, zone_features,
            exceptions_unsnapped + exceptions_unreachable, node_zone)
        print(f"  K={k}: zones={len(results[str(k)]['zones'])} "
              f"split_streets={results[str(k)]['split_streets']} "
              f"uncertain={len(results[str(k)]['uncertain_streets'])}")

    _write_outputs(repo_root, origins, origin_doc, zone_features, results, taxi,
                   zcfg, graph, len(customers),
                   exceptions_unsnapped, exceptions_unreachable, proj)
    return 0


def _build_origins(bender_pbf, proj, dcfg, village_food):
    """Representative restaurant origins, documented, never from villages."""
    cfg = dcfg.get("restaurant_origins", {})
    radius = float(cfg.get("cluster_radius_m", 600))
    min_outer = int(cfg.get("min_outer_cluster_pois", 3))
    central_w = float(cfg.get("central_weight", 0.85))
    outer_w = float(cfg.get("outer_total_weight", 0.15))

    pois = _load_food_pois(bender_pbf, proj)
    pts = [p[0] for p in pois]
    groups = _cluster(pts, radius)
    if not groups:
        return [], {"error": "no food-service POIs found"}

    def centroid(idxs):
        return Point(sum(pts[i].x for i in idxs) / len(idxs),
                     sum(pts[i].y for i in idxs) / len(idxs))

    central = groups[0]
    outer = [g for g in groups[1:] if len(g) >= min_outer]
    origins = [{"key": "central_bender_origin", "role": "central",
                "point": centroid(central), "weight": central_w,
                "poi_count": len(central)}]
    total_outer = sum(len(g) for g in outer) or 1
    for i, g in enumerate(outer):
        origins.append({"key": f"bam_outer_origin_{i + 1}", "role": "bam_outer",
                        "point": centroid(g),
                        "weight": round(outer_w * len(g) / total_outer, 6),
                        "poi_count": len(g)})
    doc = {
        "method": ("Food-service POIs (amenity=restaurant/fast_food/cafe/bar/pub "
                   "plus takeaway/delivery venues) were read from the LOCAL Bender "
                   "extract and single-link clustered at "
                   f"{radius:.0f} m. The largest cluster is the central origin; "
                   f"remaining clusters with >= {min_outer} POIs represent BAM and "
                   "other outer Bender districts."),
        "why_representative": ("OSM venue coverage is incomplete, so clusters are used "
                              "as representative origins instead of treating each POI "
                              "as complete truth."),
        "central_weight": central_w, "outer_total_weight": outer_w,
        "total_food_pois_bender": len(pois),
        "central_cluster_pois": len(central),
        "outer_clusters": [len(g) for g in outer],
        "villages_excluded": ("Villages are NOT restaurant origins: too little actual "
                              "restaurant evidence in the local extract."),
        "village_food_poi_counts": {str(k): v for k, v in village_food.items()},
        "bam_landmark_note": ("BAM has no place=* object in OSM; the northern outer "
                              "cluster nearest 'Бамовское озеро' represents it. "
                              "Confirm with the owner."),
        "source": "local Geofabrik Moldova extract (no Nominatim, no Overpass)",
    }
    return origins, doc


def _zone_metrics(k, routable_idx, customers, cust_street, cust_weight, cust_nodes,
                  assignment, seeds, graph, origins, origin_tables, zcfg, proj,
                  service_all, zone_features, base_exceptions, node_zone):
    margin = zcfg["zoning"]["uncertain_margin_pct"]
    outlier_p = zcfg["zoning"]["outlier_percentile"]
    zbuf = zcfg["zoning"]["zone_buffer_m"]

    per_zone: dict = {}
    street_zones: dict = {}
    uncertain_streets = set()
    for i in routable_idx:
        node = cust_nodes[i]
        zone, best_t, second_t = assignment.get(node, (None, None, None))
        if zone is None:
            continue
        z = per_zone.setdefault(zone, {"idx": [], "pts": [], "w": 0.0})
        z["idx"].append(i)
        z["pts"].append(customers[i])
        z["w"] += cust_weight[i]
        street = cust_street[i]
        if street:
            street_zones.setdefault(street, set()).add(zone)
            if is_uncertain(best_t, second_t, margin):
                uncertain_streets.add(street)

    split_streets = sorted(s for s, zs in street_zones.items() if len(zs) > 1)
    for s in split_streets:
        uncertain_streets.add(s)

    zones_out = []
    for zone in sorted(per_zone):
        z = per_zone[zone]
        poly = unary_union([p.buffer(zbuf) for p in z["pts"]]).intersection(service_all)
        comps = polygon_components(poly)
        dist_vals, time_vals, pair_w = [], [], []
        by_origin = {}
        for o in origins:
            table = origin_tables[o["key"]]
            d_list, t_list, w_list = [], [], []
            for i in z["idx"]:
                entry = table.get(cust_nodes[i])
                if entry is None:
                    continue
                d_list.append(entry[1] / 1000.0)
                t_list.append(entry[2] / 60.0)
                w_list.append(cust_weight[i] * o["weight"])
            dist_vals += d_list
            time_vals += t_list
            pair_w += w_list
            by_origin[o["key"]] = {
                "role": o["role"], "origin_weight": o["weight"],
                "median_km": _r(weighted_percentile(d_list, w_list, 50)),
                "median_min": _r(weighted_percentile(t_list, w_list, 50)),
            }
        central = [v for v in by_origin.values() if v["role"] == "central"]
        bam = [v for v in by_origin.values() if v["role"] == "bam_outer"]
        zones_out.append({
            "zone": zone,
            "addresses": len(z["idx"]),
            "demand_weight": round(z["w"], 2),
            "distance_km": {"p50": _r(weighted_percentile(dist_vals, pair_w, 50)),
                            "p75": _r(weighted_percentile(dist_vals, pair_w, 75)),
                            "p90": _r(weighted_percentile(dist_vals, pair_w, 90))},
            "travel_time_min": {"p50": _r(weighted_percentile(time_vals, pair_w, 50)),
                                "p75": _r(weighted_percentile(time_vals, pair_w, 75)),
                                "p90": _r(weighted_percentile(time_vals, pair_w, 90))},
            "max_reasonable_route": {
                "distance_km": _r(weighted_percentile(dist_vals, pair_w, outlier_p)),
                "travel_time_min": _r(weighted_percentile(time_vals, pair_w, outlier_p)),
                "excludes_percentile_above": outlier_p},
            "compactness_polsby_popper": polsby_popper(poly),
            "polygon_components": len(comps),
            "graph_components": zone_graph_components(
                graph, [n for n, z in node_zone.items() if z == zone]),
            "graph_connected": zone_graph_components(
                graph, [n for n, z in node_zone.items() if z == zone]) == 1,
            "origin_comparison": {
                "central_median_min": _r(central[0]["median_min"]) if central else None,
                "bam_outer_median_min": _r(
                    sum(v["median_min"] for v in bam if v["median_min"]) / len(bam))
                if bam and any(v["median_min"] for v in bam) else None,
            },
            "by_origin": by_origin,
        })
        if not poly.is_empty:
            zone_features.append(_feature(to_degrees(poly.simplify(3.0), proj), {
                "k": k, "zone": zone, "kind": "candidate_zone",
                "status": "prepared_not_selected",
                "addresses": len(z["idx"]), "demand_weight": round(z["w"], 2),
                "median_km": zones_out[-1]["distance_km"]["p50"],
                "median_min": zones_out[-1]["travel_time_min"]["p50"],
                "p90_min": zones_out[-1]["travel_time_min"]["p90"],
                "compactness": zones_out[-1]["compactness_polsby_popper"],
                "area_km2": round(area_m2(poly) / 1e6, 4),
            }))

    return {
        "k": k,
        "zones": zones_out,
        "connected_zones": sum(1 for z in zones_out if z["graph_connected"]),
        "split_streets": len(split_streets),
        "split_street_list": [f"{s[0]}: {s[1]}" for s in split_streets],
        "exceptions": base_exceptions,
        "uncertain_streets": sorted(f"{s[0]}: {s[1]}" for s in uncertain_streets),
        "seeds_lonlat": [[round(v, 6) for v in proj.to_deg(*graph.coords[s])]
                         for s in seeds if s in graph.coords],
    }


def _r(v, nd=2):
    return round(v, nd) if isinstance(v, (int, float)) else v


def _write_outputs(repo_root, origins, origin_doc, zone_features, results, taxi,
                   zcfg, graph, customer_count, unsnapped, unreachable, proj):
    data = repo_root / "docs/data"
    generated = _utc_now_iso()

    origin_feats = [_feature(to_degrees(o["point"], proj), {
        "key": o["key"], "role": o["role"], "weight": o["weight"],
        "poi_count": o["poi_count"],
        "note": "Представительный источник заказов (кластер заведений), не один POI.",
    }) for o in origins]
    jsonutil.write(data / "restaurant-origins.geojson",
                   {"type": "FeatureCollection", "features": origin_feats,
                    "selection": origin_doc})

    zone_features.sort(key=lambda f: (f["properties"]["k"], f["properties"]["zone"]))
    jsonutil.write_compact(data / "zone-candidates.geojson",
                           {"type": "FeatureCollection", "features": zone_features})

    metrics = {
        "schema": "bender-zone-candidates/5",
        "generated_at": generated,
        "status": "prepared_not_selected",
        "winner": None,
        "note": NOTE_RU,
        "prices_assigned": False,
        "tariffs_created": False,
        "direct_integration": False,
        "taxi_calibration": taxi.get("taxi_calibration"),
        "taxi_calibration_supplied": bool(taxi.get("calibration_supplied")),
        "method": {
            "distance_basis": "actual road travel distance and time (local OSM graph)",
            "not_used": ["straight-line distance", "polygon area"],
            "routing_engine": "none (in-memory Dijkstra; no OSRM/Valhalla/GraphHopper)",
            "road_graph": {"nodes": graph.node_count, "edges": graph.edge_count},
            "speeds_kmh": zcfg["speeds_kmh"],
            "tier_c": "excluded from service, centres, clustering and percentiles",
            "travel_time_basis": ("free-flow speeds only: no traffic, no turn or "
                                  "junction delay, no parking/handover time. Treat "
                                  "the reported minutes as LOWER BOUNDS, not "
                                  "promised delivery times."),
            "zone_connectivity": ("measured on the road graph (can a driver stay "
                                  "inside the zone on real roads); polygon parts are "
                                  "only a drawing artifact"),
        },
        "customers_considered": customer_count,
        "exceptions": {"unsnapped_to_road": unsnapped, "unreachable": unreachable},
        "origins": origin_doc,
        "candidates": results,
    }
    jsonutil.write(data / "zone-metrics.json", metrics)

    reports = repo_root / "reports/stage-05"
    reports.mkdir(parents=True, exist_ok=True)
    jsonutil.write(reports / "zoning-candidates.json", metrics)
    (reports / "zoning-candidates.md").write_text(_render_md(metrics),
                                                  encoding="utf-8", newline="\n")


def _render_md(m):
    lines = ["# Stage 05 — routing-based candidate zones (K=4 / K=5)", "",
             f"- Generated (UTC): `{m['generated_at']}`",
             f"- status: **{m['status']}** · winner: **{m['winner']}** · prices "
             f"assigned: **{m['prices_assigned']}**",
             f"- road graph: {m['method']['road_graph']['nodes']} nodes / "
             f"{m['method']['road_graph']['edges']} edges · routing engine: "
             f"`{m['method']['routing_engine']}`",
             f"- customers: {m['customers_considered']} · exceptions: "
             f"{m['exceptions']}", "", "> " + m["note"], "",
             "## Restaurant origins", "",
             f"- {m['origins']['method']}",
             f"- central weight **{m['origins']['central_weight']}**, outer total "
             f"**{m['origins']['outer_total_weight']}**",
             f"- Bender food POIs: {m['origins']['total_food_pois_bender']} "
             f"(central cluster {m['origins']['central_cluster_pois']}, outer "
             f"clusters {m['origins']['outer_clusters']})",
             f"- {m['origins']['villages_excluded']}",
             f"- {m['origins']['bam_landmark_note']}", ""]
    for k, res in m["candidates"].items():
        lines += [f"## K={k}", "",
                  f"- connected zones: {res['connected_zones']}/{len(res['zones'])} · "
                  f"split streets: {res['split_streets']} · exceptions: "
                  f"{res['exceptions']} · uncertain streets: "
                  f"{len(res['uncertain_streets'])}", "",
                  "| Зона | адресов | вес | км p50/p75/p90 | мин p50/p75/p90 | "
                  "макс.разумный | компактность | центр→ / БАМ→ |",
                  "|---|---:|---:|---|---|---|---:|---|"]
        for z in res["zones"]:
            d, t = z["distance_km"], z["travel_time_min"]
            oc = z["origin_comparison"]
            lines.append(
                f"| {z['zone']} | {z['addresses']} | {z['demand_weight']} | "
                f"{d['p50']}/{d['p75']}/{d['p90']} | {t['p50']}/{t['p75']}/{t['p90']} | "
                f"{z['max_reasonable_route']['travel_time_min']} мин | "
                f"{z['compactness_polsby_popper']} | "
                f"{oc['central_median_min']} / {oc['bam_outer_median_min']} мин |")
        lines += [""]
        if res["uncertain_streets"]:
            lines += ["Улицы с неуверенной привязкой к зоне:", ""]
            lines += [f"- {s}" for s in res["uncertain_streets"][:30]]
            if len(res["uncertain_streets"]) > 30:
                lines += [f"- … и ещё {len(res['uncertain_streets']) - 30}"]
            lines += [""]
    lines += ["## Оговорки", "",
              "- Время рассчитано по свободному потоку: без пробок, задержек на "
              "перекрёстках, парковки и передачи заказа. Это **нижняя граница**, а не "
              "обещанное время доставки.",
              "- Связность зоны измерена по дорожному графу; разбиение полигона на "
              "части — артефакт отрисовки.", "",
              "## Не сделано намеренно", "",
              "- Победитель K **не выбран** — нужны решения владельца и тарифы такси.",
              "- Денежные цены и тарифы **не назначались**; поля калибровки такси "
              f"остаются null (`supplied={m['taxi_calibration_supplied']}`).",
              "- Tier C (1-2 изолированных дома) — **не обслуживается**: исключён из "
              "зон, центров, кластеризации и перцентилей.",
              "- Интеграция с Direct не выполнялась.", ""]
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
    sources = load_sources(repo_root / "config/sources.yml")
    pbf = repo_root / (args.pbf or sources[args.source].destination)
    if not pbf.is_file():
        print(f"error: PBF not found: {pbf}", file=sys.stderr)
        return 2
    if osmium_tool_path() is None:
        print("error: osmium-tool not found", file=sys.stderr)
        return 2
    return build(pbf, repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
