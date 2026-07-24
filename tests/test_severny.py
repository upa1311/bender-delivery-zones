"""Stage 08 (cont.) — Северный residential candidates, Varnița proof, scenarios."""

from __future__ import annotations

import json


def _json(repo_root, rel):
    return json.loads((repo_root / rel).read_text(encoding="utf-8"))


def _audit(repo_root):
    return _json(repo_root, "reports/stage-08/severny-audit.json")


def test_severny_has_derived_residential_clusters(repo_root):
    a = _audit(repo_root)
    assert a["clusters"], "residential candidate clusters must be derived"
    strong = [c for c in a["clusters"] if c["evidence_strength"] == "strong"]
    assert strong, "at least one strongly supported cluster expected"
    for c in a["clusters"]:
        for field in ("building_count", "confirmed_address_count",
                      "apartment_building_count", "streets", "area_m2",
                      "distance_from_terminal_m", "separation_from_varnita_m",
                      "buildings_inside_varnita", "evidence_strength"):
            assert field in c, field


def test_severny_is_not_declared_added(repo_root):
    a = _audit(repo_root)
    assert a["resolved"] is False
    assert "owner_review_required" in a["message"]
    fc = _json(repo_root, "docs/data/severny-service-area.geojson")
    assert fc["resolution_status"] == "candidates_pending_owner_review"
    assert fc["chosen_cluster"] is None, "no cluster may be silently chosen"
    for f in fc["features"]:
        p = f["properties"]
        assert p["district_ru"] == "Северный" and p["settlement_ru"] == "Бендеры"
        assert p["resolution"] == "owner_review_required"
        assert p["geometry_kind"] == "derived_residential_footprint"
        assert f["geometry"]["type"] in ("Polygon", "MultiPolygon")


def test_radius_profile_uses_several_radii(repo_root):
    prof = _audit(repo_root)["radius_profile"]
    assert {"300", "500", "800"} <= set(prof)
    assert (prof["300"]["residential_buildings"]
            <= prof["500"]["residential_buildings"]
            <= prof["800"]["residential_buildings"])


def test_varnita_exclusion_is_proven(repo_root):
    vp = _audit(repo_root)["varnita_proof"]
    assert vp["serviceable_addresses_inside_varnita"] == 0
    assert vp["residential_buildings_of_varnita_included"] == 0
    assert vp["proven"] is True
    fc = _json(repo_root, "docs/data/varnita-exclusion.geojson")
    assert fc["features"][0]["properties"]["status"] == "excluded"


def test_no_severny_candidate_is_classified_as_varnita(repo_root):
    a = _audit(repo_root)
    assert a["varnita_proof"]["severny_candidate_buildings_inside_varnita"] == 0
    for c in a["clusters"]:
        # any building inside Varnița would be flagged, never silently included
        assert c["buildings_inside_varnita"] == 0


def test_scenarios_cover_A_and_B(repo_root):
    sc = _audit(repo_root)["scenarios"]
    assert sc["current_k4_edges_km"]
    for pc in sc["clusters"]:
        assert set(pc["expected_km"]) <= {"begin", "centre", "end"}
        assert "route_through_varnita" in pc
        if pc["scenario_A"]:
            assert 1 <= pc["scenario_A"]["assigned_zone"] <= 4
    b = sc["scenario_B"]
    assert "PREVIEW ONLY" in b["note"]
    assert b["existing_addresses_changing_zone"] >= 0
    assert b["severny_addresses_added"] > 0


def test_scenario_A_keeps_current_k4_edges(repo_root):
    sc = _audit(repo_root)["scenarios"]
    metrics = _json(repo_root, "docs/data/tariff-band-metrics.json")
    assert sc["current_k4_edges_km"] == metrics["candidates"]["4"]["upper_edges_km"]


def test_k4_decision_and_no_money_preserved(repo_root):
    a = _audit(repo_root)
    assert a["decided_k"] == 4
    assert a["prices_assigned"] is False
    assert a["direct_integration"] is False
    metrics = _json(repo_root, "docs/data/tariff-band-metrics.json")
    assert metrics["recommendation"]["decided_k"] == 4


def test_leninsky_ptichnik_reviewed_at_building_level(repo_root):
    review = _json(repo_root, "reports/stage-08/district-coverage-audit.json")[
        "building_level_review"]
    assert {"Ленинский", "Птичник"} <= set(review)
    for _name, r in review.items():
        assert r["residential_buildings_within_400m"] > 0
        assert (r["covered_by_candidate_area"] + r["genuinely_omitted_buildings"]
                == r["residential_buildings_within_400m"])
        assert "expansion_recommended" in r


def test_place_node_outside_is_not_treated_as_district_excluded(repo_root):
    """The owner's point: a label node outside the polygon is not exclusion."""
    d = _json(repo_root, "reports/stage-08/district-coverage-audit.json")
    for x in d["districts"]:
        if x["name"] in ("Ленинский", "Птичник"):
            assert x["status"] == "covered_at_building_level"


def test_owner_decisions_are_listed(repo_root):
    a = _audit(repo_root)
    assert a["owner_decisions_required"]
    joined = " ".join(a["owner_decisions_required"]).lower()
    assert "северный" in joined or "severny" in joined or "footprint" in joined
