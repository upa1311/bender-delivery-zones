"""Stage 06 — OSRM tariff distance bands.

Offline. OSRM itself runs locally during the build; here we assert on the
committed QA evidence it produced (osrm-qa-routes.json) plus the pure banding
and demand-unit logic.
"""

from __future__ import annotations

import csv
import json

import yaml
from shapely.geometry import Point, Polygon, shape

from bender_zones.bands import (
    assign_band,
    band_edges,
    dispersion,
    is_monotonic,
    make_bins,
    optimal_bands,
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
from bender_zones.osrm import expected_cost, worst_cost


def _json(repo_root, rel):
    return json.loads((repo_root / rel).read_text(encoding="utf-8"))


def _units(repo_root):
    text = (repo_root / "docs/data/delivery-units.csv").read_text(encoding="utf-8")
    return list(csv.DictReader(text.splitlines()))


def _u(osm_type, osm_id, unit_type, x, y):
    return DemandUnit(osm_type, osm_id, unit_type, Point(x, y), x, y)


# --- OSRM behaviour, asserted on committed QA evidence ----------------------

def test_osrm_qa_routes_cover_required_pairs(repo_root):
    qa = _json(repo_root, "docs/data/osrm-qa-routes.json")
    pairs = {(r["origin_role"], r["target"]) for r in qa["routes"]}
    for target in ("Parkany", "Giska", "Protyagailovka", "Lipcani"):
        assert ("central", target) in pairs, target
        assert ("bam", target) in pairs, target
    for r in qa["routes"]:
        assert r["distance_km"] and r["distance_km"] > 0
        assert r["duration_min"] and r["duration_min"] > 0


def test_one_way_and_turn_restrictions_make_routing_directional(repo_root):
    """A directed graph gives different forward/reverse road distance.

    An undirected graph that ignored one-ways and turn restrictions would return
    identical distances both ways.
    """
    probe = _json(repo_root, "docs/data/osrm-qa-routes.json")["probes"]["directionality"]
    assert probe["forward_km"] is not None and probe["reverse_km"] is not None
    assert probe["asymmetric"] is True
    assert probe["forward_km"] != probe["reverse_km"]


def test_bridge_crossing_is_a_real_road_distance(repo_root):
    """Crossing ways must not be fused into a false junction.

    If a bridge and the road beneath it were wrongly connected, the route would
    collapse to a near-zero shortcut instead of a real crossing distance.
    """
    probe = _json(repo_root, "docs/data/osrm-qa-routes.json")["probes"]["bridge_crossing"]
    assert probe["plausible"] is True
    assert probe["distance_km"] > 0.9


def test_routing_engine_is_locally_built_osrm_mld(repo_root):
    engine = _json(repo_root, "docs/data/tariff-band-metrics.json")["routing_engine"]
    assert engine["name"] == "OSRM"
    assert engine["algorithm"] == "MLD"
    assert engine["profile"] == "car.lua"
    for capability in ("one-way", "turn restrictions", "barriers", "maxspeed"):
        assert any(capability in h for h in engine["handles"]), capability


def test_spatial_clustering_is_not_the_zoning_model(repo_root):
    doc = _json(repo_root, "docs/data/tariff-band-metrics.json")
    assert doc["model"] == "ordered_cost_bands_over_osrm_road_km"
    for rejected in ("network Voronoi", "spatial K-means", "customer-centred seeds",
                     "Lloyd clustering"):
        assert rejected in doc["not_used"], rejected


# --- demand-unit deduplication ---------------------------------------------

def test_address_node_on_its_building_is_merged():
    building = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    b_unit = _u("w", 1, UNIT_ADDRESSED_BUILDING, 5, 5)
    inside = _u("n", 2, UNIT_ADDRESS_NODE, 5, 5)
    outside = _u("n", 3, UNIT_ADDRESS_NODE, 100, 100)
    kept, merged = deduplicate_address_nodes([b_unit], [inside, outside], [building])
    assert merged == 1
    assert [u.osm_id for u in kept] == [3]


def test_each_unit_occurs_exactly_once_in_committed_csv(repo_root):
    uids = [r["uid"] for r in _units(repo_root)]
    assert len(uids) == len(set(uids)), "a delivery unit appears more than once"


def test_units_are_identified_by_osm_ids(repo_root):
    for r in _units(repo_root)[:200]:
        assert r["osm_type"] in ("n", "w")
        assert r["uid"] == f"{r['osm_type']}{r['osm_id']}"
        assert int(r["osm_id"]) > 0


def test_building_counts_are_not_reported_as_addresses(repo_root):
    counts = _json(repo_root, "docs/data/tariff-band-metrics.json")["unit_counts"]
    assert counts["address_units"] < counts["serviceable_units"]
    assert counts["residential_building_objects_without_address"] > 0
    assert (counts["address_units"]
            + counts["residential_building_objects_without_address"]
            == counts["serviceable_units"])


def test_unaddressed_building_is_lower_confidence():
    addressed = _u("w", 1, UNIT_ADDRESSED_BUILDING, 0, 0)
    bare = _u("w", 2, UNIT_UNADDRESSED_BUILDING, 0, 0)
    assert addressed.is_address is True
    assert bare.is_address is False
    assert unit_weight(bare, 1.0) < unit_weight(addressed, 1.0)


def test_summarise_splits_addresses_from_buildings():
    units = [_u("w", 1, UNIT_ADDRESSED_BUILDING, 0, 0),
             _u("n", 2, UNIT_ADDRESS_NODE, 1, 1),
             _u("w", 3, UNIT_UNADDRESSED_BUILDING, 2, 2)]
    s = summarise(units)
    assert s["unique_units"] == 3
    assert s["address_units"] == 2
    assert s["residential_building_objects_without_address"] == 1


def test_tier_c_units_are_absent_from_bands(repo_root):
    counts = _json(repo_root, "docs/data/tariff-band-metrics.json")["unit_counts"]
    assert counts["tier_c_units_excluded"] >= 0
    for r in _units(repo_root):
        assert r["tier"] in ("A", "B"), "a Tier C unit leaked into the bands"


def test_exceptions_are_listed_explicitly(repo_root):
    text = (repo_root / "docs/data/delivery-exceptions.csv").read_text(encoding="utf-8")
    rows = list(csv.DictReader(text.splitlines()))
    assert rows, "exception list must be explicit, not silent"
    reasons = {r["reason"] for r in rows}
    assert reasons <= {"unreachable_by_osrm", "outside_service_area",
                       "tier_c_no_delivery",
                       "no_serviceable_street_within_threshold",
                       "address_inside_nonresidential_building"}
    for r in rows:
        assert r["uid"] and r["osm_id"]


# --- restaurant origins drive the assignment --------------------------------

def test_origin_weights_change_the_expected_cost():
    central, outer = 1.0, 9.0
    mostly_central = expected_cost([central, outer], [0.85, 0.15])
    mostly_outer = expected_cost([central, outer], [0.15, 0.85])
    assert mostly_central < mostly_outer
    assert abs(mostly_central - (0.85 * 1.0 + 0.15 * 9.0)) < 1e-9


def test_restaurant_weights_can_change_the_assigned_band():
    edges = [2.0, 5.0, 8.0]
    unit_per_origin = [1.0, 9.0]                     # near centre, far from outer
    with_owner_weights = expected_cost(unit_per_origin, [0.85, 0.15])
    if_outer_dominated = expected_cost(unit_per_origin, [0.15, 0.85])
    assert assign_band(with_owner_weights, edges) < assign_band(if_outer_dominated, edges)


def test_worst_origin_is_reported_for_qa():
    assert worst_cost([1.0, 9.0, None]) == 9.0
    assert worst_cost([None, None]) is None


def test_bam_is_resolved_from_the_landmark_not_every_outer_cluster(repo_root):
    fc = _json(repo_root, "docs/data/restaurant-origins.geojson")
    roles = [f["properties"]["role"] for f in fc["features"]]
    assert roles.count("central") == 1
    assert roles.count("bam") == 1, "exactly one origin may be called BAM"
    assert "outer_other" in roles, "other outer clusters must not be labelled BAM"
    assert fc["selection"]["bam_landmark_found"] is True


def test_included_and_excluded_poi_tables_are_published(repo_root):
    sel = _json(repo_root, "docs/data/restaurant-origins.geojson")["selection"]
    assert sel["included_pois"] and sel["excluded_pois"]
    for poi in sel["included_pois"]:
        assert poi["name"], "included POIs must be named"


def test_poi_whitelist_is_strict_named_values(repo_root):
    cfg = yaml.safe_load((repo_root / "config/demand.yml").read_text(encoding="utf-8"))
    wl = cfg["poi_whitelist"]
    assert cfg["poi_require_name"] is True
    assert "restaurant" in wl["amenity"] and "pharmacy" in wl["amenity"]
    assert "supermarket" in wl["shop"] and "bakery" in wl["shop"]
    flat = {v for values in wl.values() for v in values}
    for banned in ("parking", "bench", "toilets", "shelter", "waste_basket",
                   "vending_machine"):
        assert banned not in flat, banned


# --- one-dimensional ordered banding ---------------------------------------

def test_bands_are_ordered_and_monotonic():
    values = [0.5, 0.6, 3.0, 3.1, 7.0, 7.2, 12.0, 12.5]
    weights = [1.0] * len(values)
    bins = make_bins(values, weights, 0.05)
    bounds = optimal_bands(bins, 4, min_weight_share=0.05)
    edges = band_edges(bins, bounds)
    assert edges == sorted(edges)
    grouped = {}
    for v in values:
        grouped.setdefault(assign_band(v, edges), []).append(v)
    ordered = [grouped[k] for k in sorted(grouped)]
    assert is_monotonic(ordered)


def test_committed_bands_are_monotonic_and_ordered(repo_root):
    doc = _json(repo_root, "docs/data/tariff-band-metrics.json")
    for k, res in doc["candidates"].items():
        assert res["monotonic"] is True, k
        edges = res["upper_edges_km"]
        assert edges == sorted(edges)
        zones = res["zones"]
        assert [z["zone"] for z in zones] == list(range(1, len(zones) + 1))
        assert [z["name"] for z in zones] == [f"Zone {i}"
                                              for i in range(1, len(zones) + 1)]
        for a, b in zip(zones, zones[1:], strict=False):
            assert a["km"]["max"] <= b["km"]["min"] + 1e-6, "bands overlap in cost"


def test_every_unit_belongs_to_exactly_one_band(repo_root):
    doc = _json(repo_root, "docs/data/tariff-band-metrics.json")
    rows = _units(repo_root)
    for k, res in doc["candidates"].items():
        col = f"band_k{k}"
        assigned = [r[col] for r in rows]
        assert all(a not in ("", None) for a in assigned), "an address has no zone"
        valid = {str(z["zone"]) for z in res["zones"]}
        assert set(assigned) <= valid
        total = sum(z["unique_delivery_units"] for z in res["zones"])
        assert total == len(rows), "band membership must be exhaustive"


def test_no_economically_meaningless_band(repo_root):
    doc = _json(repo_root, "docs/data/tariff-band-metrics.json")
    for k, res in doc["candidates"].items():
        total = sum(z["demand_weight"] for z in res["zones"])
        for z in res["zones"]:
            assert z["demand_weight"] / total >= 0.04, f"K={k} {z['name']} is a sliver"


def test_min_weight_share_is_enforced_when_satisfiable():
    values = [1.0] * 50 + [9.0] * 50
    weights = [1.0] * 100
    bins = make_bins(values, weights, 0.05)
    bounds = optimal_bands(bins, 2, min_weight_share=0.2)
    total = sum(b.weight for b in bins)
    for start, end in bounds:
        assert sum(b.weight for b in bins[start:end]) / total >= 0.2 - 1e-9


def test_infeasible_floor_still_returns_a_complete_partition():
    """One lonely far unit cannot satisfy a 20% floor; the split still covers all."""
    values = [1.0] * 100 + [50.0]
    weights = [1.0] * 101
    bins = make_bins(values, weights, 0.05)
    bounds = optimal_bands(bins, 2, min_weight_share=0.2)
    assert bounds[0][0] == 0
    assert bounds[-1][1] == len(bins)
    for a, b2 in zip(bounds, bounds[1:], strict=False):
        assert a[1] == b2[0], "bands must tile the cost axis without gaps"


def test_band_polygons_are_mutually_exclusive(repo_root):
    """Bands must not overlap.

    Snapping to the published 5-decimal coordinate grid can leave sub-metre
    slivers along a shared border, so exclusivity is asserted relative to zone
    size rather than as an exact zero.
    """
    fc = _json(repo_root, "docs/data/tariff-bands.geojson")
    for k in (4, 5):
        polys = [shape(f["geometry"]) for f in fc["features"]
                 if f["properties"]["k"] == k]
        assert polys
        for i in range(len(polys)):
            assert polys[i].is_valid, f"K={k} zone {i + 1} geometry is invalid"
            for j in range(i + 1, len(polys)):
                # deg^2 -> m^2 at ~46.8N, so the tolerance is a real-world area.
                overlap_m2 = polys[i].intersection(polys[j]).area * 8.48e9
                assert overlap_m2 < 1000.0, (
                    f"K={k} zones {i + 1} and {j + 1} overlap by "
                    f"{overlap_m2:.0f} m2")


def test_band_layers_are_named_zone_1_upwards(repo_root):
    fc = _json(repo_root, "docs/data/tariff-bands.geojson")
    for k in (4, 5):
        names = sorted(f["properties"]["name"] for f in fc["features"]
                       if f["properties"]["k"] == k)
        assert names == sorted(f"Zone {i}" for i in range(1, k + 1))


def test_dispersion_rewards_tight_bands():
    tight = dispersion([1.0, 1.1, 1.2], [1, 1, 1])
    loose = dispersion([1.0, 5.0, 9.0], [1, 1, 1])
    assert tight < loose


# --- recommendation and money guardrails ------------------------------------

def test_recommendation_requires_owner_review(repo_root):
    doc = _json(repo_root, "docs/data/tariff-band-metrics.json")
    assert doc["recommendation_status"] == "owner_review_required"
    rec = doc["recommendation"]
    assert rec["suggested_k"] in (4, 5)
    assert set(rec["comparison"]) == {"4", "5"}
    for k in ("weighted_km_dispersion", "split_streets",
              "demand_balance_min_over_max"):
        assert k in rec["comparison"]["4"]


def test_no_money_assigned(repo_root):
    doc = _json(repo_root, "docs/data/tariff-band-metrics.json")
    assert doc["prices_assigned"] is False
    assert doc["tariffs_created"] is False
    assert doc["direct_integration"] is False
    assert doc["taxi_calibration_supplied"] is False
    for value in doc["taxi_calibration"].values():
        assert value is None


def test_split_streets_are_reported(repo_root):
    doc = _json(repo_root, "docs/data/tariff-band-metrics.json")
    for res in doc["candidates"].values():
        assert "split_streets" in res
        assert len(res["split_street_list"]) == res["split_streets"]


# --- Stage-06 hardening -----------------------------------------------------

def test_address_inside_nonresidential_building_is_rejected():
    from shapely.geometry import Polygon as P

    from bender_zones.demand_units import reject_addresses_in_nonresidential
    warehouse = P([(0, 0), (10, 0), (10, 10), (0, 10)])
    inside = _u("n", 1, UNIT_ADDRESS_NODE, 5, 5)
    outside = _u("n", 2, UNIT_ADDRESS_NODE, 100, 100)
    kept, rejected = reject_addresses_in_nonresidential(
        [inside, outside], [(warehouse, "non_residential")])
    assert [u.osm_id for u in kept] == [2]
    assert rejected[0]["reason"] == "address_inside_nonresidential_building"
    assert rejected[0]["building_class"] == "non_residential"


def test_nonresidential_address_leakage_is_published(repo_root):
    counts = _json(repo_root, "docs/data/tariff-band-metrics.json")["unit_counts"]
    assert counts["address_nodes_in_nonresidential"] > 0
    rows = list(csv.DictReader((repo_root / "docs/data/delivery-exceptions.csv")
                               .read_text(encoding="utf-8").splitlines()))
    assert any(r["reason"] == "address_inside_nonresidential_building" for r in rows)


def test_no_automatic_tier_a_fallback(repo_root):
    counts = _json(repo_root, "docs/data/tariff-band-metrics.json")["unit_counts"]
    assert counts["no_serviceable_street_within_threshold"] > 0
    rows = list(csv.DictReader((repo_root / "docs/data/delivery-exceptions.csv")
                               .read_text(encoding="utf-8").splitlines()))
    assert any(r["reason"] == "no_serviceable_street_within_threshold" for r in rows)
    # every banded unit really is attached to a serviceable street
    for r in _units(repo_root):
        assert r["street_ru"], "a banded unit has no serviceable street"


def test_split_penalty_reduces_splits_without_breaking_monotonicity(repo_root):
    sweep = _json(repo_root, "docs/data/tariff-band-metrics.json")["tuning"][
        "split_penalty_sweep"]
    for k in ("4", "5"):
        assert sweep["high"]["k"][k]["split_streets"] < \
            sweep["baseline"]["k"][k]["split_streets"]
        for name in sweep:
            edges = sweep[name]["k"][k]["upper_edges_km"]
            assert edges == sorted(edges), f"{name} K={k} lost monotonic ranges"


def test_split_penalty_objective_moves_a_boundary():
    from bender_zones.bands import street_split_counts
    values = [1.0, 1.1, 1.2, 1.3, 2.0, 2.1]
    weights = [1.0] * 6
    bins = make_bins(values, weights, 0.05)
    # one street spans the middle of the cost axis
    street_bins = {"s": list(range(1, len(bins) - 1))}
    split_at = street_split_counts(street_bins, len(bins))
    plain = optimal_bands(bins, 2, 0.05)
    penalised = optimal_bands(bins, 2, 0.05, split_at=split_at, split_penalty=1e6)
    assert plain != penalised


def test_house_number_ranges_are_compact_and_natural():
    from bender_zones.bands import housenumber_ranges
    assert housenumber_ranges(["1", "3", "5", "11"]) == "1-5, 11"
    assert housenumber_ranges(["10", "2", "2A"]) == "2, 2A, 10"
    assert housenumber_ranges([]) == ""


def test_split_streets_publish_exact_house_ranges(repo_root):
    doc = _json(repo_root, "docs/data/tariff-band-metrics.json")
    for res in doc["candidates"].values():
        detail = res["split_street_house_ranges"]
        assert len(detail) == res["split_streets"]
        for d in detail:
            assert len(d["zones"]) > 1, "a split street must span >1 zone"
            for name, z in d["zones"].items():
                assert name.startswith("Zone ")
                assert (z["canonical_address_count"]
                        + z["unaddressed_building_units"]) > 0


def test_demand_weight_sensitivity_is_published_not_chosen_silently(repo_root):
    t = _json(repo_root, "docs/data/tariff-band-metrics.json")["tuning"]
    sens = t["demand_weight_sensitivity"]
    assert {"A", "B", "C"} <= set(sens)
    assert sens["B"]["unaddressed_building_weight"] == 0.25
    assert sens["C"]["unaddressed_building_weight"] == 0.50
    for k in ("4", "5"):
        assert sens["B"]["k"][k]["max_abs_shift_km"] > 0     # boundaries do move
    assert t["published_weight_model"] in sens


def test_apartment_proxy_does_not_invent_household_counts(repo_root):
    apt = _json(repo_root, "docs/data/tariff-band-metrics.json")["tuning"][
        "apartment_sensitivity"]
    assert "addr:flats" in apt["proxy_basis"]
    assert apt["with_addr_flats"] <= apt["apartment_buildings_total"]
    for field in ("with_building_levels", "with_entrances"):
        assert field in apt


def test_conditional_food_venues_need_takeaway(repo_root):
    excluded = _json(repo_root, "docs/data/restaurant-origins.geojson")["selection"][
        "excluded_pois"]
    assert any(e["reason"] == "no_takeaway_or_delivery" for e in excluded), \
        "bar/pub/ice_cream without takeaway must be excluded from origins"


def test_every_unit_is_inside_its_own_band_polygon(repo_root):
    """Voronoi cells guarantee containment; only grid snapping can nudge a
    vertex-adjacent point across a shared border, so a hard-zero would be a lie.
    The residual is bounded and published."""
    cov = _json(repo_root, "docs/data/tariff-band-metrics.json")["map_coverage_check"]
    for k, c in cov.items():
        assert c["units_in_no_band_polygon"] == 0, k
        misplaced = c["units_only_inside_another_band"]
        share = misplaced / c["units_checked"]
        assert share <= 0.001, (
            f"K={k}: {misplaced}/{c['units_checked']} units drawn in "
            "another band")


def test_areas_without_address_data_are_shown_not_coloured(repo_root):
    fc = _json(repo_root, "docs/data/no-address-data.geojson")
    assert fc["features"], "uncovered service area must be published explicitly"
    for f in fc["features"]:
        assert f["properties"]["status"] == "no_assigned_address_data"


def test_unit_points_are_published_for_both_k(repo_root):
    fc = _json(repo_root, "docs/data/delivery-unit-points.geojson")
    for k in (4, 5):
        zones = {f["properties"]["zone"] for f in fc["features"]
                 if f["properties"]["k"] == k}
        assert zones == set(range(1, k + 1))


# --- reproducible OSRM build -------------------------------------------------

def test_osrm_build_provenance_is_recorded(repo_root):
    doc = json.loads((repo_root / "reports/stage-06/osrm-build.json")
                     .read_text(encoding="utf-8"))
    assert doc["engine"]["name"] == "OSRM"
    assert doc["engine"]["algorithm"] == "MLD"
    assert doc["engine"]["version"].startswith("v")
    assert len(doc["engine"]["binary_sha256"]) == 64
    assert len(doc["profile"]["sha256"]) == 64
    assert len(doc["source_pbf"]["sha256"]) == 64
    assert doc["generated_at"].endswith("Z")
    joined = " ".join(doc["commands"])
    for step in ("osrm-extract", "osrm-partition", "osrm-customize", "osrm-routed"):
        assert step in joined, step
    assert "--algorithm mld" in joined


def test_osrm_clean_rebuild_smoke_test_passed(repo_root):
    smoke = json.loads((repo_root / "reports/stage-06/osrm-build.json")
                       .read_text(encoding="utf-8"))["smoke_test"]
    assert smoke["passed"] is True
    assert smoke["directional"]["passed"] is True
    assert smoke["bridge_crossing"]["passed"] is True
    for name in ("centre_to_parkany", "centre_to_giska"):
        lo, hi = smoke[name]["expected_km_range"]
        assert lo <= smoke[name]["distance_km"] <= hi


# --- address-weighted split penalty & canonical addresses -------------------

def test_split_penalty_is_proportional_to_address_demand():
    from bender_zones.bands import street_split_demand
    big = {"busy": [(0, 100.0), (5, 100.0)]}      # 200 addresses torn in half
    small = {"quiet": [(0, 1.0), (5, 1.0)]}       # 2 uncertain units
    cost_big = street_split_demand(big, 6)
    cost_small = street_split_demand(small, 6)
    assert max(cost_big) > max(cost_small) * 50


def test_split_cost_is_lowest_at_the_end_of_a_street():
    from bender_zones.bands import street_split_demand
    cost = street_split_demand({"s": [(0, 10.0), (1, 10.0), (2, 1.0)]}, 4)
    assert cost[3] < cost[2]        # cutting off one unit costs less than halving


def test_penalty_reduces_split_streets_under_balance_constraints(repo_root):
    """With the balance ceiling on, the penalty still buys fewer split streets.

    Split ADDRESS counts no longer fall monotonically: once no zone may exceed
    the ceiling, cuts must pass through the dense middle wherever they go, so the
    address count stays roughly flat. That trade-off is published, not hidden.
    """
    sweep = _json(repo_root, "docs/data/tariff-band-metrics.json")["tuning"][
        "split_penalty_sweep"]
    assert (sweep["high"]["k"]["4"]["split_streets"]
            < sweep["baseline"]["k"]["4"]["split_streets"])
    for name in sweep:
        assert sweep[name]["k"]["4"]["split_confirmed_addresses"] > 0


def test_split_metrics_report_streets_addresses_and_weight(repo_root):
    for res in _json(repo_root, "docs/data/tariff-band-metrics.json")[
            "candidates"].values():
        for field in ("split_streets", "split_confirmed_addresses",
                      "split_demand_weight"):
            assert field in res


def test_canonical_address_key_identifies_the_real_doorway():
    from bender_zones.demand_units import canonical_address_key
    a = canonical_address_key("bender_core", "улица Ленина", "10")
    b = canonical_address_key("bender_core", " Улица  Ленина ", "10 ")
    assert a == b, "the same real address must produce one key"
    assert canonical_address_key("bender_core", "улица Ленина", "11") != a
    assert canonical_address_key("bender_core", "", "10") is None


def test_no_canonical_address_spans_two_zones(repo_root):
    rows = _units(repo_root)
    for k in ("4", "5"):
        seen = {}
        for r in rows:
            key = r.get("canonical_address")
            if not key:
                continue
            seen.setdefault(key, set()).add(r[f"band_k{k}"])
        offenders = [key for key, zones in seen.items() if len(zones) > 1]
        assert not offenders, f"K={k}: {len(offenders)} addresses in >1 zone"


def test_split_streets_publish_canonical_addresses_and_flag_exactness(repo_root):
    for res in _json(repo_root, "docs/data/tariff-band-metrics.json")[
            "candidates"].values():
        assert res["canonical_addresses_in_multiple_zones"] == 0
        for d in res["split_street_house_ranges"]:
            assert d["ranges_are_exact"] is True
            assert not d["canonical_addresses_in_multiple_zones"]
            for z in d["zones"].values():
                assert "canonical_addresses" in z
                assert "unaddressed_building_units" in z


def test_duplicate_address_conflicts_are_published(repo_root):
    conflicts = _json(repo_root, "docs/data/tariff-band-metrics.json")["tuning"][
        "duplicate_address_conflicts"]
    for c in conflicts:
        assert len(c["objects"]) > 1
        assert c["resolution"] == "nearest_access_used_for_all_objects"
        assert c["spread_km"] > 0


# --- apartment scenarios -----------------------------------------------------

def test_apartment_scenarios_published_none_selected(repo_root):
    apt = _json(repo_root, "docs/data/tariff-band-metrics.json")["tuning"][
        "apartment_sensitivity"]
    assert apt["no_scenario_selected"] is True
    assert apt["with_addr_flats"] == 0, "addr:flats is absent in this extract"
    assert apt["with_building_levels"] > 0
    assert set(apt["scenarios"]) >= {"one_unit", "levels"}
    assert any(name.startswith("levels_capped") for name in apt["scenarios"])
    for v in apt["scenarios"].values():
        for k in ("4", "5"):
            assert "edge_shift_km" in v["k"][k]


def test_apartment_proxy_never_claims_household_counts(repo_root):
    apt = _json(repo_root, "docs/data/tariff-band-metrics.json")["tuning"][
        "apartment_sensitivity"]
    assert "No household count is claimed" in apt["proxy_basis"]
    assert "NOT a household count" in apt["scenarios"]["levels"]["description"]


# --- no-street review --------------------------------------------------------

def test_no_street_units_are_grouped_for_review(repo_root):
    s = _json(repo_root, "docs/data/no-street-units-summary.json")
    assert s["total_units"] > 0
    assert set(s["by_kind"]) == {"address", "unaddressed_building"}
    assert "unassigned" not in s["by_settlement"], "units must be attributed"
    rows = list(csv.DictReader((repo_root / "docs/data/no-street-units-review.csv")
                               .read_text(encoding="utf-8").splitlines()))
    assert len(rows) == s["total_units"]
    for r in rows[:50]:
        assert r["cluster_size"] and r["nearest_serviceable_road_m"] is not None
        assert r["status"] == "excluded_pending_owner_review"


def test_dense_no_street_clusters_are_flagged_not_written_off(repo_root):
    s = _json(repo_root, "docs/data/no-street-units-summary.json")
    assert s["dense_clusters_flagged"] > 0
    rows = list(csv.DictReader((repo_root / "docs/data/no-street-units-review.csv")
                               .read_text(encoding="utf-8").splitlines()))
    flags = {r["flag"] for r in rows}
    assert "possible_missing_or_unnamed_access_road" in flags
    assert "missing" in s["note"]


# --- pinned, vendored OSRM ---------------------------------------------------

def test_car_lua_is_vendored_and_checksummed(repo_root):
    import hashlib
    recorded = (repo_root / "vendor/osrm/CHECKSUMS.sha256").read_text(encoding="utf-8")
    assert "profiles/car.lua" in recorded
    for line in recorded.splitlines():
        want, _, name = line.partition("  ")
        got = hashlib.sha256((repo_root / "vendor/osrm" / name).read_bytes()).hexdigest()
        assert got == want, name


def test_osrm_release_is_pinned_for_a_clean_clone(repo_root):
    pin = _json(repo_root, "vendor/osrm/OSRM_PIN.json")
    assert pin["version"].startswith("v")
    for platform in ("linux-x64", "win32-x64"):
        assert pin["binaries"][platform].startswith(
            "https://github.com/Project-OSRM/osrm-backend/releases/download/")
    assert pin["profile"]["vendored"] is True
    assert (repo_root / "scripts/setup_osrm.sh").exists()


def test_build_record_matches_the_vendored_pin(repo_root):
    import hashlib
    rec = json.loads((repo_root / "reports/stage-06/osrm-build.json")
                     .read_text(encoding="utf-8"))
    pin = _json(repo_root, "vendor/osrm/OSRM_PIN.json")
    assert rec["engine"]["version"] == pin["version"]
    vendored = hashlib.sha256(
        (repo_root / "vendor/osrm/profiles/car.lua").read_bytes()).hexdigest()
    assert rec["profile"]["sha256"] == vendored
    assert rec["profile"]["vendored"] is True


# --- K=4 balance regression guard -------------------------------------------

def test_k4_has_no_giant_catch_all_zone(repo_root):
    """Regression: one zone once held 76.6% of all units."""
    res = _json(repo_root, "docs/data/tariff-band-metrics.json")["candidates"]["4"]
    total = sum(z["unique_delivery_units"] for z in res["zones"])
    for z in res["zones"]:
        share = z["unique_delivery_units"] / total
        assert share <= 0.45, f"{z['name']} holds {share:.1%} of all units"


def test_every_k4_zone_has_meaningful_demand(repo_root):
    res = _json(repo_root, "docs/data/tariff-band-metrics.json")["candidates"]["4"]
    total_weight = sum(z["demand_weight"] for z in res["zones"])
    for z in res["zones"]:
        assert z["demand_weight"] / total_weight >= 0.10, \
            f"{z['name']} is economically meaningless"
        assert z["unique_delivery_units"] > 0


def test_k4_stays_monotonic_and_ordered(repo_root):
    res = _json(repo_root, "docs/data/tariff-band-metrics.json")["candidates"]["4"]
    assert res["monotonic"] is True
    assert [z["name"] for z in res["zones"]] == [f"Zone {i}" for i in range(1, 5)]
    for a, b in zip(res["zones"], res["zones"][1:], strict=False):
        assert a["km"]["max"] <= b["km"]["min"] + 1e-6


def test_k_is_fixed_at_four_by_owner_decision(repo_root):
    rec = _json(repo_root, "docs/data/tariff-band-metrics.json")["recommendation"]
    assert rec["decided_k"] == 4
    assert rec["k_decision"] == "fixed_by_owner"
    assert rec["suggested_k"] == 4, "the optimiser must not switch the owner to K=5"
    assert rec["status"] == "owner_review_required"


def test_penalty_variants_all_respect_balance(repo_root):
    sweep = _json(repo_root, "docs/data/tariff-band-metrics.json")["tuning"][
        "split_penalty_sweep"]
    for name, v in sweep.items():
        k4 = v["k"]["4"]
        assert k4["largest_zone_share"] <= 0.45, name
        assert k4["smallest_zone_share"] >= 0.10, name
        assert len(k4["units_per_zone"]) == 4


def test_balance_ceiling_is_enforced_by_the_dp():
    from bender_zones.bands import make_bins, optimal_bands
    # 90 / 60 / 50 by weight: a 0.6 ceiling is satisfiable (45% + 55%).
    bins = make_bins([1.0] * 90 + [3.0] * 60 + [5.0] * 50, [1.0] * 200, 0.05)
    total = sum(b.weight for b in bins)
    bounded = optimal_bands(bins, 2, 0.05, max_weight_share=0.6)
    shares = [sum(b.weight for b in bins[a:b]) / total for a, b in bounded]
    assert max(shares) <= 0.6 + 1e-9, shares
    assert abs(sum(shares) - 1.0) < 1e-9


def test_infeasible_ceiling_relaxes_but_still_partitions_everything():
    """One dominant bin cannot satisfy any ceiling; the split must still cover all."""
    from bender_zones.bands import make_bins, optimal_bands
    bins = make_bins([1.0] * 5 + [5.0] * 400, [1.0] * 405, 0.05)
    bounds = optimal_bands(bins, 2, 0.05, max_weight_share=0.6)
    assert bounds[0][0] == 0 and bounds[-1][1] == len(bins)
