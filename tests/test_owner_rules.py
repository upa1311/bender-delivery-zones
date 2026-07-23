"""Authoritative owner rules (Stage 04/05 decisions), verified offline.

Tier C = no_delivery, restaurant-origin weights, and the Protyagailovka
correction. Routing itself is now OSRM: see tests/test_bands.py.
"""

from __future__ import annotations

import csv
import json

import yaml

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


def _json(repo_root, rel):
    return json.loads((repo_root / rel).read_text(encoding="utf-8"))


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
    outer = [f for f in feats if f["properties"]["role"] in ("bam", "outer_other")]
    assert len(central) == 1
    assert abs(central[0]["properties"]["weight"] - 0.85) < 1e-6
    assert abs(sum(f["properties"]["weight"] for f in outer) - 0.15) < 1e-3
    doc = fc["selection"]
    for key in ("bam_resolution", "included_pois", "source"):
        assert doc.get(key), key
    assert "Overpass" in doc["source"] or "Nominatim" in doc["source"]


def test_villages_are_not_restaurant_origins(repo_root):
    fc = _json(repo_root, "docs/data/restaurant-origins.geojson")
    roles = {f["properties"]["role"] for f in fc["features"]}
    assert roles <= {"central", "bam", "outer_other"}


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


