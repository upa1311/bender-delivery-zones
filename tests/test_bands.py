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
                       "tier_c_no_delivery"}
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
