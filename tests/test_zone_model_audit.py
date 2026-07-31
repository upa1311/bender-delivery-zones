"""Integrity rules for the candidate zone-model audit (commit 1: route models).

Economic-model checks (5E / 5T / hybrid, sensitivity grid) are added in commit 2.
These tests cover the route-distance foundation, provenance and protected data.
"""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "releases/bender-zones-v1.1/address-registry.json"
FEATURES = ROOT / "data/interim/zone-model-address-features-v1.csv"
CANDIDATES = ROOT / "data/interim/zone-model-candidates-v1.csv"
ANCHORS = ROOT / "data/interim/external-tariff-boundary-anchors-v1.csv"


def _load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ZM = _load_module("zone_model_audit", "scripts/zone_model_audit.py")


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


REGISTRY_ADDRESSES = json.loads(REGISTRY.read_text(encoding="utf-8"))["addresses"]
FEATURE_ROWS = _csv(FEATURES)
CANDIDATE_ROWS = _csv(CANDIDATES)
ANCHOR_ROWS = _csv(ANCHORS)


def _models() -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in CANDIDATE_ROWS:
        grouped.setdefault(row["model_id"], []).append(row)
    return grouped


# 1
def test_canonical_population_is_9216():
    assert len(REGISTRY_ADDRESSES) == 9216
    assert len(FEATURE_ROWS) == 9216


# 2
def test_address_ids_are_unique():
    ids = [row["address_id"] for row in FEATURE_ROWS]
    assert len(set(ids)) == 9216
    assert set(ids) == {a["uid"] for a in REGISTRY_ADDRESSES}


# 3
def test_coordinates_present_for_every_address():
    for row in FEATURE_ROWS:
        assert row["lat"] and row["lon"]
        assert -90 <= float(row["lat"]) <= 90
        assert -180 <= float(row["lon"]) <= 180


# 4
def test_protected_registry_addresses_unchanged_count_and_zone_range():
    zones = {int(a["zone_id"]) for a in REGISTRY_ADDRESSES}
    assert zones == {1, 2, 3, 4}
    assert all(a["source_dataset_version"] == "moldova-pbf:09ba0c058e89"
               for a in REGISTRY_ADDRESSES)


# 5
def test_every_route_metric_has_provenance_status():
    for row in FEATURE_ROWS:
        assert row["route_metric_status"] == "expected_km_osrm"
        assert float(row["route_km"]) > 0


# 6
def test_missing_route_metrics_are_not_simulated():
    # No per-address route duration exists; it must stay blank, never invented.
    assert all(row["route_duration_min"] == "" for row in FEATURE_ROWS)


# 7
def test_in_and_outside_km_are_non_negative():
    for row in FEATURE_ROWS:
        for field in ("in_city_km", "outside_city_km"):
            if row[field] != "":
                assert float(row[field]) >= 0


# 8
def test_split_used_only_with_evidence():
    for row in FEATURE_ROWS:
        if row["territory"] == "Бендеры":
            assert row["outside_split_status"] == "CITY_ALL_IN"
            assert float(row["outside_city_km"]) == 0.0
            assert float(row["in_city_km"]) == float(row["route_km"])
        else:
            assert row["outside_split_status"] == "OUTSIDE_SPLIT_UNKNOWN"
            assert row["in_city_km"] == "" and row["outside_city_km"] == ""


# 9
def test_varnita_not_in_deliverable_population():
    assert all(row["territory"] != "Варница" for row in FEATURE_ROWS)
    assert all(a["settlement_ru"] != "Варница" for a in REGISTRY_ADDRESSES)


# 10
def test_lipcani_is_city_not_external():
    lip = [a for a in REGISTRY_ADDRESSES if a.get("district_ru") == "Липканы"]
    assert len(lip) == 248
    assert all(a["settlement_ru"] == "Бендеры" for a in lip)
    lip_uids = {a["uid"] for a in lip}
    for row in FEATURE_ROWS:
        if row["address_id"] in lip_uids:
            assert row["territory"] == "Бендеры"
            assert row["outside_split_status"] == "CITY_ALL_IN"


# 11
def test_parkany_and_giska_are_separate_territories():
    territories = {row["territory"] for row in FEATURE_ROWS}
    assert {"Парканы", "Гиска", "Протягайловка"} <= territories
    anchor_terr = {row["territory"] for row in ANCHOR_ROWS}
    assert {"Парканы", "Гиска", "Протягайловка"} <= anchor_terr


# 12
def test_severny_has_no_automatic_classification():
    sev = [row for row in ANCHOR_ROWS if row["territory"] == "Северный"]
    assert sev and sev[0]["confidence"] == "UNPROVEN"
    assert sev[0]["owner_confirmation_required"] == "True"


# 13-15
def test_k4_k5_k6_have_the_right_number_of_non_empty_zones():
    models = _models()
    for model_id, k in (("K4R_dp_optimal_jenks", 4),
                        ("K5R_dp_optimal_jenks", 5),
                        ("K6R_dp_optimal_jenks", 6)):
        zones = models[model_id]
        assert len(zones) == k
        assert all(int(z["address_count"]) > 0 for z in zones)


# 16-18
def test_thresholds_strictly_increasing_and_partition_is_exhaustive():
    models = _models()
    for zones in models.values():
        zones = sorted(zones, key=lambda z: int(z["zone_id"]))
        uppers = [float(z["upper_bound"]) for z in zones if z["upper_bound"] != ""]
        assert uppers == sorted(uppers) and len(uppers) == len(set(uppers))
        # contiguous: each lower bound equals the previous upper bound
        for prev, cur in zip(zones, zones[1:], strict=False):
            assert float(cur["lower_bound"]) == float(prev["upper_bound"])
        assert sum(int(z["address_count"]) for z in zones) == 9216


# 19
def test_baseline_k4_reproduces_released_zones():
    assert ZM.BASELINE_EDGES == [2.424, 4.076, 5.577]
    rows = ZM.load_addresses()
    match = sum(1 for r in rows
                if ZM.zone_for(r["route_km"], ZM.BASELINE_EDGES) == r["zone_id"])
    assert match >= 9211


# 40
def test_unknown_boundary_anchors_have_no_invented_coordinates():
    for row in ANCHOR_ROWS:
        assert row["confidence"] == "UNPROVEN"
        assert row["lat"] == "" and row["lon"] == ""
        assert row["owner_confirmation_required"] == "True"
    gai = [r for r in ANCHOR_ROWS if r["anchor_id"] == "PARKANY_KOTOVSKOGO_GAI_POST"]
    assert gai and "UNKNOWN_REQUIRES_OWNER_MAP_CONFIRMATION" in gai[0]["notes"]


# 38
def test_partition_methods_are_deterministic():
    rows = ZM.load_addresses()
    values = [r["route_km"] for r in rows]
    for func in (ZM.thresholds_quantile, ZM.thresholds_kmeans, ZM.thresholds_dp_optimal):
        assert func(values, 5) == func(values, 5)


def test_taxi_reference_formulas_match_owner_evidence():
    # Owner assumptions: min 18, city 6/km, outside 10/km.
    assert ZM.taxi_reference_a(2.0, 0.0) == 18.0          # floor binds
    assert ZM.taxi_reference_a(4.0, 0.0) == 24.0          # 6*4
    assert ZM.taxi_reference_a(3.0, 2.0) == max(18.0, 18.0 + 20.0)  # 6*3 + 10*2
    assert ZM.taxi_reference_b(2.0, 0.0) == 18.0          # first 3 km included
    assert ZM.taxi_reference_b(5.0, 0.0) == 18.0 + 6 * 2  # (5-3)*6
    assert ZM.taxi_reference_b(4.0, 1.0) == 18.0 + 6 * 1 + 10 * 1
