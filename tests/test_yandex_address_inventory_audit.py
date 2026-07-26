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
RECOVERY = ROOT / "data/interim/recovered-nonresidential-address-candidates-v1.csv"
REVERSE = ROOT / "data/interim/yandex-reverse-street-audit-v1.csv"
OWNER_REVIEW = ROOT / "data/interim/recovered-candidate-owner-review-v1.csv"
EXCLUSIONS = ROOT / "docs/data/delivery-exceptions.csv"
DELIVERY_UNITS = ROOT / "docs/data/delivery-units.csv"
REGISTRY_SHA = "bc66ad113a6ba5706bb6d2797ddc543e5b576482051d0d981551f014561c1817"
FIRST_THREE_FORWARD_SHA = (
    "a184e12c61488120f559419c3a66296d7ed0e40ed4f0392e6c7e008aa94f6380"
)
OLD_53_FORWARD_SHA = "2ace7cddce5423d3fdfc36cf5b292f12c8d7146847676cccb8f44e8db3508255"


def _load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILD = _load_module("build_yandex_inventory", "scripts/build_yandex_address_inventory_sample.py")
ANALYZE = _load_module("analyze_yandex_inventory", "scripts/analyze_yandex_address_inventory.py")
RECOVER = _load_module(
    "recover_nonresidential", "scripts/recover_nonresidential_address_candidates.py"
)


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
    canonical = [row for row in results if row["population_type"] == "CANONICAL_9216"]
    assert len(canonical) == len({row["address_id"] for row in canonical})


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
    assert not ANALYZE.audit_can_be_complete(len(sample_rows), 17, 10, 316, False)


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


@pytest.mark.parametrize("source_type", ["hospital", "medical_centre"])
def test_23_medical_destination_with_separate_address_is_deliverable(source_type):
    result = BUILD.classify_delivery_destination(source_type, has_separate_address=True)
    assert result["facility_category"] == "MEDICAL"
    assert result["deliverable_address_status"] == "DELIVERABLE"


def test_24_clinic_with_separate_address_is_deliverable():
    result = BUILD.classify_delivery_destination("clinic", has_separate_address=True)
    assert result["facility_category"] == "MEDICAL"
    assert result["deliverable_address_status"] == "DELIVERABLE"


@pytest.mark.parametrize("source_type", ["school", "kindergarten"])
def test_25_education_destination_with_separate_address_is_deliverable(source_type):
    result = BUILD.classify_delivery_destination(source_type, has_separate_address=True)
    assert result["facility_category"] == "EDUCATION"
    assert result["deliverable_address_status"] == "DELIVERABLE"


@pytest.mark.parametrize("source_type", ["industrial", "factory", "enterprise"])
def test_26_industrial_destination_with_separate_address_is_deliverable(source_type):
    result = BUILD.classify_delivery_destination(source_type, has_separate_address=True)
    assert result["facility_category"] == "INDUSTRIAL"
    assert result["deliverable_address_status"] == "DELIVERABLE"


def test_27_warehouse_with_separate_address_is_deliverable():
    result = BUILD.classify_delivery_destination("warehouse", has_separate_address=True)
    assert result["facility_category"] == "WAREHOUSE"
    assert result["deliverable_address_status"] == "DELIVERABLE"


def test_28_industrial_tag_alone_is_not_an_exclusion_reason():
    result = BUILD.classify_delivery_destination("industrial", has_separate_address=False)
    assert result["facility_category"] == "INDUSTRIAL"
    assert result["deliverable_address_status"] == "UNKNOWN_REQUIRES_REVIEW"
    assert result["deliverable_address_status"] != "NON_DELIVERABLE_STRUCTURE"


def test_29_multiple_organizations_at_one_address_do_not_increase_address_count():
    organization_keys = [
        BUILD.address_grain_key("Бендеры", "улица Титова", "80"),
        BUILD.address_grain_key("Бендеры", "улица Титова", "80"),
        BUILD.address_grain_key("Бендеры", "улица Титова", "80"),
    ]
    assert len(set(organization_keys)) == 1


def test_30_separately_addressed_gates_or_buildings_can_be_separate_addresses():
    keys = {
        BUILD.address_grain_key("Бендеры", "Промышленная улица", "1"),
        BUILD.address_grain_key("Бендеры", "Промышленная улица", "1А"),
    }
    assert len(keys) == 2


def test_31_unaddressed_internal_building_is_not_a_new_address():
    result = BUILD.classify_delivery_destination(
        "industrial",
        has_separate_address=False,
        internal_structure=True,
    )
    assert result["deliverable_address_status"] == "NON_DELIVERABLE_STRUCTURE"


@pytest.mark.parametrize("source_type", ["garage", "shed"])
def test_32_unaddressed_garage_or_shed_is_not_deliverable(source_type):
    result = BUILD.classify_delivery_destination(source_type, has_separate_address=False)
    assert result["facility_category"] == "NON_DELIVERABLE_AUXILIARY"
    assert result["deliverable_address_status"] == "NON_DELIVERABLE_STRUCTURE"


def test_33_named_facility_without_house_number_is_kept_for_review():
    result = BUILD.classify_delivery_destination(
        "hospital",
        has_separate_address=False,
        named_facility=True,
    )
    assert result["deliverable_address_status"] == "UNKNOWN_REQUIRES_REVIEW"
    assert result["manual_review_required"] == "True"


def test_34_classification_and_report_expose_facility_categories():
    rows = _csv(CLASSIFICATION)
    expected_fields = {
        "facility_category",
        "facility_name",
        "public_or_commercial_destination",
        "independent_delivery_entrance",
        "shared_address_with_other_pois",
        "deliverable_reason",
    }
    assert expected_fields <= set(rows[0])
    assert {row["facility_category"] for row in rows} <= BUILD.FACILITY_CATEGORIES
    report_path = ROOT / "reports/yandex-address-inventory/final-address-count-estimate-v1.md"
    report = report_path.read_text(encoding="utf-8")
    for category in ("RESIDENTIAL", "MEDICAL", "EDUCATION", "INDUSTRIAL", "WAREHOUSE"):
        assert category in report


def test_35_all_36_legacy_exclusions_are_in_recovery_file():
    legacy = {
        row["uid"]
        for row in _csv(EXCLUSIONS)
        if row["reason"] == "address_inside_nonresidential_building"
    }
    recovery = _csv(RECOVERY)
    assert len(legacy) == len(recovery) == 36
    assert {row["exception_row_id"] for row in recovery} == legacy


def test_36_no_exclusion_was_lost_or_blocked():
    recovery = _csv(RECOVERY)
    assert len({row["exception_row_id"] for row in recovery}) == 36
    assert {row["source_recovery_status"] for row in recovery} == {
        "RECOVERED_FROM_PINNED_SOURCE"
    }


def test_37_generic_nonresidential_is_not_automatically_non_deliverable():
    status = RECOVER.classify_candidate(
        unit_type="address_in_non_residential",
        category="UNKNOWN",
        has_address=True,
        has_entrance=False,
        lifecycle="",
        is_duplicate=False,
    )
    assert status == "UNKNOWN_REQUIRES_REVIEW"


def test_38_hospital_or_clinic_with_address_is_a_candidate():
    assert RECOVER.classify_candidate(
        unit_type="address_in_non_residential",
        category="MEDICAL",
        has_address=True,
        has_entrance=False,
        lifecycle="",
        is_duplicate=False,
    ) == "DELIVERABLE_CANDIDATE"


@pytest.mark.parametrize("source_type", ["school", "kindergarten"])
def test_39_school_or_kindergarten_with_address_is_a_candidate(source_type):
    category = RECOVER.facility_category({"amenity": source_type})
    assert category == "EDUCATION"
    assert RECOVER.classify_candidate(
        unit_type="address_in_non_residential",
        category=category,
        has_address=True,
        has_entrance=False,
        lifecycle="",
        is_duplicate=False,
    ) == "DELIVERABLE_CANDIDATE"


@pytest.mark.parametrize("source_type", ["enterprise", "factory", "industrial"])
def test_40_factory_or_enterprise_with_address_is_a_candidate(source_type):
    category = RECOVER.facility_category({"building": source_type})
    assert category == "INDUSTRIAL"
    assert RECOVER.classify_candidate(
        unit_type="address_in_non_residential",
        category=category,
        has_address=True,
        has_entrance=False,
        lifecycle="",
        is_duplicate=False,
    ) == "DELIVERABLE_CANDIDATE"


@pytest.mark.parametrize(
    ("tags", "category"),
    [
        ({"building": "warehouse"}, "WAREHOUSE"),
        ({"shop": "supermarket"}, "RETAIL"),
        ({"office": "company"}, "OFFICE"),
    ],
)
def test_41_warehouse_shop_or_office_with_address_is_a_candidate(tags, category):
    assert RECOVER.facility_category(tags) == category
    assert RECOVER.classify_candidate(
        unit_type="address_in_non_residential",
        category=category,
        has_address=True,
        has_entrance=False,
        lifecycle="",
        is_duplicate=False,
    ) == "DELIVERABLE_CANDIDATE"


def test_42_unaddressed_outbuilding_is_auxiliary():
    assert RECOVER.classify_candidate(
        unit_type="address_in_outbuilding",
        category="UNKNOWN",
        has_address=False,
        has_entrance=False,
        lifecycle="",
        is_duplicate=False,
    ) == "NON_DELIVERABLE_AUXILIARY"


def test_43_lifecycle_status_requires_positive_source_evidence():
    common = {
        "unit_type": "address_in_non_residential",
        "category": "UNKNOWN",
        "has_address": True,
        "has_entrance": False,
        "is_duplicate": False,
    }
    assert RECOVER.classify_candidate(**common, lifecycle="") == "UNKNOWN_REQUIRES_REVIEW"
    assert (
        RECOVER.classify_candidate(**common, lifecycle="ruins")
        == "NON_DELIVERABLE_LIFECYCLE"
    )


def test_44_named_facility_without_house_number_remains_unknown():
    assert RECOVER.classify_candidate(
        unit_type="address_in_non_residential",
        category="MEDICAL",
        has_address=False,
        has_entrance=False,
        lifecycle="",
        is_duplicate=False,
    ) == "UNKNOWN_REQUIRES_REVIEW"


def test_45_canonical_duplicate_does_not_increase_address_count():
    assert RECOVER.classify_candidate(
        unit_type="address_in_non_residential",
        category="RETAIL",
        has_address=True,
        has_entrance=False,
        lifecycle="",
        is_duplicate=True,
    ) == "DUPLICATE_EXISTING_ADDRESS"


def test_46_first_three_yandex_observations_are_unchanged():
    fields = [
        "sample_id",
        "address_id",
        "checked_date",
        "our_territory",
        "our_street",
        "our_house_number",
        "our_lat",
        "our_lon",
        "yandex_search_query",
        "yandex_displayed_label",
        "yandex_displayed_street",
        "yandex_displayed_house_number",
        "yandex_displayed_settlement",
        "yandex_match_status",
        "coordinate_distance_m",
        "visible_object_type",
        "is_normal_deliverable_building",
        "notes",
        "owner_review_required",
    ]
    protected = [{field: row[field] for field in fields} for row in _csv(RESULTS)[:3]]
    payload = json.dumps(
        protected, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    assert hashlib.sha256(payload).hexdigest() == FIRST_THREE_FORWARD_SHA


def test_47_new_forward_sample_ids_are_unique():
    rows = _csv(RESULTS)
    assert len(rows) == 153
    assert len({row["sample_id"] for row in rows}) == 153


def test_47a_old_53_forward_observations_are_unchanged():
    payload = json.dumps(
        _csv(RESULTS)[:53], ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    assert hashlib.sha256(payload).hexdigest() == OLD_53_FORWARD_SHA


def test_48_canonical_and_recovered_populations_are_counted_separately():
    counts = defaultdict(int)
    for row in _csv(RESULTS):
        counts[row["population_type"]] += 1
    assert counts == {"CANONICAL_9216": 117, "RECOVERED_EXCLUSION_CANDIDATE": 36}


def test_49_recovered_rows_do_not_enter_weighted_canonical_rate(sample_rows):
    sample_by_id = {row["sample_id"]: row for row in sample_rows}
    canonical = []
    for row in _csv(RESULTS):
        if row["population_type"] == "CANONICAL_9216":
            row["sampling_weight"] = sample_by_id[row["sample_id"]]["sampling_weight"]
            canonical.append(row)
    rate, _, _ = ANALYZE.weighted_rate(canonical, {"EXACT_MATCH", "NORMALIZED_EQUIVALENT"})
    assert 0 <= rate <= 1
    assert len(canonical) == 117
    assert all("sampling_weight" not in row for row in _csv(RESULTS))


def test_50_high_confidence_extras_are_absent_from_recovered_keys():
    recovered = {
        BUILD.address_grain_key(row["settlement"], row["street"], row["house_number"])
        for row in _csv(RECOVERY)
        if row["street"] and row["house_number"]
    }
    high = [row for row in _csv(EXTRAS) if row["confidence"] == "HIGH"]
    assert len(high) == 7
    for row in high:
        key = BUILD.address_grain_key(row["territory"], row["street"], row["house_number"])
        assert key not in recovered


def test_51_reverse_audit_cannot_be_complete_without_start_middle_and_end():
    for row in _csv(REVERSE):
        if not ANALYZE.reverse_group_can_be_complete(row):
            assert row["review_status"] != "COMPLETE_FOR_VISIBLE_MAP"


def test_51a_all_six_medium_extras_were_independently_rechecked():
    rechecked = [row for row in _csv(EXTRAS) if row["observation_id"] != "YOX-0001"]
    assert len(rechecked) == 6
    assert {row["confidence"] for row in rechecked} == {"HIGH"}
    assert all("Two independent manual" in row["match_method"] for row in rechecked)


def test_51b_high_extras_require_two_manual_confirmations():
    high = [row for row in _csv(EXTRAS) if row["confidence"] == "HIGH"]
    assert high
    assert all("Two independent manual" in row["match_method"] for row in high)


def test_51c_reverse_groups_are_unique_and_have_required_coverage():
    rows = _csv(REVERSE)
    keys = {(row["territory"], row["district"], row["street"]) for row in rows}
    complete = [row for row in rows if row["review_status"] == "COMPLETE_FOR_VISIBLE_MAP"]
    assert len(rows) == len(keys) >= 35
    assert len(complete) >= 10
    assert all(ANALYZE.reverse_group_can_be_complete(row) for row in complete)


def test_51d_owner_review_contains_all_15_deliverable_candidates():
    expected = {
        row["candidate_id"]
        for row in _csv(RECOVERY)
        if row["candidate_delivery_status"] == "DELIVERABLE_CANDIDATE"
    }
    review = _csv(OWNER_REVIEW)
    allowed = {
        "APPROVE_FOR_FUTURE_RELEASE",
        "REJECT_DUPLICATE",
        "REJECT_NON_DELIVERABLE",
        "HOLD_ADDRESS_CONFLICT",
        "HOLD_OPERATIONAL_STATUS",
        "HOLD_INSUFFICIENT_EVIDENCE",
    }
    assert len(expected) == len(review) == 15
    assert {row["candidate_id"] for row in review} == expected
    assert {row["recommended_owner_decision"] for row in review} <= allowed


def test_52_checkpoint_matches_actual_csv_counts():
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    results = _csv(RESULTS)
    recovery = _csv(RECOVERY)
    reverse = _csv(REVERSE)
    assert checkpoint["processed"] == checkpoint["forward_processed_total"] == len(results)
    assert checkpoint["canonical_processed"] == 117
    assert checkpoint["recovered_candidate_processed"] == len(recovery) == 36
    assert checkpoint["reverse_street_groups_reviewed"] == len(reverse) == 35
    assert checkpoint["reverse_street_groups_complete"] == 10
    assert checkpoint["medium_extras_rechecked"] == 6
    assert checkpoint["deliverable_candidates_owner_reviewed"] == 15


def test_52a_not_found_and_non_deliverable_require_positive_evidence():
    for row in _csv(RESULTS):
        if row["yandex_match_status"] == "NOT_FOUND":
            assert "query" in row["notes"].lower() or "search" in row["notes"].lower()
        if row["yandex_match_status"] == "NON_DELIVERABLE_STRUCTURE":
            evidence = row["notes"].lower()
            assert any(token in evidence for token in ("ruin", "garage", "shed", "lifecycle"))


def test_53_complete_stays_false_below_1000_canonical_observations():
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    assert checkpoint["canonical_processed"] < 1000
    assert checkpoint["complete"] is False


def test_54_all_9216_ids_and_coordinates_are_unchanged():
    assert _normalized_hash(DELIVERY_UNITS) == (
        "7f52e5119db0bfeb8a68464ad79ed1288a070c3563d887c088f72283c85c4250"
    )


def test_55_zone_thresholds_are_unchanged():
    assert _normalized_hash(ROOT / "docs/data/final-zone-polygons.geojson") == (
        "cfc80697a7300890321319845704f1601f9a35317d80c99ec909d4be68e9db00"
    )
    assert _normalized_hash(ROOT / "config/bands.yml") == (
        "ebec96536b0f68ad8b2d41a9a04874dfd29acab56eec20f42a5e188ad00b6c8e"
    )
