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
PROBABILITY_SAMPLE = ROOT / "data/interim/yandex-probability-sample-v1.csv"
PROBABILITY_LINKS = ROOT / "data/interim/yandex-probability-observations-v1.csv"
RECHECK = ROOT / "data/interim/yandex-canonical-conflict-recheck-v1.csv"
RECONCILIATION = ROOT / "data/interim/yandex-address-number-reconciliation-v1.csv"
RECONCILIATION_RECHECK = (
    ROOT / "data/interim/yandex-address-number-reconciliation-recheck-v1.csv"
)
EXCLUSIONS = ROOT / "docs/data/delivery-exceptions.csv"
DELIVERY_UNITS = ROOT / "docs/data/delivery-units.csv"
REGISTRY_SHA = "bc66ad113a6ba5706bb6d2797ddc543e5b576482051d0d981551f014561c1817"
FIRST_THREE_FORWARD_SHA = (
    "a184e12c61488120f559419c3a66296d7ed0e40ed4f0392e6c7e008aa94f6380"
)
OLD_53_FORWARD_SHA = "2ace7cddce5423d3fdfc36cf5b292f12c8d7146847676cccb8f44e8db3508255"
OLD_153_FORWARD_SHA = "c2c22da033082896a403cbf5669ff7891955dd935ba1aa2333b0b4fae6e4dec4"
OLD_253_FORWARD_SHA = "52c17e9976bfcb7179872c95f375b78b6fb945483e8a5ec739a569879ee8011e"
OLD_7_EXTRAS_SHA = "575f206c72519997b58cfa8a73ed820b67b9908ae35080b2a5f0f8be98277bb9"
OLD_35_REVERSE_SHA = "84ede575db75e8a322fc592d3d2601fbc525e83faf138e14da85c26a7c4b10b1"
OLD_60_REVERSE_SHA = "ddec018cab99f2705099e444cd433b954569f969ebb92d9c9781477f1473ac3a"
OLD_100_PROBABILITY_OBSERVATIONS_SHA = (
    "5cdd275aa347f2cdbbe0e21f40e922484de67cb7588e842d6d31a5c57616739e"
)
OLD_69_CONFLICT_RECHECKS_SHA = (
    "e4e26f7cdf15d0908bac118fceb4702abf2d8957d36f59c9049aa123a9cf16dd"
)
# Base reconciliation observations are immutable and pinned byte-for-byte to the
# parent commit 75544b3d9c65ddc279ecd55b1f36d8e7b58f56d2. Later rechecks live in
# an append-only overlay and never rewrite these seven rows.
BASE_RECONCILIATION_SHA = (
    "1c41f93ac2d346c851f2cd20f1ff3941641697e50d677959bbc62cb69ed8edce"
)
RECHECK_OVERLAY_SHA = (
    "dc047276fa6298cc5a1ff31282a92ce8b98f583a3a16264ab8695fbeda46a181"
)
# The first 143 reverse-street rows are frozen; new work may only be appended.
OLD_143_REVERSE_PREFIX_SHA = (
    "94d084550800e26ee470e0c4f63df7d35de6e951f2d5d17860c05de8369a1aa5"
)


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
PROBABILITY_BUILD = _load_module(
    "build_yandex_probability", "scripts/build_yandex_probability_sample.py"
)


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _normalized_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _rows_hash(rows: list[dict[str, str]]) -> str:
    payload = json.dumps(
        rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(payload).hexdigest()


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
    assert len(rows) == 420
    assert len({row["sample_id"] for row in rows}) == 420


def test_47a_old_53_forward_observations_are_unchanged():
    payload = json.dumps(
        _csv(RESULTS)[:53], ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    assert hashlib.sha256(payload).hexdigest() == OLD_53_FORWARD_SHA


def test_48_canonical_and_recovered_populations_are_counted_separately():
    counts = defaultdict(int)
    for row in _csv(RESULTS):
        counts[row["population_type"]] += 1
    assert counts == {"CANONICAL_9216": 384, "RECOVERED_EXCLUSION_CANDIDATE": 36}


def test_49_recovered_rows_do_not_enter_weighted_canonical_rate(sample_rows):
    sample_by_id = {row["sample_id"]: row for row in sample_rows}
    canonical = []
    for row in _csv(RESULTS):
        if row["population_type"] == "CANONICAL_9216" and row["sample_id"] in sample_by_id:
            row["sampling_weight"] = sample_by_id[row["sample_id"]]["sampling_weight"]
            canonical.append(row)
    positive = {"EXACT_MATCH", "NORMALIZED_EQUIVALENT"}
    numerator = sum(
        float(row["sampling_weight"])
        for row in canonical
        if row["yandex_match_status"] in positive
    )
    denominator = sum(float(row["sampling_weight"]) for row in canonical)
    expected_rate = numerator / denominator
    rate, _, _ = ANALYZE.weighted_rate(canonical, positive)
    assert numerator > 0
    assert denominator > numerator
    assert rate == pytest.approx(expected_rate)
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
    assert len(rows) == len(keys) >= 60
    assert len(complete) >= 25
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
    assert checkpoint["canonical_processed"] == 384
    assert checkpoint["recovered_candidate_processed"] == len(recovery) == 36
    assert checkpoint["reverse_street_groups_reviewed"] == len(reverse) == 143
    assert checkpoint["reverse_street_groups_complete"] == 25
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


def test_56_protected_153_forward_observations_are_unchanged():
    assert _rows_hash(_csv(RESULTS)[:153]) == OLD_153_FORWARD_SHA


def test_56a_protected_253_forward_observations_are_unchanged():
    assert _rows_hash(_csv(RESULTS)[:253]) == OLD_253_FORWARD_SHA


def test_57_protected_extras_and_reverse_prefix_are_unchanged():
    assert _rows_hash(_csv(EXTRAS)) == OLD_7_EXTRAS_SHA
    assert _rows_hash(_csv(REVERSE)[:35]) == OLD_35_REVERSE_SHA
    assert _rows_hash(_csv(REVERSE)[:60]) == OLD_60_REVERSE_SHA


def test_58_every_canonical_conflict_has_a_separate_recheck():
    conflict_statuses = {
        "DIFFERENT_HOUSE_NUMBER",
        "DIFFERENT_STREET",
        "NEARBY_ADDRESS_ONLY",
        "SETTLEMENT_ONLY",
        "AMBIGUOUS_REQUIRES_REVIEW",
        "NOT_FOUND",
    }
    expected = {
        row["sample_id"]
        for row in _csv(RESULTS)[:153]
        if row["population_type"] == "CANONICAL_9216"
        and row["yandex_match_status"] in conflict_statuses
    }
    rechecks = _csv(RECHECK)
    assert len(expected) == len(rechecks) == 69
    assert {row["original_sample_id"] for row in rechecks} == expected
    assert _rows_hash(rechecks) == OLD_69_CONFLICT_RECHECKS_SHA


def test_59_nearest_result_is_not_absence_confirmation():
    nearest = [
        row
        for row in _csv(RECHECK)
        if row["resolved_conflict_type"] == "YANDEX_NEAREST_RESULT_ONLY"
    ]
    assert nearest
    assert all(row["nearest_result_only"].lower() == "true" for row in nearest)
    assert all(
        row["requested_number_visible_anywhere"].lower() == "false" for row in nearest
    )


def test_60_settlement_or_not_found_recheck_has_two_queries_and_coordinate_review():
    rows = [
        row
        for row in _csv(RECHECK)
        if row["original_status"] in {"SETTLEMENT_ONLY", "NOT_FOUND"}
    ]
    assert rows
    assert all(" || " in row["second_search_query"] for row in rows)
    assert all(row["coordinate_click_label"] for row in rows)


def test_61_all_seven_high_extras_are_reconciled_to_canonical_rows():
    rows = _csv(RECONCILIATION)
    assert len(rows) == 7
    assert {row["yandex_observation_id"] for row in rows} == {
        row["observation_id"] for row in _csv(EXTRAS)
    }
    canonical_ids = {
        row["address_id"]
        for row in _csv(CLASSIFICATION)
    }
    assert all(row["nearest_canonical_address_id"] in canonical_ids for row in rows)


def test_62_reconciliation_checkpoint_separates_known_net_from_unresolved():
    base = _csv(RECONCILIATION)
    effective = ANALYZE.build_effective_reconciliations(base, _csv(RECONCILIATION_RECHECK))
    paired = [
        row for row in effective if row["net_inventory_effect"] == "ZERO_SUBSTITUTION"
    ]
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    assert len(paired) == checkpoint["paired_number_substitutions"] == 4
    assert checkpoint["gross_yandex_only_high"] == 7
    assert checkpoint["gross_canonical_only"] == 5
    assert checkpoint["unresolved_reconciliations"] == 1
    assert ANALYZE.provisional_net_inventory_difference(effective) == 2
    assert checkpoint["provisional_net_inventory_difference"] == 2


def test_62a_all_net_effect_values_have_the_required_sign():
    rows = [
        {"net_inventory_effect": "PLUS_ONE"},
        {"net_inventory_effect": "MINUS_ONE"},
        {"net_inventory_effect": "ZERO_SUBSTITUTION"},
        {"net_inventory_effect": "UNKNOWN"},
        {"net_inventory_effect": "UNRESOLVED"},
    ]
    assert ANALYZE.provisional_net_inventory_difference(rows) == 0
    assert ANALYZE.provisional_net_inventory_difference(rows[:1]) == 1
    assert ANALYZE.provisional_net_inventory_difference(rows[1:2]) == -1
    for row in rows[2:]:
        assert ANALYZE.provisional_net_inventory_difference([row]) == 0


def test_62b_reports_exclude_unresolved_rows_from_the_numeric_net():
    statement = (
        "Known provisional net effect: 2. One reconciliation remains unresolved "
        "and is excluded from the numeric net effect."
    )
    report_names = (
        "address-number-reconciliation-v1.md",
        "final-address-count-estimate-v1.md",
        "observed-extra-addresses-v1.md",
        "owner-decision-pack-v1.md",
    )
    for report_name in report_names:
        report = (ROOT / "reports/yandex-address-inventory" / report_name).read_text(
            encoding="utf-8"
        )
        assert statement in report


def test_62c_base_reconciliation_file_is_immutable_and_pinned():
    # Byte-for-byte identical to parent 75544b3; the seven observations are frozen.
    assert _normalized_hash(RECONCILIATION) == BASE_RECONCILIATION_SHA
    base = _csv(RECONCILIATION)
    assert len(base) == 7
    frozen = {row["reconciliation_id"]: row for row in base}
    for ynr in ("YNR-0001", "YNR-0002", "YNR-0004"):
        row = frozen[ynr]
        assert row["relationship_type"] == "UNRESOLVED"
        assert row["net_inventory_effect"] == "UNKNOWN"
        assert row["confidence"] == "LOW"


def test_62d_recheck_overlay_layer_is_append_only_and_well_formed():
    assert _normalized_hash(RECONCILIATION_RECHECK) == RECHECK_OVERLAY_SHA
    rechecks = _csv(RECONCILIATION_RECHECK)
    assert len(rechecks) == 3
    assert [r["recheck_id"] for r in rechecks] == ["RCK-0001", "RCK-0002", "RCK-0004"]
    assert len({r["recheck_id"] for r in rechecks}) == 3  # unique recheck ids
    base_by_id = {row["reconciliation_id"]: row for row in _csv(RECONCILIATION)}
    for r in rechecks:
        base = base_by_id[r["original_reconciliation_id"]]  # references existing base
        assert r["yandex_observation_id"] == base["yandex_observation_id"]


def test_62d1_rck0004_preserves_verbatim_pinned_source_flag():
    # Provenance: the relocated recheck must match commit 7493b2a byte-for-byte.
    # The original row carried yandex_number_present_in_pinned_source = False and
    # it must never be silently flipped without a fresh manual recheck.
    rck = {row["recheck_id"]: row for row in _csv(RECONCILIATION_RECHECK)}["RCK-0004"]
    assert rck["yandex_number_present_in_pinned_source"] == "False"
    assert rck["resolved_relationship_type"] == "UNRESOLVED"
    assert rck["resolved_net_inventory_effect"] == "UNKNOWN"
    assert rck["resolution_confidence"] == "LOW"


def test_62e_overlay_produces_seven_effective_rows_with_expected_effects():
    effective = ANALYZE.build_effective_reconciliations(
        _csv(RECONCILIATION), _csv(RECONCILIATION_RECHECK)
    )
    assert len(effective) == 7
    effects = [row["net_inventory_effect"] for row in effective]
    assert effects.count("PLUS_ONE") == 2
    assert effects.count("ZERO_SUBSTITUTION") == 4
    assert effects.count("UNKNOWN") == 1
    assert effects.count("MINUS_ONE") == 0
    assert ANALYZE.provisional_net_inventory_difference(effective) == 2
    unresolved = sum(row["relationship_type"] == "UNRESOLVED" for row in effective)
    assert unresolved == 1


def test_62f_overlay_never_mutates_the_base_rows():
    base = _csv(RECONCILIATION)
    snapshot = [dict(row) for row in base]
    ANALYZE.build_effective_reconciliations(base, _csv(RECONCILIATION_RECHECK))
    assert base == snapshot  # build must not mutate the immutable base observations


def test_62g_without_overlay_effective_result_collapses_to_the_base_state():
    # Proves the analytical +2 / unresolved=1 come from the overlay, not hard-coding.
    base = _csv(RECONCILIATION)
    effective = ANALYZE.build_effective_reconciliations(base, [])
    assert ANALYZE.provisional_net_inventory_difference(effective) == 0
    assert sum(row["relationship_type"] == "UNRESOLVED" for row in effective) == 3


def test_62h_overlay_rejects_duplicate_recheck_ids():
    base = _csv(RECONCILIATION)
    rechecks = _csv(RECONCILIATION_RECHECK)
    dup = rechecks + [dict(rechecks[0])]
    with pytest.raises(ValueError):
        ANALYZE.build_effective_reconciliations(base, dup)


def test_62i_overlay_rejects_unknown_original_reconciliation_id():
    base = _csv(RECONCILIATION)
    rechecks = _csv(RECONCILIATION_RECHECK)
    bad = [dict(rechecks[0], recheck_id="RCK-9999", original_reconciliation_id="YNR-9999")]
    with pytest.raises(ValueError):
        ANALYZE.build_effective_reconciliations(base, bad)


def test_62j_overlay_rejects_mismatched_yandex_observation_id():
    base = _csv(RECONCILIATION)
    rechecks = _csv(RECONCILIATION_RECHECK)
    bad = [dict(rechecks[0], yandex_observation_id="YOX-9999")]
    with pytest.raises(ValueError):
        ANALYZE.build_effective_reconciliations(base, bad)


def test_62k_checkpoint_exposes_overlay_bookkeeping_fields():
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    assert checkpoint["reconciliation_base_total"] == 7
    assert checkpoint["reconciliation_recheck_total"] == 3
    assert checkpoint["reconciliation_effective_total"] == 7
    assert checkpoint["reconciliation_overlay_applied"] is True
    assert checkpoint["reconciliation_effective_status_counts"] == {
        "PLUS_ONE": 2,
        "MINUS_ONE": 0,
        "ZERO_SUBSTITUTION": 4,
        "UNKNOWN": 1,
    }


def _reverse_prefix_hash(row_count: int) -> str:
    raw = REVERSE.read_bytes().replace(b"\r\n", b"\n")
    lines = raw.split(b"\n")
    prefix = b"\n".join(lines[: row_count + 1]) + b"\n"  # header + first N data rows
    return hashlib.sha256(prefix).hexdigest()


def test_62l_first_143_reverse_rows_are_frozen_prefix():
    rows = _csv(REVERSE)
    reviewed = len(rows)
    complete = sum(row["review_status"] == "COMPLETE_FOR_VISIBLE_MAP" for row in rows)
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    assert reviewed == checkpoint["reverse_street_groups_reviewed"] == 143
    assert complete == checkpoint["reverse_street_groups_complete"] == 25
    assert checkpoint["complete"] is False
    # The first 143 rows must stay byte-equivalent; new work may only be appended.
    assert _reverse_prefix_hash(143) == OLD_143_REVERSE_PREFIX_SHA


def test_63_probability_sample_is_reproducible_and_unique():
    rows = _csv(PROBABILITY_SAMPLE)
    assert len(rows) == len({row["address_id"] for row in rows}) == 400
    assert PROBABILITY_BUILD.build_probability_sample() == rows
    assert {row["selection_seed"] for row in rows} == {"20260727"}


def test_64_probability_weights_are_valid():
    for row in _csv(PROBABILITY_SAMPLE):
        probability = float(row["inclusion_probability"])
        assert 0 < probability <= 1
        assert float(row["sampling_weight"]) == pytest.approx(1 / probability)
        assert "yandex_match_status" not in row


def test_65_probability_observations_are_267_unique_canonical_rows():
    links = _csv(PROBABILITY_LINKS)
    forward = {row["sample_id"]: row for row in _csv(RESULTS)}
    assert len(links) == 267
    assert len({row["probability_sample_id"] for row in links}) == 267
    assert len({row["address_id"] for row in links}) == 267
    assert all(
        forward[row["forward_sample_id"]]["population_type"] == "CANONICAL_9216"
        for row in links
    )
    assert _rows_hash(links[:100]) == OLD_100_PROBABILITY_OBSERVATIONS_SHA


def test_65a_new_probability_batch_has_167_rows_and_sequential_ids():
    links = _csv(PROBABILITY_LINKS)[100:]
    forward = _csv(RESULTS)[253:]
    assert len(links) == len(forward) == 167
    assert [row["forward_sample_id"] for row in links] == [
        f"YAP-{index:04d}" for index in range(101, 268)
    ]
    assert [row["sample_id"] for row in forward] == [
        f"YAP-{index:04d}" for index in range(101, 268)
    ]


def test_65b_probability_review_design_is_derived_from_sample_and_links():
    sample = _csv(PROBABILITY_SAMPLE)
    links = _csv(PROBABILITY_LINKS)
    design = ANALYZE.probability_review_design(sample, links)
    independently_linked = sum(row["already_reviewed"] == "True" for row in sample)
    independently_eligible = len(sample) - independently_linked
    eligible_ids = [
        row["probability_sample_id"]
        for row in sample
        if row["already_reviewed"] == "False"
        and not row["linked_forward_sample_id"]
    ]
    actual_link_ids = [row["probability_sample_id"] for row in links]
    assert design["preexisting_linked"] == independently_linked == 33
    assert design["eligible_new"] == independently_eligible == 367
    assert design["new_random_batch_reviewed"] == len(links) == 267
    assert actual_link_ids == eligible_ids[: len(links)]
    assert design["new_random_batch_inclusion_probability"] == pytest.approx(
        len(links) / independently_eligible
    )
    assert design["second_phase_selection_rule"] == (
        "FIRST_N_ELIGIBLE_IN_FROZEN_SAMPLE_ORDER"
    )
    assert design["second_phase_batch_size"] == len(links) == 267


def test_65ba_replacing_one_link_with_another_eligible_id_is_rejected():
    sample = _csv(PROBABILITY_SAMPLE)
    links = [dict(row) for row in _csv(PROBABILITY_LINKS)]
    eligible_ids = [
        row["probability_sample_id"]
        for row in sample
        if row["already_reviewed"] == "False"
        and not row["linked_forward_sample_id"]
    ]
    links[-1]["probability_sample_id"] = eligible_ids[len(links)]
    with pytest.raises(ValueError, match="frozen eligible sample order"):
        ANALYZE.probability_review_design(sample, links)


def test_65bb_reordering_link_rows_is_rejected():
    sample = _csv(PROBABILITY_SAMPLE)
    links = [dict(row) for row in _csv(PROBABILITY_LINKS)]
    links[0], links[1] = links[1], links[0]
    with pytest.raises(ValueError, match="frozen eligible sample order"):
        ANALYZE.probability_review_design(sample, links)


def test_65bc_arbitrary_eligible_subset_is_rejected():
    sample = _csv(PROBABILITY_SAMPLE)
    links = [dict(row) for row in _csv(PROBABILITY_LINKS)]
    eligible_ids = [
        row["probability_sample_id"]
        for row in sample
        if row["already_reviewed"] == "False"
        and not row["linked_forward_sample_id"]
    ]
    handpicked_ids = eligible_ids[-len(links) :]
    for link, probability_sample_id in zip(links, handpicked_ids, strict=True):
        link["probability_sample_id"] = probability_sample_id
    with pytest.raises(ValueError, match="frozen eligible sample order"):
        ANALYZE.probability_review_design(sample, links)


def test_65c_all_reviewed_probability_rows_have_two_phase_weights():
    sample = _csv(PROBABILITY_SAMPLE)
    links = _csv(PROBABILITY_LINKS)
    reviewed = ANALYZE.probability_reviewed_rows(sample, links, _csv(RESULTS))
    assert len(reviewed) == 300
    assert {row["review_phase"] for row in reviewed} == {
        "PREEXISTING_LINKED",
        "NEW_RANDOM_BATCH",
    }
    for row in reviewed:
        first_probability = float(row["first_stage_inclusion_probability"])
        first_weight = float(row["first_stage_weight"])
        second_probability = float(row["second_phase_inclusion_probability"])
        assert first_weight == pytest.approx(1 / first_probability)
        if row["review_phase"] == "PREEXISTING_LINKED":
            assert second_probability == 1
        else:
            assert second_probability == pytest.approx(267 / 367)
        assert float(row["final_analysis_weight"]) == pytest.approx(
            first_weight / second_probability
        )


def test_65d_two_phase_hajek_rate_is_independently_recomputed_from_raw_rows():
    reviewed = ANALYZE.probability_reviewed_rows(
        _csv(PROBABILITY_SAMPLE), _csv(PROBABILITY_LINKS), _csv(RESULTS)
    )
    positive = {"EXACT_MATCH", "NORMALIZED_EQUIVALENT"}
    numerator = sum(
        float(row["final_analysis_weight"])
        for row in reviewed
        if row["yandex_match_status"] in positive
    )
    denominator = sum(float(row["final_analysis_weight"]) for row in reviewed)
    assert ANALYZE.two_phase_hajek_rate(reviewed, positive) == pytest.approx(
        numerator / denominator
    )
    assert ANALYZE.two_phase_hajek_rate(reviewed, positive) == pytest.approx(
        0.5197651199056238
    )
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    assert checkpoint["probability_two_phase_hajek_rate"] == pytest.approx(
        numerator / denominator
    )
    assert checkpoint["probability_interval_status"] == (
        "UNAVAILABLE_PENDING_LARGER_OR_COMPLETE_PROBABILITY_REVIEW"
    )
    assert checkpoint["probability_second_phase_selection_rule"] == (
        "FIRST_N_ELIGIBLE_IN_FROZEN_SAMPLE_ORDER"
    )
    assert checkpoint["probability_second_phase_batch_size"] == len(
        _csv(PROBABILITY_LINKS)
    )


def test_66_checkpoint_has_separate_population_and_probability_counts():
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    assert checkpoint["canonical_processed"] == 384
    assert checkpoint["forward_processed_total"] == 420
    assert checkpoint["probability_sample_total"] == 400
    assert checkpoint["probability_sample_reviewed"] == 300
    assert checkpoint["targeted_sample_reviewed"] == 117
    assert sum(checkpoint["canonical_status_counts"].values()) == 384
    assert sum(checkpoint["recovered_status_counts"].values()) == 36
    assert sum(checkpoint["combined_status_counts"].values()) == 420


def test_67_reverse_batch_has_required_complete_coverage():
    rows = _csv(REVERSE)
    complete = [row for row in rows if row["review_status"] == "COMPLETE_FOR_VISIBLE_MAP"]
    assert len(rows) == 143
    assert len(complete) >= 25
    assert all(ANALYZE.reverse_group_can_be_complete(row) for row in complete)
    assert all("start/25%/middle/75%/end" in row["segments_reviewed"] for row in complete[10:])


def test_68_owner_decision_pack_lists_all_required_recommendations():
    report = (ROOT / "reports/yandex-address-inventory/owner-decision-pack-v1.md").read_text(
        encoding="utf-8"
    )
    for candidate in ("REC-002", "REC-013", "REC-018", "REC-023", "REC-026", "REC-027"):
        assert candidate in report
    for index in range(1, 8):
        assert f"YOX-{index:04d}" in report or "YOX-0001` through `YOX-0007" in report


def test_69_audit_remains_partial_and_publishes_no_full_yandex_total():
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    report_path = ROOT / "reports/yandex-address-inventory/final-address-count-estimate-v1.md"
    report = report_path.read_text(encoding="utf-8")
    assert checkpoint["complete"] is False
    assert "INCONCLUSIVE / PARTIAL_EVIDENCE_ONLY" in report
    assert "Estimated full normal Yandex address range | unavailable" in report
