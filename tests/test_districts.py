"""Stage 08 — Bender district coverage and the unresolved Северный area."""

from __future__ import annotations

import json


def _json(repo_root, rel):
    return json.loads((repo_root / rel).read_text(encoding="utf-8"))


def test_district_coverage_audit_lists_every_bender_suburb(repo_root):
    d = _json(repo_root, "reports/stage-08/district-coverage-audit.json")
    assert d["districts_total"] >= 10
    assert d["connected"] + d["disconnected"] == d["districts_total"]
    for x in d["districts"]:
        assert x["status"] in ("connected", "disconnected",
                               "covered_at_building_level")
        if x["status"] == "connected":
            assert x["covered_by_candidate_area"] is True
        assert x["osm_id"] and x["name"]


def test_disconnected_districts_are_flagged(repo_root):
    d = _json(repo_root, "reports/stage-08/district-coverage-audit.json")
    disc = [x for x in d["districts"] if x["status"] == "disconnected"]
    assert len(disc) == d["disconnected"]
    for x in disc:
        assert x["covered_by_candidate_area"] is False
        assert x["distance_to_candidate_area_m"] >= 0


def test_severny_is_not_declared_resolved(repo_root):
    """Full Severny candidate checks live in tests/test_severny.py."""
    a = _json(repo_root, "reports/stage-08/severny-audit.json")
    assert a["resolved"] is False
    assert a["direct_integration"] is False


def test_severny_route_qa_has_real_geometry(repo_root):
    fc = _json(repo_root, "docs/data/severny-route-qa.geojson")
    assert fc["features"], "the marshrutka route geometry must be published"
    for f in fc["features"]:
        assert f["geometry"]["type"] == "LineString"
        assert len(f["geometry"]["coordinates"]) >= 2
        assert f["properties"]["layer"] == "severny_route_qa"
