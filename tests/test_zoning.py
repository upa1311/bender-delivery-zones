"""Stage-05: owner decisions, routing measurements and K=4/K=5 candidates.

Offline: pure routing/zoning logic plus assertions on the committed artifacts.
"""

from __future__ import annotations

import csv
import json

import yaml
from shapely.geometry import Point, Polygon

from bender_zones.demand import (
    TIER_A,
    TIER_B,
    TIER_C,
    StreetDemand,
    assign_tier,
    is_serviceable,
    service_status,
    tier_weight,
)
from bender_zones.routing import (
    build_graph,
    dijkstra,
    parse_maxspeed,
    snap_nodes,
    way_speed_kmh,
    weighted_percentile,
)
from bender_zones.zoning import (
    assign_all_nodes,
    build_zones,
    is_uncertain,
    polsby_popper,
    zone_graph_components,
)

SPEEDS = {"residential": 30, "primary": 60}


def _json(repo_root, rel):
    return json.loads((repo_root / rel).read_text(encoding="utf-8"))


def _grid_graph():
    """Small 3-node chain: A --100m-- B --100m-- C on a residential road."""
    ways = [([(0, 0), (100, 0), (200, 0)], {"highway": "residential"})]
    return build_graph(ways, SPEEDS, 30)


# --- owner decision 1: Tier C is not serviceable ---------------------------

def test_tier_c_is_not_serviceable():
    assert is_serviceable(TIER_A) is True
    assert is_serviceable(TIER_B) is True
    assert is_serviceable(TIER_C) is False


def test_tier_c_service_status_is_no_delivery():
    assert service_status(TIER_C) == "no_delivery"
    assert tier_weight(TIER_C) == 0.0


def test_isolated_one_or_two_house_street_is_tier_c():
    tier, _reason = assign_tier(StreetDemand(probable_residential_buildings=2))
    assert tier == TIER_C
    assert is_serviceable(tier) is False


def test_committed_tier_c_rows_are_no_delivery(repo_root):
    rows = list(csv.DictReader(
        (repo_root / "docs/data/street-demand-audit.csv").read_text(
            encoding="utf-8").splitlines()))
    tier_c = [r for r in rows if r["demand_tier"] == "C"]
    assert tier_c
    for r in tier_c:
        assert r["service_status"] == "no_delivery"
        assert r["affects_zone_pricing"] == "False"


def test_tier_c_layer_marks_no_delivery(repo_root):
    fc = _json(repo_root, "docs/data/tier-c-manual-review.geojson")
    assert fc["features"]
    for f in fc["features"]:
        assert f["properties"]["service_status"] == "no_delivery"
        assert f["properties"]["affects_zone_pricing"] is False


# --- owner decision 2: restaurant-origin model ------------------------------

def test_origin_weights_are_85_15(repo_root):
    cfg = yaml.safe_load((repo_root / "config/demand.yml").read_text(encoding="utf-8"))
    origins = cfg["restaurant_origins"]
    assert origins["central_weight"] == 0.85
    assert origins["outer_total_weight"] == 0.15


def test_committed_origins_split_85_15_and_document_selection(repo_root):
    fc = _json(repo_root, "docs/data/restaurant-origins.geojson")
    feats = fc["features"]
    assert feats
    central = [f for f in feats if f["properties"]["role"] == "central"]
    outer = [f for f in feats if f["properties"]["role"] == "bam_outer"]
    assert len(central) == 1
    assert abs(central[0]["properties"]["weight"] - 0.85) < 1e-6
    assert abs(sum(f["properties"]["weight"] for f in outer) - 0.15) < 1e-3
    doc = fc["selection"]
    for key in ("method", "why_representative", "villages_excluded",
                "bam_landmark_note", "source"):
        assert doc.get(key), key
    assert "Overpass" in doc["source"] or "no Nominatim" in doc["source"]


def test_villages_are_not_restaurant_origins(repo_root):
    fc = _json(repo_root, "docs/data/restaurant-origins.geojson")
    roles = {f["properties"]["role"] for f in fc["features"]}
    assert roles <= {"central", "bam_outer"}


# --- owner decision 3: Protyagailovka correction ----------------------------

def test_protyagailovka_is_not_clipped_by_a_side_of_glavnaya(repo_root):
    cfg = yaml.safe_load(
        (repo_root / "config/service-trim.yml").read_text(encoding="utf-8"))
    terr = next(t for t in cfg["territories"] if t["key"] == "protyagailovka")
    limits = terr["owner_limits"]
    assert "left_limit_street" not in limits
    assert "left_direction" not in limits
    assert "Главная улица" in limits["include_full_length_streets"]
    for street in ("улица Мунтяна", "Лесовая улица", "Первомайская улица"):
        assert street in limits["orientation_streets"]


def test_report_has_no_unresolved_glavnaya_side_question(repo_root):
    fc = _json(repo_root, "docs/data/boundary-questions.geojson")
    for f in fc["features"]:
        props = f["properties"]
        assert props["kind"] != "unresolved", props.get("question")
        assert "Подтвердите сторону" not in props.get("question", "")
    report = _json(repo_root, "reports/stage-04/residential-demand-audit.json")
    meta = report["owner_limits"]["protyagailovka"]
    assert meta["clipped_by_side"] is False


def test_glavnaya_marked_included_full_length_both_sides(repo_root):
    fc = _json(repo_root, "docs/data/boundary-questions.geojson")
    glavnaya = [f for f in fc["features"]
                if f["properties"].get("street") == "Главная улица"]
    assert glavnaya
    assert glavnaya[0]["properties"]["role"] == "included_full_length"
    assert "ОБЕИМ" in glavnaya[0]["properties"]["question"]


# --- routing measurements ---------------------------------------------------

def test_maxspeed_parsing():
    assert parse_maxspeed("50") == 50
    assert parse_maxspeed("30 km/h") == 30
    assert round(parse_maxspeed("30 mph"), 1) == 48.3
    assert parse_maxspeed("walk") is None
    assert parse_maxspeed(None) is None


def test_way_speed_prefers_maxspeed_then_class():
    assert way_speed_kmh({"highway": "residential", "maxspeed": "50"}, SPEEDS, 30) == 50
    assert way_speed_kmh({"highway": "residential"}, SPEEDS, 30) == 30
    assert way_speed_kmh({"highway": "unknown_class"}, SPEEDS, 30) == 30


def test_dijkstra_returns_road_distance_and_time_not_straight_line():
    # A detour: the direct line is short but the road goes around.
    ways = [([(0, 0), (0, 100), (100, 100), (100, 0)], {"highway": "residential"})]
    graph = build_graph(ways, SPEEDS, 30)
    table = dijkstra(graph, [(0, 0)], minimise="time")
    entry = table[(100, 0)]
    assert round(entry[1]) == 300          # 300 m along the road...
    assert Point(0, 0).distance(Point(100, 0)) == 100   # ...vs 100 m straight line
    assert entry[2] > 0


def test_travel_time_uses_speed():
    graph = _grid_graph()
    table = dijkstra(graph, [(0, 0)], minimise="time")
    seconds = table[(200, 0)][2]
    assert abs(seconds - 200 / (30 * 1000 / 3600)) < 1e-6


def test_snap_nodes_respects_radius():
    graph = _grid_graph()
    near, far = Point(10, 5), Point(10, 5000)
    got = snap_nodes([near, far], graph, radius_m=50)
    assert got[0] is not None
    assert got[1] is None


def test_weighted_percentile():
    assert weighted_percentile([1, 2, 3], [1, 1, 1], 50) == 2
    assert weighted_percentile([1, 100], [100, 1], 50) == 1   # weight dominates
    assert weighted_percentile([], [], 50) is None


# --- zoning -----------------------------------------------------------------

def test_zones_are_connected_on_the_graph():
    ways = [([(x * 100, 0) for x in range(11)], {"highway": "residential"})]
    graph = build_graph(ways, SPEEDS, 30)
    customers = [(x * 100, 0) for x in range(11)]
    assignment, seeds = build_zones(graph, customers, [1.0] * 11, 2, iterations=4)
    assert len(seeds) == 2
    node_zone = assign_all_nodes(graph, seeds)
    for zone in set(node_zone.values()):
        nodes = [n for n, z in node_zone.items() if z == zone]
        assert zone_graph_components(graph, nodes) == 1


def test_zone_graph_components_detects_a_split():
    ways = [([(0, 0), (100, 0)], {"highway": "residential"}),
            ([(5000, 0), (5100, 0)], {"highway": "residential"})]
    graph = build_graph(ways, SPEEDS, 30)
    assert zone_graph_components(graph, list(graph.adjacency)) == 2


def test_uncertainty_margin():
    assert is_uncertain(100.0, 105.0, 10) is True     # 5% apart
    assert is_uncertain(100.0, 130.0, 10) is False    # 30% apart
    assert is_uncertain(100.0, float("inf"), 10) is False


def test_polsby_popper_circle_is_more_compact_than_a_sliver():
    circle = Point(0, 0).buffer(100)
    sliver = Polygon([(0, 0), (1000, 0), (1000, 5), (0, 5)])
    assert polsby_popper(circle) > polsby_popper(sliver)


# --- committed K candidates -------------------------------------------------

def test_both_k_published_and_neither_selected(repo_root):
    m = _json(repo_root, "docs/data/zone-metrics.json")
    assert set(m["candidates"]) == {"4", "5"}
    assert len(m["candidates"]["4"]["zones"]) == 4
    assert len(m["candidates"]["5"]["zones"]) == 5
    assert m["status"] == "prepared_not_selected"
    assert m["winner"] is None


def test_no_prices_or_tariffs_assigned(repo_root):
    m = _json(repo_root, "docs/data/zone-metrics.json")
    assert m["prices_assigned"] is False
    assert m["tariffs_created"] is False
    assert m["direct_integration"] is False
    assert m["taxi_calibration_supplied"] is False
    for value in m["taxi_calibration"].values():
        assert value is None


def test_zoning_uses_road_routing_not_straight_line(repo_root):
    method = _json(repo_root, "docs/data/zone-metrics.json")["method"]
    assert "actual road travel" in method["distance_basis"]
    assert "straight-line distance" in method["not_used"]
    assert "polygon area" in method["not_used"]
    assert "none" in method["routing_engine"]      # no OSRM/Valhalla/GraphHopper
    assert method["road_graph"]["nodes"] > 0


def test_every_zone_reports_the_required_metrics(repo_root):
    m = _json(repo_root, "docs/data/zone-metrics.json")
    for res in m["candidates"].values():
        assert "connected_zones" in res
        assert "split_streets" in res
        assert "exceptions" in res
        assert "uncertain_streets" in res
        for z in res["zones"]:
            for key in ("addresses", "demand_weight", "compactness_polsby_popper",
                        "graph_connected", "origin_comparison"):
                assert key in z, key
            for p in ("p50", "p75", "p90"):
                assert z["distance_km"][p] is not None
                assert z["travel_time_min"][p] is not None
            assert z["max_reasonable_route"]["excludes_percentile_above"] == 95


def test_zones_are_connected_in_committed_output(repo_root):
    m = _json(repo_root, "docs/data/zone-metrics.json")
    for k, res in m["candidates"].items():
        assert res["connected_zones"] == len(res["zones"]), k
        for z in res["zones"]:
            assert z["graph_components"] == 1


def test_zone_candidates_geojson_has_both_k(repo_root):
    fc = _json(repo_root, "docs/data/zone-candidates.geojson")
    ks = {f["properties"]["k"] for f in fc["features"]}
    assert ks == {4, 5}
    for f in fc["features"]:
        assert f["properties"]["status"] == "prepared_not_selected"


def test_travel_times_are_documented_as_free_flow_lower_bounds(repo_root):
    method = _json(repo_root, "docs/data/zone-metrics.json")["method"]
    assert "free-flow" in method["travel_time_basis"]
    assert "LOWER BOUNDS" in method["travel_time_basis"]
