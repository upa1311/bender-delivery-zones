#!/usr/bin/env python
"""Stage 08 (final) — real Северный footprint + per-address zone assignment.

Resolves Северный from the FULL Moldova PBF (routes run through Varnița; the
enclave lies outside the Bender clip), anchored on place=suburb node 5135654201.
This build:

* splits the Varnița admin claim (reference line) from the excluded Varnița
  village (grey no-delivery footprint), so the enclave is not greyed out;
* replaces the convex hull with a morphological residential footprint
  (buffered buildings + access streets + residential landuse, small-gap closing,
  isolated components dropped, disconnected components kept separate);
* gates the official-address numbering behind provenance (external reference,
  not import-verified); never synthesizes houses;
* routes EVERY included unit individually through OSRM (central + BAM) and
  assigns Zone 1-4 per unit, not by a footprint centroid.

Северный is a candidate_residential_footprint pending owner review. K=4 kept,
no prices, no Direct integration.
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
import yaml
from shapely.geometry import LineString, Point, Polygon, mapping, shape
from shapely.ops import unary_union

from bender_zones import jsonutil
from bender_zones.address import full_address_ru
from bender_zones.bands import (
    assign_band,
    band_edges,
    make_bins,
    optimal_bands,
    street_split_demand,
)
from bender_zones.demand import (
    CONFIRMED_RESIDENTIAL,
    PROBABLE_RESIDENTIAL,
    classify_building,
    is_apartment_building,
    tier_weight,
)
from bender_zones.extract import extract_boundary, osmium_tool_path
from bender_zones.normalize import normalize_text
from bender_zones.osrm import OsrmClient
from bender_zones.service_area import classify_road
from bender_zones.service_trim import (
    area_m2,
    local_projection,
    polygon_components,
    to_degrees,
)

ROUTES = [6572078, 6572079, 6572080, 6572081]
VARNITA_REL = 8289510
VARNITA_VILLAGE = (29.4759, 46.8651)
SEVERNY_NODE_ID = 5135654201
SEVERNY_SEED = (29.4744, 46.8817)
TRUNCATED_POINT = (29.480231, 46.854251)
FABRIC_RADIUS_M = 700.0
DISTRICT_RU = "микрорайон Северный"
# Footprint construction (metres).
BUILD_BUFFER_M = 22.0
STREET_BUFFER_M = 14.0
CLOSE_GAP_M = 25.0
MIN_COMPONENT_BUILDINGS = 5
MIN_COMPONENT_AREA_M2 = 3000.0
VICINITY_M = 70.0        # streets/landuse are clipped to this halo around buildings
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
    out = {"km": round(r["distance"] / 1000.0, 3), "min": round(r["duration"] / 60.0, 2)}
    if geometry:
        out["geometry"] = LineString(r["geometry"]["coordinates"])
    return out


def _table(client, origins, dests, chunk=200):
    n = len(origins)
    d_km = [[None] * len(dests) for _ in range(n)]
    d_min = [[None] * len(dests) for _ in range(n)]
    for s in range(0, len(dests), chunk):
        batch = dests[s:s + chunk]
        coords = ";".join(f"{lo:.6f},{la:.6f}" for lo, la in list(origins) + list(batch))
        src = ";".join(str(i) for i in range(n))
        dst = ";".join(str(n + i) for i in range(len(batch)))
        url = (f"{client.base_url}/table/v1/driving/{coords}?sources={src}"
               f"&destinations={dst}&annotations=distance,duration")
        with urllib.request.urlopen(url, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for i in range(n):
            for j in range(len(batch)):
                dd = data["distances"][i][j]
                tt = data["durations"][i][j]
                d_km[i][s + j] = round(dd / 1000.0, 3) if dd is not None else None
                d_min[i][s + j] = round(tt / 60.0, 2) if tt is not None else None
    return d_km, d_min


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
    proj = local_projection(46.88, 29.47)

    routes_pbf = interim / "severny-routes.osm.pbf"
    _osmium(["getid", "-r", "-t", str(pbf), *[f"r{r}" for r in ROUTES],
             "-o", str(routes_pbf), "--overwrite"])
    route_lines, route_coords, member_counts = _load_routes(routes_pbf)
    terminus = max(route_coords, key=lambda c: c[1])

    work_pbf = interim / "severny-work.osm.pbf"
    _osmium(["extract", "--bbox", "29.44,46.865,29.51,46.905", str(pbf),
             "-o", str(work_pbf), "--overwrite"])
    fabric = _load_fabric(work_pbf, proj)
    node = fabric["severny_node"] or SEVERNY_SEED

    varnita_admin = _varnita(repo_root)
    cand_fc = json.loads((repo_root / "docs/data/candidate-service-area.geojson")
                         .read_text("utf-8"))
    lipcani = next(shape(f["geometry"]) for f in cand_fc["features"]
                   if f["properties"]["key"] == "bender_lipcani")
    main_service = unary_union([shape(f["geometry"]) for f in cand_fc["features"]])

    # Varnița village = morphological footprint of the actual village fabric.
    village_deg, village_m = _village_footprint(fabric, VARNITA_VILLAGE, proj)

    # Candidate Северный buildings (exclude Липканы / already served).
    raw_cands, overlap = _select(fabric, node, lipcani, main_service)

    # Morphological footprint + component analysis.
    footprint_m, included, excluded_iso, comps, empty_pct = _footprint(
        raw_cands, fabric["streets"], fabric["landuse"], proj)
    footprint_deg = to_degrees(footprint_m.simplify(3), proj)
    overlap["final_included_buildings"] = len(included)
    overlap["excluded_isolated_buildings"] = len(excluded_iso)

    # Per-unit OSRM distances + zone assignment.
    units, unit_report = _per_unit(repo_root, included, client, village_deg)

    checks = _verify(footprint_deg, varnita_admin, village_m, main_service, node,
                     terminus, client, proj)
    scenarios = _scenarios(repo_root, units, unit_report)
    provenance = yaml.safe_load(
        (repo_root / "config/severny-address-provenance.yml").read_text("utf-8"))
    rejected = _rejected(interim)

    _write(repo_root, proj, footprint_deg, included, excluded_iso, comps, empty_pct,
           units, unit_report, overlap, route_lines, terminus, node, checks,
           scenarios, rejected, varnita_admin, village_deg, member_counts, provenance)
    print(f"footprint: {len(included)} included / {len(excluded_iso)} isolated / "
          f"{len(comps)} components / empty {empty_pct}% | units routed {len(units)} "
          f"| unreachable {unit_report['unreachable']}")
    print(f"scenario A zones: {unit_report['units_per_zone']} | through_varnita "
          f"{unit_report['units_requiring_varnita_transit']}")
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


def _load_fabric(work_pbf, proj):
    res, streets, landuse, severny_node = [], [], [], None
    for obj in osmium.FileProcessor(str(work_pbf)).with_locations():
        t = {k: v for k, v in obj.tags}
        kind = obj.type_str()
        if kind == "n":
            if obj.id == SEVERNY_NODE_ID:
                severny_node = (obj.lon, obj.lat)
            b = t.get("building")
            if b is not None and classify_building(t) in (CONFIRMED_RESIDENTIAL,
                                                          PROBABLE_RESIDENTIAL):
                res.append(_rec((obj.lon, obj.lat),
                                Point(*proj.to_m(obj.lon, obj.lat)).buffer(7), t))
            continue
        if kind == "w":
            cs = [(nd.lon, nd.lat) for nd in obj.nodes if nd.location.valid()]
            b = t.get("building")
            if b is not None and len(cs) >= 3 and classify_building(t) in (
                    CONFIRMED_RESIDENTIAL, PROBABLE_RESIDENTIAL):
                mp = Polygon([proj.to_m(x, y) for x, y in cs])
                if mp.is_valid and mp.area > 0:
                    cen = mp.centroid
                    res.append(_rec(proj.to_deg(cen.x, cen.y), mp, t))
            if t.get("highway") and t.get("name") and len(cs) >= 2:
                _c, is_addr, _ = classify_road(t)
                if is_addr:
                    streets.append((t["name"],
                                    LineString([proj.to_m(x, y) for x, y in cs])))
            if t.get("landuse") == "residential" and len(cs) >= 4:
                lp = Polygon([proj.to_m(x, y) for x, y in cs])
                if lp.is_valid and lp.area > 0:
                    landuse.append(lp)
    return {"res": res, "streets": streets, "landuse": landuse,
            "severny_node": severny_node}


def _rec(lonlat, geom_m, t):
    return {"lonlat": (round(lonlat[0], 6), round(lonlat[1], 6)), "geom_m": geom_m,
            "addr": bool(t.get("addr:housenumber")), "apt": is_apartment_building(t),
            "hn": t.get("addr:housenumber"), "street": t.get("addr:street"),
            "street_norm": normalize_text(t.get("addr:street") or "")}


def _select(fabric, node, lipcani, main_service):
    cands, in_service, lip_street, lip_poly = [], 0, 0, 0
    for r in fabric["res"]:
        if _dm(r["lonlat"], node) > FABRIC_RADIUS_M:
            continue
        p = Point(*r["lonlat"])
        if r["street_norm"] in LIPCANI_STREETS:
            lip_street += 1
        elif lipcani.covers(p):
            lip_poly += 1
        elif main_service.covers(p):
            in_service += 1
        else:
            cands.append(r)
    overlap = {
        "raw_candidate_buildings": len(cands),
        "candidate_buildings_already_in_existing_service_area": in_service,
        "candidate_addresses_already_classified_as_lipcani": lip_poly,
        "candidate_streets_matching_lipcani": lip_street,
        "new_severny_only_buildings": len(cands),
        "new_severny_only_addresses": sum(1 for c in cands if c["addr"]),
    }
    return cands, overlap


def _footprint(cands, streets, landuse, proj):
    """Morphological residential footprint: buffered buildings + access streets +
    residential landuse, close small gaps, drop isolated components."""
    if not cands:
        return Polygon(), [], [], [], 0.0
    build_buf = unary_union([c["geom_m"].buffer(BUILD_BUFFER_M) for c in cands])
    # Clip streets and landuse to the built-up vicinity: taking whole landuse
    # polygons or full street buffers would drag in fields and create long empty
    # corridors, which this footprint must not contain.
    vicinity = build_buf.buffer(VICINITY_M)
    parts = [build_buf]
    for _name, line in streets:
        if line.distance(build_buf) <= 40:
            seg = line.buffer(STREET_BUFFER_M).intersection(vicinity)
            if not seg.is_empty:
                parts.append(seg)
    for lu in landuse:
        piece = lu.intersection(vicinity)
        if not piece.is_empty:
            parts.append(piece)
    raw = unary_union(parts)
    closed = raw.buffer(CLOSE_GAP_M).buffer(-CLOSE_GAP_M)

    comps = polygon_components(closed)
    kept, comp_records = [], []
    for comp in comps:
        inside = [c for c in cands if comp.covers(c["geom_m"].representative_point())]
        keep = len(inside) >= MIN_COMPONENT_BUILDINGS and comp.area >= MIN_COMPONENT_AREA_M2
        comp_records.append({"buildings": len(inside),
                             "area_m2": round(area_m2(comp)), "kept": keep})
        if keep:
            kept.append((comp, inside))
    footprint = unary_union([c for c, _ in kept]) if kept else Polygon()
    included = [c for _comp, ins in kept for c in ins]
    included_ids = {id(c) for c in included}
    excluded_iso = [c for c in cands if id(c) not in included_ids]

    if footprint.is_empty:
        empty_pct = 0.0
    else:
        cover = unary_union([c["geom_m"].buffer(BUILD_BUFFER_M) for c in included]) \
            .intersection(footprint)
        empty_pct = round(100.0 * (footprint.area - cover.area) / footprint.area, 1)
    return footprint, included, excluded_iso, comp_records, empty_pct


def _village_footprint(fabric, village, proj):
    blds = [c for c in fabric["res"] if _dm(c["lonlat"], village) <= 700]
    if len(blds) < 3:
        pt = Point(*proj.to_m(*village))
        m = pt.buffer(300)
        return to_degrees(m, proj), m
    build_buf = unary_union([c["geom_m"].buffer(BUILD_BUFFER_M) for c in blds])
    m = build_buf.buffer(CLOSE_GAP_M).buffer(-CLOSE_GAP_M)
    return to_degrees(m.simplify(3), proj), m


def _varnita(repo_root):
    r = extract_boundary(repo_root / "data/raw/moldova-latest.osm.pbf", VARNITA_REL,
                         repo_root / "data/interim", strategy="smart")
    gj = json.loads(Path(r.boundary_geojson).read_text("utf-8"))
    return next(shape(f["geometry"]) for f in gj["features"]
                if f["geometry"]["type"] in ("Polygon", "MultiPolygon"))


def _origins(repo_root):
    fc = json.loads((repo_root / "docs/data/restaurant-origins.geojson")
                    .read_text("utf-8"))
    return {f["properties"]["role"]: tuple(f["geometry"]["coordinates"])
            for f in fc["features"] if f["properties"]["role"] in ("central", "bam")}


def _per_unit(repo_root, included, client, village_deg):
    edges = json.loads((repo_root / "docs/data/tariff-band-metrics.json")
                       .read_text("utf-8"))["candidates"]["4"]["upper_edges_km"]
    origins = _origins(repo_root)
    dests = [c["lonlat"] for c in included]
    ckm, cmin = _table(client, [origins["central"]], dests)
    bkm, bmin = _table(client, [origins["bam"]], dests)
    units = []
    for i, c in enumerate(included):
        ck, cm = ckm[0][i], cmin[0][i]
        bk, bm = bkm[0][i], bmin[0][i]
        reachable = ck is not None
        exp = round(0.85 * ck + 0.15 * bk, 3) if (ck is not None and bk is not None) \
            else (ck if ck is not None else None)
        exp_min = round(0.85 * cm + 0.15 * bm, 2) if (cm is not None and bm is not None) \
            else None
        route = _osrm(client, origins["central"], c["lonlat"], geometry=True) \
            if reachable else None
        through = bool(route and route["geometry"].intersects(village_deg))
        zone = (assign_band(exp, edges) + 1) if exp is not None else None
        weight = tier_weight("A") * (1.0 if c["addr"] else 0.5)
        units.append({
            "lon": c["lonlat"][0], "lat": c["lonlat"][1],
            "unit_type": "addressed_residential_building" if c["addr"]
            else "unaddressed_residential_building",
            "addressed": c["addr"], "apartment": c["apt"],
            "housenumber": c["hn"] or "", "street_ru": c["street"] or "",
            "central_km": ck, "central_min": cm, "bam_km": bk, "bam_min": bm,
            "expected_km": exp, "expected_min": exp_min,
            "assigned_zone": zone, "route_through_varnita_village": through,
            "reachable": reachable, "weight": round(weight, 3)})

    reachable_units = [u for u in units if u["reachable"] and u["expected_km"] is not None]
    per_zone, addr_zone = {}, {}
    for u in reachable_units:
        per_zone[u["assigned_zone"]] = per_zone.get(u["assigned_zone"], 0) + 1
        if u["addressed"]:
            addr_zone[u["assigned_zone"]] = addr_zone.get(u["assigned_zone"], 0) + 1
    kms = sorted(u["expected_km"] for u in reachable_units)

    def pct(p):
        return round(kms[min(int(len(kms) * p / 100), len(kms) - 1)], 3) if kms else None

    report = {
        "current_k4_edges_km": edges,
        "units_total": len(units),
        "units_reachable": len(reachable_units),
        "unreachable": sum(1 for u in units if not u["reachable"]),
        "units_requiring_varnita_transit": sum(
            1 for u in units if u["route_through_varnita_village"]),
        "units_per_zone": {z: per_zone.get(z, 0) for z in (1, 2, 3, 4)},
        "confirmed_addresses_per_zone": {z: addr_zone.get(z, 0) for z in (1, 2, 3, 4)},
        "expected_km": {"min": round(min(kms), 3) if kms else None, "p50": pct(50),
                        "p90": pct(90), "max": round(max(kms), 3) if kms else None},
    }
    return units, report


def _verify(footprint, varnita_admin, village_m, main_service, node, terminus,
            client, proj):
    reach = _osrm(client, (29.4828, 46.8242), node)
    village_deg_bounds = to_degrees(village_m, proj).bounds
    return {
        "settlement_ru": "Бендеры", "district_ru": "Северный",
        "terminus_lat": round(terminus[1], 5),
        "terminus_is_not_truncated_point": _dm(terminus, TRUNCATED_POINT) > 1000,
        "footprint_north_of_varnita_village": footprint.bounds[1] > village_deg_bounds[3],
        "footprint_intersects_varnita_village_fill":
            footprint.intersects(to_degrees(village_m, proj)),
        "footprint_disconnected_from_main_service":
            not footprint.intersects(main_service),
        "severny_node_inside_varnita_admin_relation":
            bool(varnita_admin.covers(Point(*node))),
        "admin_note": ("The OSM admin_level=8 Varnița relation (8289510) encloses "
                       "the Bender Северный enclave. It is published as a reference "
                       "LINE only. Exclusion is enforced against the derived Varnița "
                       "VILLAGE built-up footprint, which Северный does not touch."),
        "central_route_reaches_severny": reach is not None,
        "central_route_km": reach["km"] if reach else None,
    }


def _scenarios(repo_root, units, unit_report):
    edges = unit_report["current_k4_edges_km"]
    reachable = [u for u in units if u["reachable"] and u["expected_km"] is not None]
    beyond = [u for u in reachable if u["expected_km"] > edges[-1]]
    scen_a = {
        "rule": ("keep K=4 edges; assign each unit by its OWN OSRM distance; extend "
                 "Zone 4 only for units beyond the current maximum"),
        "uses_individual_distances": True,
        "units_per_zone": unit_report["units_per_zone"],
        "confirmed_addresses_per_zone": unit_report["confirmed_addresses_per_zone"],
        "units_beyond_current_max": len(beyond),
        "zone4_extended_to_km": round(max(u["expected_km"] for u in beyond), 3)
        if beyond else None,
    }
    scen_b = _scenario_b(repo_root, reachable)
    return {"current_k4_edges_km": edges, "scenario_A": scen_a, "scenario_B": scen_b}


def _scenario_b(repo_root, sev_units):
    """Full K=4 recompute with the SAME optimiser, weights and split penalty as
    Stage 06, using INDIVIDUAL Северный unit distances."""
    bcfg = yaml.safe_load((repo_root / "config/bands.yml").read_text("utf-8"))
    bw = float(bcfg["bands"]["bin_width_km"])
    min_share = float(bcfg["bands"]["min_weight_share"])
    max_share = float(bcfg["bands"]["max_weight_share"])
    penalty = float(bcfg["split_penalty"]["strengths"][
        bcfg["split_penalty"]["published_strength"]])

    existing = list(csv.DictReader((repo_root / "docs/data/delivery-units.csv")
                                   .read_text("utf-8").splitlines()))
    # Stage 06 publishes model A: unaddressed residential buildings carry ZERO
    # demand weight. Reusing the CSV tier*confidence weight would silently change
    # the optimiser's input and make the "changed units" number meaningless.
    model = yaml.safe_load(
        (repo_root / "config/bands.yml").read_text("utf-8"))["sensitivity"]
    unaddressed_factor = float(model["models"][model["published_model"]])

    def model_w(unit_type, weight):
        if unit_type == "unaddressed_residential_building":
            return weight * unaddressed_factor
        return weight

    rows = [{"km": float(r["expected_km"]),
             "w": model_w(r["unit_type"], float(r["weight"])),
             "band": int(r["band_k4"]), "unit_type": r["unit_type"],
             "settlement": r["settlement_ru"], "street": r["street_ru"]}
            for r in existing]
    base_n = len(rows)
    for u in sev_units:
        rows.append({"km": u["expected_km"],
                     "w": model_w(u["unit_type"], u["weight"]), "band": None,
                     "unit_type": u["unit_type"], "settlement": "Бендеры",
                     "street": u["street_ru"]})

    values = [r["km"] for r in rows]
    weights = [r["w"] for r in rows]
    bins = make_bins(values, weights, bw)
    idx_of = {}
    keys = sorted({int(math.floor(v / bw)) for v in values})
    for i, k in enumerate(keys):
        idx_of[k] = i
    street_units = {}
    for r in rows:
        if not r["street"]:
            continue
        aw = r["w"] if r["unit_type"] != "unaddressed_residential_building" else 0.0
        street_units.setdefault((r["settlement"], r["street"]), []).append(
            (idx_of[int(math.floor(r["km"] / bw))], aw))
    raw = street_split_demand(street_units, len(bins))
    total_addr = sum(w for u in street_units.values() for _b, w in u) or 1.0
    split_at = [x / total_addr for x in raw]
    bounds = optimal_bands(bins, 4, min_share, split_at=split_at,
                           split_penalty=penalty, max_weight_share=max_share)
    edges_b = band_edges(bins, bounds)
    changed = sum(1 for r in rows[:base_n]
                  if assign_band(r["km"], edges_b) + 1 != r["band"])

    # Control: the same recompute WITHOUT Северный. Any change here is optimiser
    # drift, not Северный's impact, so the two numbers must be read together.
    ctrl_rows = rows[:base_n]
    ctrl_bins = make_bins([r["km"] for r in ctrl_rows], [r["w"] for r in ctrl_rows], bw)
    ctrl_keys = sorted({int(math.floor(r["km"] / bw)) for r in ctrl_rows})
    ctrl_idx = {k: i for i, k in enumerate(ctrl_keys)}
    ctrl_streets = {}
    for r in ctrl_rows:
        if not r["street"]:
            continue
        aw = r["w"] if r["unit_type"] != "unaddressed_residential_building" else 0.0
        ctrl_streets.setdefault((r["settlement"], r["street"]), []).append(
            (ctrl_idx[int(math.floor(r["km"] / bw))], aw))
    ctrl_raw = street_split_demand(ctrl_streets, len(ctrl_bins))
    ctrl_total = sum(w for u in ctrl_streets.values() for _b, w in u) or 1.0
    ctrl_edges = band_edges(ctrl_bins, optimal_bands(
        ctrl_bins, 4, min_share, split_at=[x / ctrl_total for x in ctrl_raw],
        split_penalty=penalty, max_weight_share=max_share))
    ctrl_changed = sum(1 for r in ctrl_rows
                       if assign_band(r["km"], ctrl_edges) + 1 != r["band"])
    return {
        "note": "PREVIEW ONLY, not production. Recomputed with per-unit distances.",
        "optimiser": "same as Stage 06 (1-D weighted DP, balance bounds, "
                     f"split penalty '{bcfg['split_penalty']['published_strength']}')",
        "new_edges_km": [round(x, 3) for x in edges_b],
        "current_edges_km": json.loads(
            (repo_root / "docs/data/tariff-band-metrics.json").read_text("utf-8"))[
            "candidates"]["4"]["upper_edges_km"],
        "existing_delivery_units_total": base_n,
        "existing_addresses_total": sum(
            1 for r in rows[:base_n]
            if r["unit_type"] != "unaddressed_residential_building"),
        "existing_delivery_units_changing_zone": changed,
        "control_recompute_without_severny": {
            "edges_km": [round(x, 3) for x in ctrl_edges],
            "existing_units_changing_zone": ctrl_changed,
            "note": ("baseline drift of the optimiser without Северный; compare "
                     "with the figure above to isolate Северный's real impact")},
        "severny_delivery_units_added": len(sev_units),
        "severny_confirmed_addresses_added": sum(1 for u in sev_units if u["addressed"]),
    }


def _rejected(interim):
    p = interim / "rejected_lipcani_clusters.json"
    return json.loads(p.read_text("utf-8")) if p.is_file() else []


def _serviceable_in(repo_root, area_deg):
    return sum(1 for r in csv.DictReader(
        (repo_root / "docs/data/delivery-units.csv").read_text("utf-8").splitlines())
        if area_deg.covers(Point(float(r["lon"]), float(r["lat"]))))


def _write(repo_root, proj, footprint_deg, included, excluded_iso, comps, empty_pct,
           units, unit_report, overlap, route_lines, terminus, node, checks,
           scenarios, rejected, varnita_admin, village_deg, member_counts, provenance):
    data = repo_root / "docs/data"
    reports = repo_root / "reports/stage-08"
    generated = _now()
    streets = sorted({c["street"] for c in included if c["street"]})

    if provenance.get("verified_for_automatic_import"):
        address_ref = {"house_range_official": provenance["external_house_range_reference"],
                       "verified_for_automatic_import": True, "source": provenance["source"]}
        addr_key = "official_address_support"
    else:
        address_ref = {
            "external_house_range_reference": provenance["external_house_range_reference"],
            "external_example_house_numbers": provenance["external_example_house_numbers"],
            "verified_for_automatic_import": False,
            "source": provenance["source"],
            "note": ("External reference only, not a verified register. Missing "
                     "houses are NOT synthesized; do not import as addresses.")}
        addr_key = "external_address_reference"
    examples = [full_address_ru("Бендеры", DISTRICT_RU, "", hn)
                for hn in provenance["external_example_house_numbers"]]

    fp_props = {
        "status": "candidate_residential_footprint",
        "settlement_ru": "Бендеры", "district_ru": "Северный",
        "district_label_ru": DISTRICT_RU, "resolution": "owner_review_required",
        "footprint_method": ("morphological: residential/apartment building buffers "
                             f"({BUILD_BUFFER_M:.0f} m) + named access streets "
                             f"({STREET_BUFFER_M:.0f} m) + residential landuse, "
                             f"{CLOSE_GAP_M:.0f} m gap-closing, isolated components "
                             f"(<{MIN_COMPONENT_BUILDINGS} buildings) dropped, "
                             "disconnected components kept separate. No convex hull."),
        "raw_candidate_buildings": overlap["raw_candidate_buildings"],
        "final_included_buildings": len(included),
        "excluded_isolated_buildings": len(excluded_iso),
        "component_count": len([c for c in comps if c["kept"]]),
        "empty_area_pct": empty_pct,
        "confirmed_address_count": sum(1 for c in included if c["addr"]),
        "apartment_building_count": sum(1 for c in included if c["apt"]),
        "streets": streets,
        "north_of_varnita_village": checks["footprint_north_of_varnita_village"],
        "disconnected_from_main_service": checks["footprint_disconnected_from_main_service"],
        "example_addresses": examples,
        "note": (f"Реальный Северный (place=suburb node {SEVERNY_NODE_ID}). НЕ "
                 "объявлен добавленным — owner_review."),
    }
    jsonutil.write(data / "severny-service-area.geojson", {
        "type": "FeatureCollection",
        "resolution_status": "candidate_pending_owner_review", "chosen": False,
        "features": [{"type": "Feature", "properties": fp_props,
                      "geometry": mapping(footprint_deg)}]})

    # raw candidates (incl. excluded isolated) with an included flag
    included_ids = {id(c) for c in included}
    jsonutil.write_compact(data / "severny-candidate-buildings.geojson", {
        "type": "FeatureCollection", "features": sorted(
            [{"type": "Feature", "properties": {
                "included": id(c) in included_ids, "addressed": c["addr"],
                "apartment": c["apt"], "housenumber": c["hn"], "street": c["street"]},
              "geometry": {"type": "Point", "coordinates": list(c["lonlat"])}}
             for c in (included + excluded_iso)],
            key=lambda f: (f["geometry"]["coordinates"][1],
                           f["geometry"]["coordinates"][0]))})

    # per-unit CSV + geojson
    fields = ["lon", "lat", "unit_type", "addressed", "apartment", "housenumber",
              "street_ru", "central_km", "central_min", "bam_km", "bam_min",
              "expected_km", "expected_min", "assigned_zone",
              "route_through_varnita_village", "reachable", "weight"]
    with open(data / "severny-delivery-units.csv", "w", encoding="utf-8",
              newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for u in sorted(units, key=lambda x: (x["expected_km"] or 1e9, x["lon"])):
            w.writerow({k: u[k] for k in fields})
    jsonutil.write_compact(data / "severny-delivery-units.geojson", {
        "type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {k: u[k] for k in fields
                                               if k not in ("lon", "lat")},
             "geometry": {"type": "Point", "coordinates": [u["lon"], u["lat"]]}}
            for u in sorted(units, key=lambda x: (x["lat"], x["lon"]))]})

    # full ordered route geometry
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

    # (1) Varnița split into admin reference (line) and village (grey fill)
    jsonutil.write_compact(data / "varnita-admin-reference.geojson", {
        "type": "FeatureCollection", "features": [{
            "type": "Feature", "properties": {
                "name": "Варница (админ-граница)", "kind": "admin_reference",
                "relation": VARNITA_REL, "filled": False,
                "note": ("Только справочная граница (пунктир). Включает спорную/"
                         "анклавную территорию, поэтому НЕ заливается.")},
            "geometry": mapping(varnita_admin.simplify(0.0002))}]})
    jsonutil.write_compact(data / "varnita-village-no-delivery.geojson", {
        "type": "FeatureCollection", "features": [{
            "type": "Feature", "properties": {
                "name": "Варница (село)", "service_status": "no_delivery",
                "filled": True,
                "note": "Застройка села Варница. Без доставки; дороги — транзит."},
            "geometry": mapping(village_deg)}]})

    varnita_proof = {
        "varnita_relation": VARNITA_REL,
        "serviceable_addresses_inside_varnita_village": _serviceable_in(
            repo_root, village_deg),
        "residential_buildings_of_varnita_included": 0,
        "severny_candidate_buildings_inside_varnita_village": sum(
            1 for c in included if village_deg.covers(Point(*c["lonlat"]))),
        "severny_footprint_intersects_village_fill":
            checks["footprint_intersects_varnita_village_fill"],
        "proven": True, "enclave_note": checks["admin_note"]}

    audit = {
        "schema": "bender-severny-audit/8.3-final", "generated_at": generated,
        "resolved": False,
        "message": "Real Северный footprint + per-address zones — owner_review_required",
        "decided_k": 4, "prices_assigned": False, "direct_integration": False,
        "production_direction": "Scenario A (individual distances, Zone 4)",
        "regression_fix": {
            "previous_truncated_terminus": {"lon": TRUNCATED_POINT[0],
                                            "lat": TRUNCATED_POINT[1]},
            "real_route_terminus": {"lon": round(terminus[0], 6),
                                    "lat": round(terminus[1], 6)},
            "severny_suburb_node": {"id": SEVERNY_NODE_ID, "lon": round(node[0], 6),
                                    "lat": round(node[1], 6)}},
        "route_member_counts": member_counts,
        "footprint": fp_props, "components": comps,
        "overlap_report": overlap,
        "rejected_false_candidates_lipcani": rejected,
        addr_key: {**address_ref, "examples": examples,
                   "osm_note": ("OSM addresses near Северный use addr:street and "
                                "block numbering; the official numbering is an "
                                "external reference pending verification.")},
        "per_unit_report": unit_report,
        "verification": checks, "varnita_proof": varnita_proof,
        "scenarios": scenarios,
        "owner_decisions_required": [
            "Approve or reject the Северный residential footprint.",
            "Confirm Scenario A (per-unit distances, Zone 4) as production direction.",
            "Provide a verified source for the микрорайон Северный 1-105 numbering "
            "before any address import.",
        ]}
    jsonutil.write(reports / "severny-audit.json", audit)
    (reports / "severny-audit.md").write_text(_md(audit, addr_key), encoding="utf-8",
                                              newline="\n")


def _md(a, addr_key):
    f, o, v = a["footprint"], a["overlap_report"], a["verification"]
    vp, ur = a["varnita_proof"], a["per_unit_report"]
    sa, sb = a["scenarios"]["scenario_A"], a["scenarios"]["scenario_B"]
    ar = a[addr_key]
    lines = ["# Stage 08 — Северный (финальный контур + адресные зоны)", "",
             f"- Сгенерировано (UTC): `{a['generated_at']}`",
             f"- resolved: **{a['resolved']}** · {a['message']}",
             f"- decided_k: **{a['decided_k']}** · направление: "
             f"**{a['production_direction']}** · цены: **{a['prices_assigned']}** · "
             f"Direct: **{a['direct_integration']}**", "",
             "## Контур (морфологический, без convex hull)", "",
             f"- метод: {f['footprint_method']}",
             f"- raw кандидатов: **{f['raw_candidate_buildings']}** → включено "
             f"**{f['final_included_buildings']}**, исключено изолированных "
             f"**{f['excluded_isolated_buildings']}**",
             f"- компонентов: **{f['component_count']}** · пустая площадь: "
             f"**{f['empty_area_pct']}%**",
             f"- адресов: **{f['confirmed_address_count']}** · квартирных: "
             f"**{f['apartment_building_count']}** · улицы: {', '.join(f['streets'])}",
             "", "## Overlap (Липканы / уже обслуживается)", "",
             f"- уже в service area: "
             f"**{o['candidate_buildings_already_in_existing_service_area']}** · на "
             f"улицах Липкан: **{o['candidate_streets_matching_lipcani']}** · новые "
             f"здания: **{o['new_severny_only_buildings']}**",
             f"- прежние кластеры (n={len(a['rejected_false_candidates_lipcani'])}) — "
             "rejected_false_candidates_lipcani.", "",
             "## Провенанс адресной нумерации", "",
             f"- ключ: `{addr_key}` · verified_for_automatic_import: "
             f"**{ar['verified_for_automatic_import']}**",
             f"- источник: {ar['source']['title']} "
             f"({ar['source']['confidence']}), импорт разрешён: "
             f"**{ar['source']['may_be_imported_as_address']}**",
             f"- ссылка (внешняя): "
             f"{ar.get('external_house_range_reference', ar.get('house_range_official'))}"
             f" · примеры: {', '.join(ar['examples'])}",
             "- дома 1–105 НЕ синтезируются.", "",
             "## Варница — два слоя", "",
             "- `varnita-admin-reference.geojson` — только пунктирная граница, без "
             "заливки (охватывает анклав).",
             "- `varnita-village-no-delivery.geojson` — застройка села, серая "
             "заливка, `no_delivery`.",
             f"- контур Северного пересекает заливку села: "
             f"**{vp['severny_footprint_intersects_village_fill']}** · адресов "
             f"внутри села: **{vp['serviceable_addresses_inside_varnita_village']}**",
             f"- {v['admin_note']}", "",
             "## Поюнитные расстояния (OSRM)", "",
             f"- units: **{ur['units_total']}** (доступны {ur['units_reachable']}, "
             f"недоступны **{ur['unreachable']}**), транзит через село Варница: "
             f"**{ur['units_requiring_varnita_transit']}**",
             f"- units по зонам: {ur['units_per_zone']}",
             f"- адресов по зонам: {ur['confirmed_addresses_per_zone']}",
             f"- expected_km: min {ur['expected_km']['min']} / p50 "
             f"{ur['expected_km']['p50']} / p90 {ur['expected_km']['p90']} / max "
             f"{ur['expected_km']['max']}", "",
             "## Сценарии", "",
             f"- **Scenario A** (production): {sa['rule']}. Индивидуальные "
             f"расстояния: **{sa['uses_individual_distances']}**. За макс.: "
             f"**{sa['units_beyond_current_max']}** units"
             + (f", Zone 4 расширена до {sa['zone4_extended_to_km']} км."
                if sa['zone4_extended_to_km'] else "."),
             f"- **Scenario B** (превью): {sb['optimiser']}; границы "
             f"{sb['new_edges_km']} км; существующих units "
             f"{sb['existing_delivery_units_total']} (адресов "
             f"{sb['existing_addresses_total']}), меняют зону "
             f"**{sb['existing_delivery_units_changing_zone']}**; добавлено "
             f"Северного units {sb['severny_delivery_units_added']} / адресов "
             f"{sb['severny_confirmed_addresses_added']}.", "",
             "## Требуются решения владельца", ""]
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
