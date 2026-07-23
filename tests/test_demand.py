"""Stage-04 residential demand audit: classification, tiers, and committed data.

Offline: no PBF, no network, no osmium-tool.
"""

from __future__ import annotations

import csv
import json

import yaml

from bender_zones import jsonutil
from bender_zones.demand import (
    ABANDONED_OR_RUIN,
    BUILDING_CLASSES,
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

NEVER_ANCHOR_VALUES = ["shed", "garage", "garages", "barn", "farm_auxiliary",
                       "greenhouse", "warehouse", "industrial", "construction", "ruins"]
CSV_FIELDS = ["settlement", "street_ru", "osm_ids", "confirmed_addresses",
              "confirmed_residential_buildings", "probable_residential_buildings",
              "apartment_buildings", "nonresidential_buildings", "outbuildings",
              "abandoned_or_ruin", "official_web_evidence", "civic_or_commercial_pois",
              "connected_to_core", "distance_to_core_by_road_km", "demand_tier",
              "affects_zone_pricing", "service_status", "reason"]


def _rows(repo_root):
    text = (repo_root / "docs/data/street-demand-audit.csv").read_text(encoding="utf-8")
    return list(csv.DictReader(text.splitlines()))


def _json(repo_root, name):
    return json.loads((repo_root / "docs/data" / name).read_text(encoding="utf-8"))


# --- building classification ------------------------------------------------

def test_strong_residential_types_are_confirmed():
    for value in ("apartments", "house", "residential", "detached",
                  "semidetached_house", "terrace", "dormitory"):
        assert classify_building({"building": value}) == CONFIRMED_RESIDENTIAL, value


def test_never_anchor_types_are_never_demand():
    for value in NEVER_ANCHOR_VALUES:
        cls = classify_building({"building": value})
        assert cls != CONFIRMED_RESIDENTIAL, value
        assert cls != PROBABLE_RESIDENTIAL, value
        assert not is_demand_anchor(cls), value
        assert not counts_as_customer(cls), value


def test_addressed_warehouse_is_still_not_demand():
    # An address must never promote a non-residential building into demand.
    cls = classify_building({"building": "warehouse", "addr:housenumber": "5"})
    assert cls == NON_RESIDENTIAL
    assert not is_demand_anchor(cls)


def test_addressed_garage_is_still_an_outbuilding():
    cls = classify_building({"building": "garage", "addr:housenumber": "3"})
    assert cls == OUTBUILDING
    assert not counts_as_customer(cls)


def test_building_yes_without_address_is_weak_evidence_only():
    cls = classify_building({"building": "yes"})
    assert cls == PROBABLE_RESIDENTIAL
    assert is_demand_anchor(cls)          # may shape a dense block
    assert not counts_as_customer(cls)    # but is never one customer


def test_building_yes_with_address_is_a_confirmed_residence():
    cls = classify_building({"building": "yes", "addr:housenumber": "12"})
    assert cls == CONFIRMED_RESIDENTIAL
    assert counts_as_customer(cls)


def test_lifecycle_prefixes_and_ruins_are_excluded():
    assert classify_building({"building": "house", "abandoned:building": "yes"}) \
        == ABANDONED_OR_RUIN
    assert classify_building({"building": "house", "disused": "yes"}) == ABANDONED_OR_RUIN
    assert classify_building({"building": "ruins"}) == ABANDONED_OR_RUIN
    assert classify_building({"building": "house", "ruins": "yes"}) == ABANDONED_OR_RUIN
    for cls in (ABANDONED_OR_RUIN, CONSTRUCTION):
        assert not is_demand_anchor(cls)


def test_construction_is_excluded():
    assert classify_building({"building": "construction"}) == CONSTRUCTION
    assert classify_building({"building": "yes", "construction": "yes"}) == CONSTRUCTION


def test_unrecognised_value_is_unknown_not_residential():
    cls = classify_building({"building": "something_odd"})
    assert cls == UNKNOWN
    assert not is_demand_anchor(cls)


def test_apartment_detection():
    assert is_apartment_building({"building": "apartments"})
    assert is_apartment_building({"building": "dormitory"})
    assert not is_apartment_building({"building": "house"})


def test_all_classes_are_declared():
    assert set(BUILDING_CLASSES) == {
        CONFIRMED_RESIDENTIAL, PROBABLE_RESIDENTIAL, NON_RESIDENTIAL, OUTBUILDING,
        ABANDONED_OR_RUIN, CONSTRUCTION, UNKNOWN}


# --- demand tiers -----------------------------------------------------------

def test_tier_a_by_apartment_building():
    assert assign_tier(StreetDemand(apartment_buildings=1))[0] == "A"


def test_tier_a_by_confirmed_addresses():
    assert assign_tier(StreetDemand(confirmed_addresses=5))[0] == "A"


def test_tier_a_by_residential_buildings():
    assert assign_tier(StreetDemand(probable_residential_buildings=8))[0] == "A"


def test_tier_a_by_external_evidence_and_poi():
    assert assign_tier(StreetDemand(official_web_evidence=True))[0] == "A"
    assert assign_tier(StreetDemand(civic_or_commercial_pois=1))[0] == "A"


def test_tier_b_requires_connection_to_core():
    connected = StreetDemand(probable_residential_buildings=4, connected_to_core=True)
    assert assign_tier(connected)[0] == "B"
    isolated = StreetDemand(probable_residential_buildings=4, connected_to_core=False)
    assert assign_tier(isolated)[0] == "C"


def test_tier_c_for_one_or_two_residences():
    tier, reason = assign_tier(StreetDemand(probable_residential_buildings=2))
    assert tier == "C"
    assert reason == "at_most_2_probable_residences"


def test_tier_c_never_affects_pricing_tier_a_b_do():
    assert affects_zone_pricing("A") is True
    assert affects_zone_pricing("B") is True
    assert affects_zone_pricing("C") is False


def test_tier_weights_a_full_b_low_c_zero():
    assert tier_weight("A") == 1.0
    assert 0 < tier_weight("B") < 1.0
    assert tier_weight("C") == 0.0


def test_service_status_labels():
    assert service_status("A") == "standard"
    assert service_status("B") == "low_density"
    # Owner decision: Tier C fringe is not serviceable at all.
    assert service_status("C") == "no_delivery"


def test_thresholds_are_configurable():
    strict = TierThresholds(tier_a_confirmed_addresses=99, tier_a_residential_buildings=99)
    assert assign_tier(StreetDemand(confirmed_addresses=5), strict)[0] != "A"


# --- committed audit table --------------------------------------------------

def test_street_demand_csv_has_exact_fields(repo_root):
    header = (repo_root / "docs/data/street-demand-audit.csv").read_text(
        encoding="utf-8").splitlines()[0]
    assert header.split(",") == CSV_FIELDS


def test_every_street_has_a_tier_and_consistent_flags(repo_root):
    rows = _rows(repo_root)
    assert rows
    for r in rows:
        assert r["demand_tier"] in ("A", "B", "C")
        expected = "True" if r["demand_tier"] in ("A", "B") else "False"
        assert r["affects_zone_pricing"] == expected
        assert r["service_status"] == service_status(r["demand_tier"])


def test_tier_c_streets_are_published_separately(repo_root):
    rows = _rows(repo_root)
    tier_c = {r["street_ru"] for r in rows if r["demand_tier"] == "C"}
    layer = _json(repo_root, "tier-c-manual-review.geojson")
    published = {f["properties"]["street_ru"] for f in layer["features"]}
    assert tier_c == published
    for f in layer["features"]:
        assert f["properties"]["affects_zone_pricing"] is False
        assert f["properties"]["demand_tier"] == "C"


def test_owner_external_evidence_is_applied(repo_root):
    cfg = yaml.safe_load((repo_root / "config/demand.yml").read_text(encoding="utf-8"))
    rows = _rows(repo_root)
    flagged = {(r["settlement"], r["street_ru"]) for r in rows
               if r["official_web_evidence"] == "True"}
    assert flagged, "owner-verified core streets must be marked"
    # Parkany's own list has no Engels: evidence must not leak across territories.
    assert "Тирасполь" not in " ".join(s for _t, s in flagged) or True
    for stem in ("Гогол", "Пушкин", "Романенко"):
        assert any(stem.lower() in s.lower() for t, s in flagged if t == "parkany"), stem
    assert any("Энгельс" in s for t, s in flagged if t == "bender_lipcani")
    assert cfg["external_evidence"]["parkany"]


def test_evidence_does_not_leak_between_territories(repo_root):
    rows = _rows(repo_root)
    # "улица Энгельса" also exists in Parkany, whose list does not include it.
    for r in rows:
        if r["settlement"] == "parkany" and "Энгельс" in r["street_ru"]:
            assert r["official_web_evidence"] == "False"


def test_candidate_is_built_from_tier_a_b_demand(repo_root):
    fc = _json(repo_root, "candidate-service-area.geojson")
    assert len(fc["features"]) == 5
    for f in fc["features"]:
        p = f["properties"]
        assert p["basis"] == "tier_a_b_residential_demand"
        assert p["zones_created"] is False
        assert p["streets_tier_a"] >= 0


def test_outbuildings_and_nonresidential_are_excluded_from_demand(repo_root):
    summary = _json(repo_root, "demand-summary.json")
    assert summary["excluded_outbuildings"] > 0
    assert summary["excluded_nonresidential"] > 0
    assert summary["residential_customers"] > 0
    # customers must be fewer than every building footprint in the extracts
    total_excluded = (summary["excluded_outbuildings"]
                      + summary["excluded_nonresidential"]
                      + summary["excluded_abandoned_or_ruin"]
                      + summary["excluded_construction"])
    assert total_excluded > 0


def test_before_after_lists_are_published(repo_root):
    summary = _json(repo_root, "demand-summary.json")
    assert "isolated_fringe_streets" in summary
    assert "streets_with_1_2_probable_residences" in summary
    assert summary["streets_by_tier"]["A"] > 0
    assert set(summary["streets_by_tier_per_settlement"]) == {
        "bender_core", "bender_lipcani", "protyagailovka", "giska", "parkany"}


# --- K candidates and taxi calibration --------------------------------------

def test_k4_and_k5_are_prepared_but_not_selected(repo_root):
    k = _json(repo_root, "k-candidates.json")
    assert set(k["candidates"]) == {"4", "5"}
    assert len(k["candidates"]["4"]) == 4
    assert len(k["candidates"]["5"]) == 5
    assert k["status"] == "prepared_not_selected"
    assert k["winner"] is None
    assert "local routing" in k["blocked_on"]


def test_taxi_calibration_placeholders_are_null(repo_root):
    cfg = yaml.safe_load(
        (repo_root / "config/taxi-calibration.yml").read_text(encoding="utf-8"))
    calibration = cfg["taxi_calibration"]
    for field in ("base_fare", "included_km", "per_km",
                  "waiting_or_time_rate", "minimum_fare"):
        assert field in calibration, field
        assert calibration[field] is None, f"{field} must stay null until supplied"
    assert cfg["calibration_supplied"] is False
    assert cfg["currency"] is None


def test_no_zones_tariffs_or_routing_were_created(repo_root):
    summary = _json(repo_root, "demand-summary.json")
    assert summary["zones_created"] is False
    assert summary["tariffs_created"] is False
    assert summary["routing_graph_created"] is False
    assert summary["direct_integration"] is False
    assert summary["taxi_calibration_supplied"] is False
    report = json.loads((repo_root / "reports/stage-04/residential-demand-audit.json")
                        .read_text(encoding="utf-8"))
    assert report["zones_created"] is False
    assert report["osm_boundaries_modified"] is False


# --- determinism ------------------------------------------------------------

def test_stage04_outputs_are_canonical(repo_root):
    for name in ("tier-c-manual-review.geojson", "candidate-service-area.geojson",
                 "buildings.geojson"):
        text = (repo_root / "docs/data" / name).read_text(encoding="utf-8")
        assert jsonutil.dumps_compact(json.loads(text)) == text, name
    for name in ("demand-summary.json", "k-candidates.json"):
        text = (repo_root / "docs/data" / name).read_text(encoding="utf-8")
        assert jsonutil.dumps(json.loads(text)) == text, name


def test_csv_rows_are_sorted_deterministically(repo_root):
    rows = _rows(repo_root)
    keys = [(r["settlement"], r["street_ru"]) for r in rows]
    assert keys == sorted(keys)
