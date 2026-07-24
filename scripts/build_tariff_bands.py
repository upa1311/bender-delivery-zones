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
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import osmium
import yaml
from shapely import set_precision, voronoi_polygons
from shapely.geometry import (
    LineString,
    MultiPoint,
    Point,
    Polygon,
    mapping,
    shape,
)
from shapely.ops import unary_union
from shapely.strtree import STRtree

from bender_zones import jsonutil
from bender_zones.address import (
    UNKNOWN_SETTLEMENT as UNKNOWN_SETTLEMENT_LABEL,
)
from bender_zones.address import (
    build_street_index,
    display_address_ru,
    full_address_ru,
    settlement_district,
)
from bender_zones.address import (
    canonical_address_key as address_key,
)
from bender_zones.bands import (
    assign_band,
    band_edges,
    dispersion,
    housenumber_ranges,
    housenumber_sort_key,
    is_monotonic,
    make_bins,
    optimal_bands,
    street_split_demand,
)
from bender_zones.config import load_audit, load_sources
from bender_zones.demand import (
    CONFIRMED_RESIDENTIAL,
    PROBABLE_RESIDENTIAL,
    classify_building,
    is_apartment_building,
    is_serviceable,
    tier_weight,
)
from bender_zones.demand_units import (
    UNIT_ADDRESS_NODE,
    UNIT_ADDRESSED_BUILDING,
    UNIT_UNADDRESSED_BUILDING,
    DemandUnit,
    deduplicate_address_nodes,
    reject_addresses_in_nonresidential,
    summarise,
    unit_weight,
)
from bender_zones.extract import extract_boundary
from bender_zones.normalize import normalize_text
from bender_zones.osrm import OsrmClient, OsrmError, expected_cost, worst_cost
from bender_zones.service_trim import (
    area_m2,
    local_projection,
    to_degrees,
    to_metres,
)

# Always a delivery origin.
STRONG_FOOD = {"restaurant", "fast_food", "cafe", "food_court"}
# Only an origin when it actually does takeaway/delivery.
CONDITIONAL_FOOD = {"bar", "pub", "ice_cream"}


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
    buildings, addr_nodes, b_polys, nonres_polys = [], [], [], []
    apartments = []
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
                # Keep the footprint: an address node inside a warehouse, garage,
                # school, ruin... must never become a residential delivery unit.
                if kind == "w":
                    nonres_polys.append((poly, cls))
                continue
            if kind == "w":
                b_polys.append(poly)
            if is_apartment_building(tags):
                apartments.append({
                    "uid": f"{kind}{obj.id}",
                    "addr_flats": tags.get("addr:flats"),
                    "building_levels": tags.get("building:levels"),
                    "entrances": tags.get("building:entrances") or tags.get("entrance"),
                })
            unit_type = (UNIT_ADDRESSED_BUILDING if has_addr
                         else UNIT_UNADDRESSED_BUILDING)
            buildings.append(DemandUnit(kind, obj.id, unit_type, pt, lon, lat,
                                        housenumber=tags.get("addr:housenumber")))
        elif has_addr and kind == "n":
            raw_addresses += 1
            addr_nodes.append(DemandUnit(kind, obj.id, UNIT_ADDRESS_NODE, pt, lon, lat,
                                         housenumber=tags.get("addr:housenumber")))

    raw_addresses += sum(1 for u in buildings if u.housenumber)
    return (buildings, addr_nodes, b_polys, nonres_polys, apartments, serviceable,
            tier_c, raw_buildings, raw_addresses)


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
        named = bool((tags.get("name") or "").strip())
        if amenity in STRONG_FOOD or (takeaway and (amenity or tags.get("shop"))):
            if named:
                pois.append((pt, tags.get("name"), amenity))
            else:
                excluded.append({"reason": "unnamed_venue", "amenity": amenity})
        elif amenity in CONDITIONAL_FOOD:
            excluded.append({"reason": "no_takeaway_or_delivery", "amenity": amenity,
                             "name": tags.get("name")})

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
    service_m = {f["properties"]["key"]: to_metres(shape(f["geometry"]), proj)
                 for f in cand["features"]}
    service_all = unary_union(list(service_m.values()))

    tier_by_id, street_by_id = {}, {}
    for row in csv.DictReader((repo_root / "docs/data/street-demand-audit.csv")
                              .read_text("utf-8").splitlines()):
        for oid in row["osm_ids"].split(";"):
            if oid:
                tier_by_id[int(oid)] = row["demand_tier"]
                street_by_id[int(oid)] = (row["settlement"], row["street_ru"])

    all_buildings, all_addr, all_polys, all_nonres, all_apartments = [], [], [], [], []
    serviceable_streets, tier_c_streets = [], []
    raw_b = raw_a = 0
    for city in city_pbfs.values():
        b, a, polys, nonres, apts, sv, tc, rb, ra = _load_units_and_streets(
            city, proj, tier_by_id, street_by_id)
        all_buildings += b
        all_addr += a
        all_polys += polys
        all_nonres += nonres
        all_apartments += apts
        serviceable_streets += sv
        tier_c_streets += tc
        raw_b += rb
        raw_a += ra

    kept_addr, merged = deduplicate_address_nodes(all_buildings, all_addr, all_polys)
    kept_addr, nonres_addr = reject_addresses_in_nonresidential(kept_addr, all_nonres)
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
    serviceable_units, tier_c_units, outside_units, no_street_units = [], [], [], []
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
        threshold = float(bcfg["units"]["street_attach_threshold_m"])
        if sv_i is None or d_sv > threshold:
            # No automatic Tier A: an unattached unit is an explicit exception.
            u.nearest_road_m = None if sv_i is None else round(d_sv, 1)
            no_street_units.append(u)
            continue
        u.settlement, u.street = serviceable_streets[sv_i][1]
        u.tier = serviceable_streets[sv_i][2]
        serviceable_units.append(u)

    print(f"units: raw_buildings={raw_b} raw_address_objects={raw_a} "
          f"merged_duplicates={merged} unique={len(unique_units)} "
          f"serviceable={len(serviceable_units)} tier_c={len(tier_c_units)} "
          f"outside={len(outside_units)} no_street={len(no_street_units)} "
          f"addr_in_nonres={len(nonres_addr)}")

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

    # --- (2) structured addresses + duplicate street-name disambiguation ---
    for r in rows:
        r["settlement_key"] = r["settlement"]
        r["settlement_ru"], r["district_ru"] = settlement_district(r["settlement"])
    # Which (settlement, district, street) need a display qualifier?
    qualifiers = build_street_index(
        [(r["settlement_ru"], r["district_ru"], r["street_ru"]) for r in rows])
    # A district only enters the identity key where it actually disambiguates.
    district_needed = set()
    for (settlement, district, name), qual in qualifiers.items():
        if qual and district is not None or (qual and "другой район" in str(qual)):
            district_needed.add((settlement, name))
    for r in rows:
        key = (r["settlement_ru"], r["district_ru"], normalize_text(r["street_ru"] or ""))
        r["street_qualifier"] = qualifiers.get(key)
        r["display_address_ru"] = display_address_ru(r["street_ru"], r["street_qualifier"])
        r["full_address_ru"] = full_address_ru(
            r["settlement_ru"], r["district_ru"], r["street_ru"], r["housenumber"])
        r["canonical_address"] = address_key(
            r["settlement_ru"], r["street_ru"], r["housenumber"], r["district_ru"],
            district_required=(r["settlement_ru"],
                               normalize_text(r["street_ru"] or "")) in district_needed)

    groups: dict = {}
    for r in rows:
        if r["canonical_address"]:
            groups.setdefault(r["canonical_address"], []).append(r)
    dup_conflicts = []
    for key, members in groups.items():
        kms = [m["expected_km"] for m in members]
        canonical_km = min(kms)
        if len(members) > 1 and max(kms) - min(kms) > float(bcfg["bands"]["bin_width_km"]):
            dup_conflicts.append({
                "canonical_address": key,
                "display_address_ru": members[0]["display_address_ru"],
                "objects": [m["uid"] for m in members],
                "expected_km": [round(x, 3) for x in kms],
                "resolved_km": round(canonical_km, 3),
                "spread_km": round(max(kms) - min(kms), 3),
                "resolution": "nearest_access_used_for_all_objects"})
        for m in members:
            m["expected_km"] = canonical_km
    print(f"canonical addresses: {len(groups)} | multi-object: "
          f"{sum(1 for v in groups.values() if len(v) > 1)} | "
          f"reconciled spread: {len(dup_conflicts)}")
    _street_name_qa(repo_root, rows, qualifiers)

    # --- ordered bands ---
    bw = float(bcfg["bands"]["bin_width_km"])
    min_share = float(bcfg["bands"]["min_weight_share"])
    values = [r["expected_km"] for r in rows]

    apt_flats = {}
    for a in all_apartments:
        try:
            apt_flats[a["uid"]] = int(str(a["addr_flats"]).strip())
        except (TypeError, ValueError):
            continue

    def model_weights(unaddressed_factor, apartment_flats=False):
        out = []
        for r in rows:
            w = tier_weight(r["tier"])
            if r["unit_type"] == UNIT_UNADDRESSED_BUILDING:
                w *= unaddressed_factor
            elif apartment_flats and r["uid"] in apt_flats:
                w *= apt_flats[r["uid"]]
            out.append(w)
        return out

    def bins_for(weights):
        bins = make_bins(values, weights, bw)
        keys = sorted({int(math.floor(v / bw)) for v in values})
        idx_of = {k: i for i, k in enumerate(keys)}
        # Penalty is proportional to the CONFIRMED ADDRESS demand a cut tears
        # apart, so a 200-address street costs far more to split than two
        # uncertain building units.
        street_units = {}
        for r, w in zip(rows, weights, strict=False):
            if not r["street_ru"]:
                continue
            addr_w = w if r["unit_type"] != UNIT_UNADDRESSED_BUILDING else 0.0
            street_units.setdefault((r["settlement"], r["street_ru"]), []).append(
                (idx_of[int(math.floor(r["expected_km"] / bw))], addr_w))
        raw = street_split_demand(street_units, len(bins))
        total_addr = sum(w for units in street_units.values() for _b, w in units) or 1.0
        return bins, [x / total_addr for x in raw]

    max_share = float(bcfg["bands"].get("max_weight_share", 1.0))

    def edges_for(weights, k, penalty):
        bins, split_at = bins_for(weights)
        bounds = optimal_bands(bins, k, min_share, split_at=split_at,
                               split_penalty=penalty, max_weight_share=max_share)
        return band_edges(bins, bounds)

    def split_stats(edges):
        seen, per_street = {}, {}
        for r in rows:
            if not r["street_ru"]:
                continue
            key = (r["settlement"], r["street_ru"])
            zone = assign_band(r["expected_km"], edges)
            seen.setdefault(key, set()).add(zone)
            per_street.setdefault(key, []).append((zone, r))
        split_keys = [k for k, v in seen.items() if len(v) > 1]
        split_addr, split_weight = 0, 0.0
        for key in split_keys:
            for _zone, r in per_street[key]:
                if r["unit_type"] != UNIT_UNADDRESSED_BUILDING:
                    split_addr += 1
                    split_weight += tier_weight(r["tier"])
        return {"split_streets": len(split_keys),
                "split_confirmed_addresses": split_addr,
                "split_demand_weight": round(split_weight, 2)}

    def count_splits(edges, k):
        return split_stats(edges)["split_streets"]

    strengths = bcfg["split_penalty"]["strengths"]
    models = bcfg["sensitivity"]["models"]
    pub_model = bcfg["sensitivity"]["published_model"]
    pub_strength = bcfg["split_penalty"]["published_strength"]

    # (1) split-penalty sweep, on the published weight model
    pub_weights = model_weights(float(models[pub_model]))
    penalty_sweep = {}
    for name, penalty in strengths.items():
        penalty_sweep[name] = {"penalty": penalty, "k": {}}
        for k in bcfg["bands"]["k_values"]:
            e = edges_for(pub_weights, k, float(penalty))
            per_zone_vals = {}
            for r, w in zip(rows, pub_weights, strict=False):
                per_zone_vals.setdefault(assign_band(r["expected_km"], e),
                                         [[], []])[0].append(r["expected_km"])
                per_zone_vals[assign_band(r["expected_km"], e)][1].append(w)
            disp = sum((dispersion(v[0], v[1]) or 0) * sum(v[1])
                       for v in per_zone_vals.values())
            disp /= max(sum(sum(v[1]) for v in per_zone_vals.values()), 1e-9)
            counts, wts = {}, {}
            for r, w in zip(rows, pub_weights, strict=False):
                z = assign_band(r["expected_km"], e)
                counts[z] = counts.get(z, 0) + 1
                wts[z] = wts.get(z, 0.0) + w
            tot_u = sum(counts.values()) or 1
            tot_w = sum(wts.values()) or 1.0
            shares = [wts.get(z, 0.0) / tot_w for z in range(len(e))]
            penalty_sweep[name]["k"][str(k)] = {
                "upper_edges_km": [round(x, 3) for x in e],
                **split_stats(e),
                "weighted_km_dispersion": round(disp, 4),
                "monotonic": True,
                "units_per_zone": [counts.get(z, 0) for z in range(len(e))],
                "unit_share_per_zone": [round(counts.get(z, 0) / tot_u, 3)
                                        for z in range(len(e))],
                "weight_share_per_zone": [round(x, 3) for x in shares],
                "largest_zone_share": round(max(shares) if shares else 0, 3),
                "smallest_zone_share": round(min(shares) if shares else 0, 3),
                "balance_min_over_max": round(
                    (min(shares) / max(shares)) if shares and max(shares) else 0, 3)}

    # (2) demand-weight sensitivity, at the published penalty
    sensitivity = {}
    for name, factor in models.items():
        w = model_weights(float(factor))
        sensitivity[name] = {"unaddressed_building_weight": factor, "k": {}}
        for k in bcfg["bands"]["k_values"]:
            e = edges_for(w, k, float(strengths[pub_strength]))
            sensitivity[name]["k"][str(k)] = {"upper_edges_km": [round(x, 3) for x in e]}
    apt_levels = {}
    for a in all_apartments:
        try:
            apt_levels[a["uid"]] = max(1, int(float(str(a["building_levels"]).strip())))
        except (TypeError, ValueError):
            continue
    apt_cap = int(bcfg["sensitivity"].get("apartment_level_cap", 5))

    def apartment_weights(mode):
        out = []
        for r in rows:
            w = tier_weight(r["tier"])
            if r["unit_type"] == UNIT_UNADDRESSED_BUILDING:
                w *= float(models[pub_model])
            elif mode != "one_unit" and r["uid"] in apt_levels:
                levels = apt_levels[r["uid"]]
                w *= levels if mode == "levels" else min(levels, apt_cap)
            out.append(w)
        return out

    apartment_scenarios = {
        "one_unit": "apartment building counts as 1 address unit",
        "levels": "weight = max(1, building:levels) — an upper-bound proxy, NOT a "
                  "household count",
        f"levels_capped_{apt_cap}": f"weight = min(building:levels, {apt_cap}) — "
                                    "conservative capped proxy",
    }
    apartment_sensitivity = {
        "proxy_basis": ("addr:flats is ABSENT in this extract; building:levels is used "
                        "only as a relative proxy. No household count is claimed."),
        "apartment_buildings_total": len(all_apartments),
        "with_addr_flats": len(apt_flats),
        "with_building_levels": len(apt_levels),
        "with_entrances": sum(1 for a in all_apartments if a["entrances"]),
        "no_scenario_selected": True,
        "scenarios": {},
    }
    for mode, desc in apartment_scenarios.items():
        w = apartment_weights("one_unit" if mode == "one_unit"
                              else ("levels" if mode == "levels" else "capped"))
        apartment_sensitivity["scenarios"][mode] = {
            "description": desc,
            "k": {str(k): {"upper_edges_km":
                           [round(x, 3) for x in
                            edges_for(w, k, float(strengths[pub_strength]))]}
                  for k in bcfg["bands"]["k_values"]}}
    base_apt = apartment_sensitivity["scenarios"]["one_unit"]["k"]
    for mode in apartment_sensitivity["scenarios"]:
        for k in bcfg["bands"]["k_values"]:
            cur = apartment_sensitivity["scenarios"][mode]["k"][str(k)]["upper_edges_km"]
            ref = base_apt[str(k)]["upper_edges_km"]
            apartment_sensitivity["scenarios"][mode]["k"][str(k)]["edge_shift_km"] = [
                round(c - b, 3) for c, b in zip(cur, ref, strict=False)]
    for name in sensitivity:
        for k in bcfg["bands"]["k_values"]:
            base = sensitivity[pub_model]["k"][str(k)]["upper_edges_km"]
            cur = sensitivity[name]["k"][str(k)]["upper_edges_km"]
            sensitivity[name]["k"][str(k)]["edge_shift_km"] = [
                round(c - b, 3) for c, b in zip(cur, base, strict=False)]
            sensitivity[name]["k"][str(k)]["max_abs_shift_km"] = max(
                (abs(c - b) for c, b in zip(cur, base, strict=False)), default=0.0)

    # --- published bands: chosen model + penalty, both documented ---
    results, band_features = {}, []
    for k in bcfg["bands"]["k_values"]:
        edges = edges_for(pub_weights, k, float(strengths[pub_strength]))
        for r, w in zip(rows, pub_weights, strict=False):
            r[f"band_k{k}"] = assign_band(r["expected_km"], edges) + 1
            r["model_weight"] = round(w, 4)
        results[str(k)] = _band_metrics(k, rows, edges, origins, bcfg, pub_weights)
        _band_polygons(k, rows, proj, service_all, bcfg, band_features)

    tuning = {
        "published_weight_model": pub_model,
        "published_split_penalty": pub_strength,
        "note": ("Neither the confidence factor nor the penalty strength is chosen "
                 "silently: every alternative is published above and the owner "
                 "decides."),
        "split_penalty_sweep": penalty_sweep,
        "demand_weight_sensitivity": sensitivity,
        "apartment_sensitivity": apartment_sensitivity,
        "duplicate_address_conflicts": dup_conflicts,
    }

    # Name the territory each unattached unit falls in, so the owner can review
    # them per settlement rather than as one anonymous pile.
    for u in no_street_units:
        for key, geom in service_m.items():
            if geom.covers(u.point):
                u.settlement = key
                break
    _review_no_street(repo_root, no_street_units, service_all, proj, bcfg)
    _write(repo_root, rows, results, band_features, origins, origin_doc, taxi, bcfg,
           {"raw_building_objects": raw_b, "raw_address_objects": raw_a,
            "duplicates_merged": merged, "unique_units": len(unique_units),
            "serviceable_units": len(serviceable_units),
            "tier_c_units_excluded": len(tier_c_units),
            "outside_service_area": len(outside_units),
            "unreachable": len(unreachable),
            "no_serviceable_street_within_threshold": len(no_street_units),
            "address_nodes_in_nonresidential": len(nonres_addr),
            **summarise(serviceable_units)},
           tier_c_units, outside_units, unreachable, client, o_coords, origins, proj,
           no_street_units, nonres_addr, tuning, service_all)
    return 0


def _band_metrics(k, rows, edges, origins, bcfg, model_weights):
    zones = []
    per_band = {}
    for r in rows:
        per_band.setdefault(r[f"band_k{k}"], []).append(r)
    street_bands, split = {}, []
    for r in rows:
        if r["street_ru"]:
            street_bands.setdefault((r["settlement"], r["street_ru"]), set()).add(
                r[f"band_k{k}"])
    split_keys = sorted(s for s, b in street_bands.items() if len(b) > 1)
    split = [f"{a}: {b}" for a, b in split_keys]
    split_detail = []
    for key in split_keys:
        per_zone = {}
        for r in rows:
            if (r["settlement"], r["street_ru"]) == key:
                per_zone.setdefault(r[f"band_k{k}"], []).append(r)
        zones_doc, all_canon = {}, {}
        for z in sorted(per_zone):
            canon = sorted({r["housenumber"].strip() for r in per_zone[z]
                            if r.get("canonical_address")},
                           key=housenumber_sort_key)
            for h in canon:
                all_canon.setdefault(h, set()).add(z)
            zones_doc[f"Zone {z}"] = {
                "canonical_addresses": canon,
                "canonical_address_count": len(canon),
                "house_number_ranges": housenumber_ranges(canon),
                "unaddressed_building_units": sum(
                    1 for r in per_zone[z]
                    if r["unit_type"] == UNIT_UNADDRESSED_BUILDING)}
        overlaps = sorted(h for h, zs in all_canon.items() if len(zs) > 1)
        split_detail.append({
            "settlement": key[0], "street_ru": key[1],
            "zones": zones_doc,
            "canonical_addresses_in_multiple_zones": overlaps,
            "ranges_are_exact": not overlaps})

    ordered_values = []
    for zone in sorted(per_band):
        rs = per_band[zone]
        vals = [r["expected_km"] for r in rs]
        tms = [r["expected_min"] for r in rs]
        ws = [r.get("model_weight", r["weight"]) for r in rs]
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
    split_addr = sum(len(d["zones"][z]["canonical_addresses"])
                     for d in split_detail for z in d["zones"])
    split_weight = round(sum(
        model_weights[i] for i, r in enumerate(rows)
        if (r["settlement"], r["street_ru"]) in set(split_keys)
        and r["unit_type"] != UNIT_UNADDRESSED_BUILDING), 2)
    return {"k": k, "upper_edges_km": [round(e, 3) for e in edges], "zones": zones,
            "monotonic": is_monotonic(ordered_values), "split_streets": len(split),
            "split_confirmed_addresses": split_addr,
            "split_demand_weight": split_weight,
            "canonical_addresses_in_multiple_zones": sum(
                len(d["canonical_addresses_in_multiple_zones"]) for d in split_detail),
            "split_street_list": split, "split_street_house_ranges": split_detail,
            "weighted_dispersion": round(
                sum(z["km_dispersion"] * z["demand_weight"] for z in zones)
                / max(sum(z["demand_weight"] for z in zones), 1e-9), 4)}


def _band_polygons(k, rows, proj, service_all, bcfg, out):
    """Draw each band as the union of its units' Voronoi cells, clipped.

    A buffer-and-subtract drawing puts units near a boundary inside the
    neighbouring band's polygon. A Voronoi partition of the units cannot: every
    unit lies in its own cell, cells are disjoint, and clipping each cell to a
    maximum radius keeps areas with no address data uncovered instead of
    silently colouring them.
    """
    reach = float(bcfg["bands"]["polygon_reach_m"])
    pts = [Point(*proj.to_m(r["lon"], r["lat"])) for r in rows]
    bands = [r[f"band_k{k}"] for r in rows]

    cells = voronoi_polygons(MultiPoint(pts), extend_to=service_all.envelope)
    tree = STRtree(pts)
    per_band = {}
    for cell in cells.geoms:
        idxs = [int(i) for i in tree.query(cell) if cell.covers(pts[int(i)])]
        if not idxs:
            continue
        i = idxs[0]
        clipped = cell.intersection(pts[i].buffer(reach)).intersection(service_all)
        if clipped.is_empty:
            continue
        per_band.setdefault(bands[i], []).append(clipped)

    for zone in sorted(per_band):
        geom = unary_union(per_band[zone]).buffer(0)
        if geom.is_empty:
            continue
        geom_deg = set_precision(to_degrees(geom.simplify(2.0), proj), 1e-5)
        if geom_deg.is_empty:
            continue
        if not geom_deg.is_valid:
            geom_deg = geom_deg.buffer(0)
        out.append(_feature(geom_deg, {
            "k": k, "zone": zone, "name": f"Zone {zone}", "kind": "tariff_band",
            "units": len(per_band[zone]), "area_km2": round(area_m2(geom) / 1e6, 4),
            "status": "prepared_owner_review_required"}))


def _street_name_qa(repo_root, rows, qualifiers):
    """QA report on street names that repeat across settlements/districts."""
    by_name: dict = {}
    for r in rows:
        name = normalize_text(r["street_ru"] or "")
        if not name:
            continue
        place = (r["settlement_ru"], r["district_ru"])
        entry = by_name.setdefault(name, {})
        v = entry.setdefault(place, {"street_ru": r["street_ru"], "addresses": 0,
                                     "unaddressed": 0, "display": r["display_address_ru"]})
        if r.get("canonical_address"):
            v["addresses"] += 1
        else:
            v["unaddressed"] += 1

    duplicates = []
    for name, places in sorted(by_name.items()):
        if len(places) < 2:
            continue
        duplicates.append({
            "normalized_street": name,
            "variants": sorted(
                [{"settlement_ru": p[0] or UNKNOWN_SETTLEMENT_LABEL,
                  "district_ru": p[1], "street_ru": v["street_ru"],
                  "display_address_ru": v["display"],
                  "address_count": v["addresses"],
                  "unaddressed_units": v["unaddressed"]}
                 for p, v in places.items()],
                key=lambda x: (x["settlement_ru"], x["district_ru"] or "")),
            "variant_count": len(places)})

    unknown = [{"uid": r["uid"], "street_ru": r["street_ru"],
                "housenumber": r["housenumber"]}
               for r in rows if not r["settlement_ru"]]

    # Same settlement + street + housenumber but far apart on the ground.
    coord_conflicts = []
    triples: dict = {}
    for r in rows:
        if not r.get("canonical_address"):
            continue
        triples.setdefault(r["canonical_address"], []).append(r)
    for key, members in triples.items():
        if len(members) < 2:
            continue
        lons = [m["lon"] for m in members]
        lats = [m["lat"] for m in members]
        spread_m = max(
            ((max(lons) - min(lons)) * 76000.0), ((max(lats) - min(lats)) * 111000.0))
        if spread_m > 150.0:
            coord_conflicts.append({
                "canonical_address": key,
                "display_address_ru": members[0]["display_address_ru"],
                "full_address_ru": members[0]["full_address_ru"],
                "objects": [m["uid"] for m in members],
                "coordinate_spread_m": round(spread_m),
                "note": "same address, objects far apart — verify on the ground"})

    data = repo_root / "docs/data"
    with open(data / "duplicate-street-names.csv", "w", encoding="utf-8",
              newline="") as fh:
        w = csv.writer(fh, lineterminator=chr(10))
        w.writerow(["normalized_street", "street_ru", "settlement_ru", "district_ru",
                    "display_address_ru", "address_count", "unaddressed_units"])
        for d in duplicates:
            for v in d["variants"]:
                w.writerow([d["normalized_street"], v["street_ru"], v["settlement_ru"],
                            v["district_ru"] or "", v["display_address_ru"],
                            v["address_count"], v["unaddressed_units"]])

    report = {
        "schema": "bender-street-name-qa/7",
        "generated_at": _now(),
        "rule": ("The real OSM street name is never modified and never contains a "
                 "settlement. Qualifiers are display-only."),
        "duplicate_street_names": len(duplicates),
        "duplicates": duplicates,
        "addresses_without_settlement": len(unknown),
        "addresses_without_settlement_sample": unknown[:50],
        "same_address_different_coordinates": len(coord_conflicts),
        "coordinate_conflicts": coord_conflicts,
    }
    jsonutil.write(data / "street-name-qa.json", report)
    reports = repo_root / "reports/stage-07"
    reports.mkdir(parents=True, exist_ok=True)
    jsonutil.write(reports / "duplicate-street-names.json", report)
    lines = ["# Stage 07 — одинаковые названия улиц", "",
             f"- Сгенерировано (UTC): `{report['generated_at']}`",
             f"- Повторяющихся названий: **{len(duplicates)}**",
             f"- Адресов без определённого населённого пункта: "
             f"**{len(unknown)}**",
             f"- Один адрес с разными координатами: **{len(coord_conflicts)}**", "",
             "> " + report["rule"], "",
             "| улица | населённый пункт | район | отображение | адресов | без адреса |",
             "|---|---|---|---|---:|---:|"]
    for d in duplicates:
        for v in d["variants"]:
            lines.append(f"| {v['street_ru']} | {v['settlement_ru']} | "
                         f"{v['district_ru'] or '—'} | {v['display_address_ru']} | "
                         f"{v['address_count']} | {v['unaddressed_units']} |")
    if coord_conflicts:
        lines += ["", "## Один адрес — разные координаты", ""]
        lines += [f"- {c['full_address_ru']} — {len(c['objects'])} объекта, разброс "
                  f"{c['coordinate_spread_m']} м" for c in coord_conflicts[:40]]
    lines += [""]
    (reports / "duplicate-street-names.md").write_text(
        chr(10).join(lines), encoding="utf-8", newline=chr(10))
    return report


def _review_no_street(repo_root, units, service_all, proj, bcfg):
    """Group the unattached units so a missing OSM access road is visible.

    A dense cluster of houses with no named street nearby is far more likely to
    be an unmapped/unnamed access road than a genuine no-delivery pocket, so it
    is flagged for survey instead of being written off.
    """
    radius = float(bcfg["units"].get("cluster_radius_m", 80))
    dense_min = int(bcfg["units"].get("dense_cluster_min_units", 5))
    pts = [u.point for u in units]
    remaining, clusters = list(range(len(pts))), []
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
        clusters.append(sorted(comp))
    cluster_of = {}
    for ci, comp in enumerate(clusters):
        for i in comp:
            cluster_of[i] = (ci, len(comp))

    data = repo_root / "docs/data"
    rows_out, feats = [], []
    for i, u in enumerate(units):
        ci, size = cluster_of[i]
        dense = size >= dense_min
        rows_out.append({
            "uid": u.uid, "osm_type": u.osm_type, "osm_id": u.osm_id,
            "settlement": u.settlement or "unassigned",
            "kind": "address" if u.is_address else "unaddressed_building",
            "housenumber": u.housenumber or "",
            "cluster_id": ci, "cluster_size": size,
            "nearest_serviceable_road_m": getattr(u, "nearest_road_m", None),
            "lon": round(u.lon, 5), "lat": round(u.lat, 5),
            "flag": ("possible_missing_or_unnamed_access_road" if dense
                     else "isolated_no_delivery_candidate"),
            "status": "excluded_pending_owner_review",
        })
        feats.append({"type": "Feature", "properties": rows_out[-1],
                      "geometry": {"type": "Point",
                                   "coordinates": [round(u.lon, 5), round(u.lat, 5)]}})
    rows_out.sort(key=lambda r: (-r["cluster_size"], r["settlement"], r["uid"]))
    with open(data / "no-street-units-review.csv", "w", encoding="utf-8",
              newline="") as fh:
        fields = list(rows_out[0]) if rows_out else ["uid"]
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator=chr(10))
        w.writeheader()
        for r in rows_out:
            w.writerow(r)
    jsonutil.write_compact(data / "no-street-units-review.geojson",
                           {"type": "FeatureCollection",
                            "features": sorted(
                                feats, key=lambda f: f["properties"]["uid"])})
    summary = {
        "total_units": len(units),
        "clusters": len(clusters),
        "dense_clusters_flagged": sum(1 for c in clusters if len(c) >= dense_min),
        "units_in_dense_clusters": sum(len(c) for c in clusters if len(c) >= dense_min),
        "by_settlement": {},
        "by_kind": {"address": sum(1 for r in rows_out if r["kind"] == "address"),
                    "unaddressed_building": sum(1 for r in rows_out
                                                if r["kind"] == "unaddressed_building")},
        "largest_clusters": [{"cluster_id": ci, "units": len(c)}
                             for ci, c in sorted(enumerate(clusters),
                                                 key=lambda x: -len(x[1]))[:10]],
        "note": ("Dense clusters likely indicate a missing or unnamed OSM access "
                 "road, not a definitive no-delivery decision."),
    }
    for r in rows_out:
        key = r["settlement"]
        summary["by_settlement"][key] = summary["by_settlement"].get(key, 0) + 1
    jsonutil.write(data / "no-street-units-summary.json", summary)
    return summary


def _write(repo_root, rows, results, band_features, origins, origin_doc, taxi, bcfg,
           counts, tier_c_units, outside_units, unreachable, client, o_coords,
           origin_meta, proj, no_street_units, nonres_addr, tuning, service_all):
    data = repo_root / "docs/data"
    ks = sorted(results)
    fields = ["uid", "osm_type", "osm_id", "unit_type", "settlement",
              "settlement_ru", "district_ru", "street_ru", "display_address_ru",
              "full_address_ru", "canonical_address",
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
        for u in no_street_units:
            w.writerow([u.uid, u.osm_type, u.osm_id, u.unit_type,
                        round(u.lon, 6), round(u.lat, 6),
                        "no_serviceable_street_within_threshold"])
        for e in nonres_addr:
            w.writerow([e["uid"], e["osm_type"], e["osm_id"],
                        f"address_in_{e['building_class']}",
                        round(e["lon"], 6), round(e["lat"], 6), e["reason"]])

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
    for u in no_street_units:
        exc_feats.append({"type": "Feature",
                          "properties": {"uid": u.uid, "unit_type": u.unit_type,
                                         "reason": "no_serviceable_street_within_threshold"},
                          "geometry": {"type": "Point",
                                       "coordinates": [round(u.lon, 5), round(u.lat, 5)]}})
    for e in nonres_addr:
        exc_feats.append({"type": "Feature",
                          "properties": {"uid": e["uid"],
                                         "unit_type": f"address_in_{e['building_class']}",
                                         "reason": e["reason"]},
                          "geometry": {"type": "Point",
                                       "coordinates": [round(e["lon"], 5),
                                                       round(e["lat"], 5)]}})
    exc_feats.sort(key=lambda f: (f["properties"]["reason"], f["properties"]["uid"]))
    jsonutil.write_compact(data / "delivery-exceptions.geojson",
                           {"type": "FeatureCollection", "features": exc_feats})

    jsonutil.write_compact(data / "tariff-bands.geojson",
                           {"type": "FeatureCollection", "features": band_features})

    # --- unit points coloured by band (compact MultiPoint per k/zone) ---
    ks = sorted(results)
    point_feats = []
    for k in ks:
        groups = {}
        for r in rows:
            groups.setdefault(r[f"band_k{k}"], []).append([r["lon"], r["lat"]])
        for zone in sorted(groups):
            point_feats.append({
                "type": "Feature",
                "properties": {"k": int(k), "zone": zone, "name": f"Zone {zone}",
                               "units": len(groups[zone])},
                "geometry": {"type": "MultiPoint", "coordinates": groups[zone]}})
    jsonutil.write_compact(data / "delivery-unit-points.geojson",
                           {"type": "FeatureCollection", "features": point_feats})

    # --- verify every unit is visually inside its own band, and nowhere else ---
    coverage = {}
    for k in ks:
        polys = {f["properties"]["zone"]: shape(f["geometry"]) for f in band_features
                 if f["properties"]["k"] == int(k)}
        prepared = {z: g.buffer(0) for z, g in polys.items()}
        wrong_only, uncovered = 0, 0
        for r in rows:
            pt = Point(r["lon"], r["lat"])
            own = prepared.get(r[f"band_k{k}"])
            if own is not None and own.covers(pt):
                continue
            others = [z for z, g in prepared.items()
                      if z != r[f"band_k{k}"] and g.covers(pt)]
            if others:
                wrong_only += 1
            else:
                uncovered += 1
        coverage[str(k)] = {
            "units_checked": len(rows),
            "units_outside_own_band_polygon": wrong_only + uncovered,
            "units_only_inside_another_band": wrong_only,
            "units_in_no_band_polygon": uncovered,
        }

    # --- service area with no assigned address data (shown, never silently filled) ---
    covered = unary_union([shape(f["geometry"]) for f in band_features
                           if f["properties"]["k"] == int(ks[0])]).buffer(0)
    gap = to_degrees(service_all, proj).buffer(0).difference(covered)
    gap = set_precision(gap, 1e-5)
    gap_feats = []
    if not gap.is_empty:
        for comp in (gap.geoms if hasattr(gap, "geoms") else [gap]):
            if comp.area * 8.48e9 < 2000:
                continue
            gap_feats.append({"type": "Feature", "properties": {
                "status": "no_assigned_address_data",
                "note": ("Внутри рабочей территории, но без назначенных адресных "
                         "единиц — не окрашено ни в одну тарифную зону."),
                "area_m2": round(comp.area * 8.48e9)},
                "geometry": _round(mapping(comp))})
    jsonutil.write_compact(data / "no-address-data.geojson",
                           {"type": "FeatureCollection", "features": gap_feats})
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
        "tuning": tuning,
        "map_coverage_check": coverage,
        "no_address_data_areas": len(gap_feats),
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
    decided = 4  # owner decision: four zones. Not re-litigated by the optimiser.
    return {
        "status": "owner_review_required",
        "decided_k": decided,
        "k_decision": "fixed_by_owner",
        "suggested_k": decided,
        "note_on_k": ("K=4 is an accepted owner decision; the comparison below is "
                      "published for reference only and never overrides it. What "
                      "still needs owner review is the split-penalty variant."),
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
    t = doc["tuning"]
    lines += ["## Split-street penalty sweep", "",
              f"Опубликовано: **{t['published_split_penalty']}** · модель веса "
              f"**{t['published_weight_model']}**. {t['note']}", "",
              "| штраф | K=4 splits | K=4 дисперсия | K=5 splits | K=5 дисперсия |",
              "|---|---:|---:|---:|---:|"]
    for name in ("baseline", "low", "medium", "high"):
        v = t["split_penalty_sweep"].get(name)
        if not v:
            continue
        k4, k5 = v["k"].get("4", {}), v["k"].get("5", {})
        lines.append(f"| {name} ({v['penalty']}) | {k4.get('split_streets')} | "
                     f"{k4.get('weighted_km_dispersion')} | {k5.get('split_streets')} | "
                     f"{k5.get('weighted_km_dispersion')} |")
    lines += ["", "## Demand-weight sensitivity (сдвиг границ к модели A)", "",
              "| модель | K | границы, км | макс. сдвиг, км |", "|---|---|---|---:|"]
    for name, v in t["demand_weight_sensitivity"].items():
        for k, x in v["k"].items():
            lines.append(f"| {name} | {k} | {x['upper_edges_km']} | "
                         f"{round(x['max_abs_shift_km'], 3)} |")
    apt = t["demand_weight_sensitivity"].get("apartment_flats_proxy", {})
    lines += ["", f"Квартирный прокси: `addr:flats` у {apt.get('with_addr_flats')} из "
              f"{apt.get('apartment_units_total')} многоквартирных, "
              f"`building:levels` у {apt.get('with_building_levels')}, "
              f"подъезды у {apt.get('with_entrances')}. "
              "Точное число домохозяйств при отсутствии данных не выдумывается.", ""]
    lines += ["## Split streets — точные диапазоны домов", ""]
    for k, res in doc["candidates"].items():
        detail = res.get("split_street_house_ranges", [])
        lines += [f"### K={k} ({len(detail)} улиц)", ""]
        for d in detail[:25]:
            parts = "; ".join(
                f"{z}: {v['house_number_ranges'] or '—'}"
                f" ({v['canonical_address_count']} адр."
                + (f", +{v['unaddressed_building_units']} без адреса)"
                   if v["unaddressed_building_units"] else ")")
                for z, v in d["zones"].items())
            exact = "точные" if d["ranges_are_exact"] else "НЕ точные (дубли номеров)"
            lines.append(f"- **{d['settlement']}: {d['street_ru']}** [{exact}] — {parts}")
        if len(detail) > 25:
            lines.append(f"- … и ещё {len(detail) - 25} улиц (полный список в JSON)")
        lines += [""]
    cov = doc["map_coverage_check"]
    lines += ["## Проверка карты", "",
              "| K | единиц | вне своей зоны | только в чужой зоне | ни в одной |",
              "|---|---:|---:|---:|---:|"]
    for k, c in cov.items():
        lines.append(f"| {k} | {c['units_checked']} | "
                     f"{c['units_outside_own_band_polygon']} | "
                     f"{c['units_only_inside_another_band']} | "
                     f"{c['units_in_no_band_polygon']} |")
    lines += ["", f"Участков «нет адресных данных»: {doc['no_address_data_areas']} "
              "(показаны серым, не окрашены в зоны).", ""]
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
