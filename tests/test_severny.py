"""Stage 08 (corrected) — the REAL Северный resolved from the full PBF."""

from __future__ import annotations

import json

from bender_zones.address import full_address_ru

TRUNCATED_LAT = 46.854251
LIPCANI_STREETS = {"улица Энгельса", "переулок Энгельса", "улица Кутузова",
                   "Подольская улица", "Парканская улица", "Колхозная улица",
                   "улица Гайдара"}


def _json(repo_root, rel):
    return json.loads((repo_root / rel).read_text(encoding="utf-8"))


def _audit(repo_root):
    return _json(repo_root, "reports/stage-08/severny-audit.json")


# --- the regression itself --------------------------------------------------

def test_real_route_terminal_is_not_the_truncated_point(repo_root):
    a = _audit(repo_root)
    rf = a["regression_fix"]
    assert rf["previous_truncated_terminus"]["lat"] == TRUNCATED_LAT
    assert rf["real_route_terminus"]["lat"] > TRUNCATED_LAT + 0.02, \
        "the real terminal must be well north of the truncated point"
    assert a["verification"]["terminus_is_not_truncated_point"] is True


def test_full_routes_were_resolved_from_the_full_pbf(repo_root):
    counts = _audit(repo_root)["route_member_counts"]
    assert set(counts) == {"6572078", "6572079", "6572080", "6572081"}
    for c in counts.values():
        assert c["with_geometry"] == c["way_members"] > 0


def test_previous_clusters_recorded_as_rejected_lipcani(repo_root):
    rejected = _audit(repo_root)["rejected_false_candidates_lipcani"]
    assert rejected, "the false Lipcani clusters must be recorded, not deleted"
    joined = " ".join(s for c in rejected for s in c.get("streets", []))
    assert "Кутузова" in joined or "Подольская" in joined or "Парканская" in joined


# --- the corrected candidate ------------------------------------------------

def test_footprint_is_north_of_varnita_and_disconnected(repo_root):
    v = _audit(repo_root)["verification"]
    assert v["footprint_north_of_varnita_village"] is True
    assert v["footprint_crosses_varnita_village"] is False
    assert v["footprint_disconnected_from_main_service"] is True
    p = _json(repo_root, "docs/data/severny-service-area.geojson")[
        "features"][0]["properties"]
    assert p["north_of_varnita_village"] is True
    assert p["disconnected_from_main_service"] is True


def test_candidate_does_not_overlap_lipcani_or_service(repo_root):
    o = _audit(repo_root)["overlap_report"]
    assert o["candidate_buildings_already_in_existing_service_area"] == 0
    assert o["candidate_addresses_already_classified_as_lipcani"] == 0
    assert o["candidate_streets_matching_lipcani"] == 0
    assert o["new_severny_only_buildings"] > 0


def test_known_lipcani_streets_are_not_in_severny(repo_root):
    streets = set(_json(repo_root, "docs/data/severny-service-area.geojson")[
        "features"][0]["properties"]["streets"])
    assert not (streets & LIPCANI_STREETS), \
        f"Lipcani streets leaked into Северный: {streets & LIPCANI_STREETS}"


def test_footprint_carries_settlement_and_district(repo_root):
    p = _json(repo_root, "docs/data/severny-service-area.geojson")[
        "features"][0]["properties"]
    assert p["settlement_ru"] == "Бендеры"
    assert p["district_ru"] == "Северный"
    assert p["status"] == "candidate_residential_footprint"
    assert p["resolution"] == "owner_review_required"


def test_official_severny_address_format_is_supported(repo_root):
    assert full_address_ru("Бендеры", "микрорайон Северный", "", "13") == \
        "Бендеры, микрорайон Северный, дом 13"
    support = _audit(repo_root)["official_address_support"]
    assert support["house_range_official"] == "1-105"
    assert "Бендеры, микрорайон Северный, дом 13" in support["examples"]


def test_route_reaches_the_residential_microdistrict(repo_root):
    v = _audit(repo_root)["verification"]
    assert v["central_route_reaches_severny"] is True
    assert v["central_route_km"] and v["central_route_km"] > 4.0


def test_varnita_exclusion_still_proven(repo_root):
    vp = _audit(repo_root)["varnita_proof"]
    assert vp["serviceable_addresses_inside_varnita"] == 0
    assert vp["severny_candidate_buildings_inside_varnita_village"] == 0
    assert vp["proven"] is True


def test_enclave_admin_nuance_is_documented(repo_root):
    v = _audit(repo_root)["verification"]
    # honest: the node falls inside the OSM admin Varnița relation, and we say so
    assert "enclave" in v["admin_note"].lower()


# --- scenarios --------------------------------------------------------------

def test_scenario_A_keeps_k4_and_extends_zone4_only_if_beyond_max(repo_root):
    sc = _audit(repo_root)["scenarios"]
    metrics = _json(repo_root, "docs/data/tariff-band-metrics.json")
    assert sc["current_k4_edges_km"] == metrics["candidates"]["4"]["upper_edges_km"]
    sa = sc["scenario_A"]
    assert 1 <= sa["assigned_zone"] <= 4
    if not sa["beyond_current_max"]:
        assert sa["zone4_extended_to_km"] is None


def test_scenario_B_separates_units_from_addresses(repo_root):
    b = _audit(repo_root)["scenarios"]["scenario_B"]
    assert "PREVIEW ONLY" in b["note"]
    assert b["existing_delivery_units_total"] >= b["existing_addresses_total"]
    assert b["severny_delivery_units_added"] >= b["severny_confirmed_addresses_added"]
    assert b["severny_delivery_units_added"] > 0


def test_k4_and_no_money_preserved(repo_root):
    a = _audit(repo_root)
    assert a["decided_k"] == 4
    assert a["prices_assigned"] is False and a["direct_integration"] is False
    assert _json(repo_root, "docs/data/tariff-band-metrics.json")[
        "recommendation"]["decided_k"] == 4


def test_severny_not_declared_added(repo_root):
    a = _audit(repo_root)
    assert a["resolved"] is False
    fc = _json(repo_root, "docs/data/severny-service-area.geojson")
    assert fc["chosen"] is False
    assert fc["resolution_status"] == "candidate_pending_owner_review"
