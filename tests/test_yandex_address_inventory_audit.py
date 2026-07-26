"""Integrity and fail-closed rules for the Yandex address inventory checkpoint."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = "4a1c2a86b08e22f6a8d83ba8b5983a89f309e7b6"
REGISTRY = ROOT / "releases/bender-zones-v1.1/address-registry.json"
CLASSIFICATION = ROOT / "data/interim/canonical-deliverable-address-classification-v1.csv"
SAMPLE = ROOT / "data/interim/yandex-address-validation-sample-v1.csv"
RESULTS = ROOT / "data/interim/yandex-forward-address-validation-v1.csv"
EXTRAS = ROOT / "data/interim/yandex-observed-extra-addresses-v1.csv"
CHECKPOINT = ROOT / "data/interim/yandex-address-validation-checkpoint-v1.json"
REGISTRY_SHA = "bc66ad113a6ba5706bb6d2797ddc543e5b576482051d0d981551f014561c1817"


def _load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILD = _load_module("build_yandex_inventory", "scripts/build_yandex_address_inventory_sample.py")
ANALYZE = _load_module("analyze_yandex_inventory", "scripts/analyze_yandex_address_inventory.py")


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _normalized_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


@pytest.fixture(scope="module")
def population_and_metadata():
    return BUILD.build_classification()


@pytest.fixture(scope="module")
def sample_rows():
    return _csv(SAMPLE)


def test_01_source_database_is_unchanged():
    assert len(json.loads(REGISTRY.read_text(encoding="utf-8"))["addresses"]) == 9216
    assert _normalized_hash(REGISTRY) == REGISTRY_SHA


def test_02_source_sha256_is_preserved_and_documented():
    report = (ROOT / "reports/yandex-address-inventory/sample-methodology-v1.md").read_text(
        encoding="utf-8"
    )
    assert REGISTRY_SHA in report
    assert BUILD.normalized_sha256(REGISTRY) == REGISTRY_SHA


def test_03_address_ids_are_unique(population_and_metadata):
    population, _ = population_and_metadata
    ids = [row["address_id"] for row in population]
    assert len(ids) == len(set(ids)) == 9216


def test_04_sample_is_deterministic(population_and_metadata, sample_rows):
    rebuilt = BUILD.build_sample(*population_and_metadata)
    assert rebuilt == sample_rows
    assert len(sample_rows) >= 1000


def test_05_every_unique_street_group_is_represented(population_and_metadata, sample_rows):
    population, metadata = population_and_metadata
    population_keys = {
        (row["territory"], metadata[row["address_id"]]["district"], row["street"])
        for row in population
    }
    sampled_ids = {row["address_id"] for row in sample_rows}
    sample_keys = {
        (row["territory"], metadata[row["address_id"]]["district"], row["street"])
        for row in population
        if row["address_id"] in sampled_ids
    }
    assert sample_keys == population_keys
    assert len(population_keys) == 316


def test_06_short_streets_are_included_in_full(population_and_metadata, sample_rows):
    population, metadata = population_and_metadata
    groups = defaultdict(set)
    for row in population:
        key = (row["territory"], metadata[row["address_id"]]["district"], row["street"])
        groups[key].add(row["address_id"])
    expected = set().union(*(ids for ids in groups.values() if len(ids) <= 5))
    sampled = {row["address_id"] for row in sample_rows}
    assert expected <= sampled


def test_07_all_known_discrepancy_controls_are_mandatory(sample_rows):
    discrepancy_ids = {row["control_id"] for row in _csv(BUILD.DISCREPANCIES)}
    reasons = ";".join(row["selection_reason"] for row in sample_rows)
    assert len(discrepancy_ids) == 57
    assert all(
        f"KNOWN_DISCREPANCY:{control_id}" in reasons
        or f"KNOWN_DISCREPANCY_PROXY:{control_id}" in reasons
        for control_id in discrepancy_ids
    )


def test_08_sampling_weights_are_positive(sample_rows):
    assert all(float(row["sampling_weight"]) > 0 for row in sample_rows)


def test_09_sample_ids_are_unique(sample_rows):
    ids = [row["sample_id"] for row in sample_rows]
    assert len(ids) == len(set(ids))


def test_10_forward_results_have_no_duplicate_rows():
    results = _csv(RESULTS)
    assert len(results) == len({row["sample_id"] for row in results})
    assert len(results) == len({row["address_id"] for row in results})


def test_11_every_processed_result_has_an_allowed_status():
    assert {row["yandex_match_status"] for row in _csv(RESULTS)} <= ANALYZE.VALID_STATUSES


def test_12_non_deliverable_structures_do_not_enter_deliverable_estimate():
    assert not ANALYZE.eligible_for_deliverable_estimate("NON_DELIVERABLE_STRUCTURE")
    assert ANALYZE.eligible_for_deliverable_estimate("DELIVERABLE")


def test_13_organizations_do_not_create_separate_address_grains():
    base = BUILD.address_grain_key("Бендеры", "улица Титова", "80")
    organization_in_same_building = BUILD.address_grain_key("Бендеры", "улица Титова", "80")
    assert base == organization_in_same_building
    assert len([row for row in _csv(RESULTS) if row["address_id"] == "n11888388469"]) == 1


@pytest.mark.parametrize("source_type", ["garage", "garage box", "shed", "barn"])
def test_14_garages_and_sheds_are_not_deliverable(source_type):
    _, status, _, _ = BUILD.classify_source_object_type(source_type)
    assert status == "NON_DELIVERABLE_STRUCTURE"


def test_15_high_confidence_extras_are_absent_from_canonical_keys():
    canonical = {
        BUILD.address_grain_key(row["settlement_ru"], row["street_ru"], row["housenumber"])
        for row in json.loads(REGISTRY.read_text(encoding="utf-8"))["addresses"]
    }
    for row in _csv(EXTRAS):
        if row["confidence"] == "HIGH":
            key = BUILD.address_grain_key(row["territory"], row["street"], row["house_number"])
            assert row["present_in_our_database"] == "False"
            assert key not in canonical


def test_16_wilson_confidence_interval_is_correct():
    lower, upper = ANALYZE.wilson_interval(3, 3)
    assert lower == pytest.approx(0.4385029682)
    assert upper == pytest.approx(1.0)
    lower, upper = ANALYZE.wilson_interval(1, 2)
    assert lower == pytest.approx(0.0945312057)
    assert upper == pytest.approx(0.9054687943)


def test_17_partial_audit_cannot_be_complete(sample_rows):
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    assert checkpoint["complete"] is False
    assert not ANALYZE.audit_can_be_complete(len(sample_rows), 3, 3, 316, False)


def test_18_exact_yandex_total_requires_a_licensed_full_source():
    assert not ANALYZE.can_publish_exact_yandex_total(False)
    report_path = ROOT / "reports/yandex-address-inventory/final-address-count-estimate-v1.md"
    final_report = report_path.read_text(encoding="utf-8")
    assert "Estimated full normal Yandex address range | unavailable" in final_report


def test_19_zone_ids_and_polygons_are_unchanged():
    assert _normalized_hash(REGISTRY) == REGISTRY_SHA
    assert _normalized_hash(ROOT / "docs/data/final-zone-polygons.geojson") == (
        "cfc80697a7300890321319845704f1601f9a35317d80c99ec909d4be68e9db00"
    )


def test_20_routing_graph_inputs_and_provenance_are_unchanged():
    assert _normalized_hash(ROOT / "scripts/stage10d_graph.py") == (
        "d994a5d0da4a96e1d4f84e4eabbe5960b80d600cb1cf4b08a6ebbcbea47dc190"
    )
    assert _normalized_hash(ROOT / "docs/data/stage10d-graph-provenance.json") == (
        "da8e656b6f994d15c7df8f5cd839d79cc3b477955c0fb728ec849327b0de7c60"
    )


def test_21_direct_and_pricing_artifacts_are_unchanged():
    expected = {
        "config/bands.yml": "ebec96536b0f68ad8b2d41a9a04874dfd29acab56eec20f42a5e188ad00b6c8e",
        "docs/data/tariff-band-metrics.json": (
            "5a15d0086d4f04428e0cc3d8065ae120841040e7c31e707876484b1bf9eefd70"
        ),
        "docs/catalog.js": "b641541c24143c3936052013e4ecf89d97886137ffe0abd506dabc38b11b380e",
        "docs/app.js": "75d768c54c06acce22221b2847ade2c5094b73a1fda0061dde6ec8d89940df4f",
    }
    assert all(_normalized_hash(ROOT / path) == digest for path, digest in expected.items())


def test_22_immutable_releases_are_unchanged():
    digest = hashlib.sha256()
    files = sorted(path for path in (ROOT / "releases").rglob("*") if path.is_file())
    for path in files:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
        digest.update(b"\0")
    assert len(files) == 27
    assert digest.hexdigest() == "f6b666d433dab96d9c71c1a3567d6f9d95b30d07f3b9d7deff3dd05ee08748e2"
    assert BASE == "4a1c2a86b08e22f6a8d83ba8b5983a89f309e7b6"
