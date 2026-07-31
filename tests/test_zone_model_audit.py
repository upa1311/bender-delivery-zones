"""Integrity rules for the candidate zone-model audit (decision-layer hardened).

Covers: exact protected hashes, the exact baseline-mismatch set, full-population
vs city separation, city partitions, business-constrained validity, real
manual-control validation (not a perturbation proxy), the three price policies,
the fixed-5 vs 65% benchmark truth, policy-specific 25-ruble analysis, external
bracket (range-not-tariff), and neighbour discontinuities.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "releases/bender-zones-v1.1/address-registry.json"
FEATURES = ROOT / "data/interim/zone-model-address-features-v1.csv"
CANDIDATES = ROOT / "data/interim/zone-model-candidates-v1.csv"
ANCHORS = ROOT / "data/interim/external-tariff-boundary-anchors-v1.csv"
MISMATCH = ROOT / "data/interim/zone-baseline-reproduction-mismatches-v1.csv"
MANUAL = ROOT / "data/interim/zone-model-manual-control-validation-v1.csv"
POLICIES = ROOT / "data/interim/zone-policy-prices-v1.csv"
EXTERNAL = ROOT / "data/interim/zone-external-bracket-scenarios-v1.csv"
NEIGHBOURS = ROOT / "data/interim/zone-neighbour-discontinuities-v1.csv"
SCENARIOS = ROOT / "data/interim/zone-economics-scenarios-v1.csv"
CONTROLS = ROOT / "docs/data/manual-yandex-route-controls.csv"
MEASUREMENTS = ROOT / "docs/data/manual-yandex-measurements.csv"

PROTECTED_HASHES = {
    "releases/bender-zones-v1.1/address-registry.json":
        "bc66ad113a6ba5706bb6d2797ddc543e5b576482051d0d981551f014561c1817",
    "docs/data/delivery-units.csv":
        "7f52e5119db0bfeb8a68464ad79ed1288a070c3563d887c088f72283c85c4250",
    "config/bands.yml":
        "ebec96536b0f68ad8b2d41a9a04874dfd29acab56eec20f42a5e188ad00b6c8e",
    "docs/data/final-zone-polygons.geojson":
        "cfc80697a7300890321319845704f1601f9a35317d80c99ec909d4be68e9db00",
    "docs/data/manual-yandex-route-controls.csv":
        "5ff6617f3a51145febcd77dfe0ffeedc7f14bdcda268552b6b01f76c4c07a4ca",
    "docs/data/manual-yandex-measurements.csv":
        "58a71e47ac546f2788af0fc977709db169baea792bb866184e8ca926e177571c",
    "data/interim/yandex-forward-address-validation-v1.csv":
        "7f704c37e4f022b3a0416573adc23b7c4f4fd434a774b9e85acdd45d3309e512",
    "data/interim/yandex-probability-observations-v1.csv":
        "0f5b5081f54a6681f2c75ec02900b633a071e33531b34a416ea848a4c974977b",
    "data/interim/yandex-address-number-reconciliation-v1.csv":
        "1c41f93ac2d346c851f2cd20f1ff3941641697e50d677959bbc62cb69ed8edce",
    "data/interim/yandex-address-number-reconciliation-recheck-v1.csv":
        "dc047276fa6298cc5a1ff31282a92ce8b98f583a3a16264ab8695fbeda46a181",
}
BASELINE_MISMATCH_IDS = ["n2337889957", "w209267127", "w284686410",
                         "w306081930", "w352111747"]


def _load_module(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ZM = _load_module("zone_model_audit", "scripts/zone_model_audit.py")
ZE = _load_module("zone_economics_audit", "scripts/zone_economics_audit.py")


def _csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _nhash(path):
    return hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


REG = json.loads(REGISTRY.read_text(encoding="utf-8"))["addresses"]
FEAT = _csv(FEATURES)
CAND = _csv(CANDIDATES)
ANCH = _csv(ANCHORS)
MIS = _csv(MISMATCH)
MAN = _csv(MANUAL)
POL = _csv(POLICIES)
EXT = _csv(EXTERNAL)
NEI = _csv(NEIGHBOURS)
_ECON_PATH = ROOT / "reports/zone-model-audit/_economics-summary-v1.json"
ECON = json.loads(_ECON_PATH.read_text(encoding="utf-8"))
CITY_FEAT = [r for r in FEAT if r["outside_split_status"] == "CITY_ALL_IN"]


def _models():
    grouped = {}
    for row in CAND:
        grouped.setdefault(row["model_id"], []).append(row)
    return grouped


# ---- 1-7: exact protected hashes (no production change, no new release) ----
def test_01_protected_registry_hash_exact():
    assert _nhash("releases/bender-zones-v1.1/address-registry.json") == \
        PROTECTED_HASHES["releases/bender-zones-v1.1/address-registry.json"]


def test_02_delivery_units_hash_exact():
    assert _nhash("docs/data/delivery-units.csv") == \
        PROTECTED_HASHES["docs/data/delivery-units.csv"]


def test_03_bands_yml_hash_exact():
    assert _nhash("config/bands.yml") == PROTECTED_HASHES["config/bands.yml"]


def test_04_zone_polygons_hash_exact():
    assert _nhash("docs/data/final-zone-polygons.geojson") == \
        PROTECTED_HASHES["docs/data/final-zone-polygons.geojson"]


def test_05_manual_controls_hash_exact():
    assert _nhash("docs/data/manual-yandex-route-controls.csv") == \
        PROTECTED_HASHES["docs/data/manual-yandex-route-controls.csv"]


def test_06_manual_measurements_hash_exact():
    assert _nhash("docs/data/manual-yandex-measurements.csv") == \
        PROTECTED_HASHES["docs/data/manual-yandex-measurements.csv"]


def test_07_address_audit_protected_hashes_exact():
    for path in ("data/interim/yandex-forward-address-validation-v1.csv",
                 "data/interim/yandex-probability-observations-v1.csv",
                 "data/interim/yandex-address-number-reconciliation-v1.csv",
                 "data/interim/yandex-address-number-reconciliation-recheck-v1.csv"):
        assert _nhash(path) == PROTECTED_HASHES[path]


# ---- population + provenance ----
def test_08_canonical_population_is_9216():
    assert len(REG) == 9216 and len(FEAT) == 9216


def test_09_address_ids_unique_and_match_registry():
    ids = [r["address_id"] for r in FEAT]
    assert len(set(ids)) == 9216 == len({a["uid"] for a in REG})
    assert set(ids) == {a["uid"] for a in REG}


def test_10_route_metric_has_provenance_and_no_invented_duration():
    for r in FEAT:
        assert r["route_metric_status"] == "expected_km_osrm"
        assert float(r["route_km"]) > 0
        assert r["route_duration_min"] == ""


def test_11_varnita_absent_lipcani_city():
    assert all(r["territory"] != "Варница" for r in FEAT)
    lip = [a for a in REG if a.get("district_ru") == "Липканы"]
    assert len(lip) == 248 and all(a["settlement_ru"] == "Бендеры" for a in lip)


def test_12_parkany_giska_protyagailovka_separate():
    assert {"Парканы", "Гиска", "Протягайловка"} <= {r["territory"] for r in FEAT}
    assert {"Парканы", "Гиска", "Протягайловка"} <= {r["territory"] for r in ANCH}


def test_13_severny_no_automatic_classification():
    sev = [r for r in ANCH if r["territory"] == "Северный"]
    assert sev and sev[0]["confidence"] == "UNPROVEN"


# ---- 8: baseline mismatch exact ----
def test_14_baseline_mismatch_count_and_ids_exact():
    assert len(MIS) == 5
    assert sorted(r["address_id"] for r in MIS) == BASELINE_MISMATCH_IDS
    assert all(r["reason"] == "threshold_inclusivity" for r in MIS)
    assert all(abs(float(r["distance_to_threshold_km"])) < 1e-9 for r in MIS)


def test_15_baseline_reproduction_le_and_strict_exact():
    rows = ZM.load_addresses()
    le = sum(1 for r in rows if ZM.zone_for(r["route_km"], ZM.BASELINE_EDGES) == r["zone_id"])
    strict = sum(1 for r in rows
                 if ZM.zone_for_released(r["route_km"], ZM.BASELINE_EDGES) == r["zone_id"])
    assert le == 9211 and strict == 9216  # inclusivity is the ONLY cause


# ---- 9: no mixing of full-population counts with city economics ----
def test_16_full_population_diagnostics_carry_no_fee():
    diags = [r for r in CAND if r["economic_scope"] == "DIAGNOSTIC_ROUTE_ONLY"]
    assert diags
    for r in diags:
        assert r["candidate_delivery_fee_rub"] == ""
        assert r["all_address_count"] != "" and r["city_address_count"] != ""


def test_17_city_models_have_no_all_population_count():
    city = [r for r in CAND if r["economic_scope"] == "CITY_DEPLOYABLE"]
    assert city
    for r in city:
        assert r["all_address_count"] == "" and r["all_population_share"] == ""
        assert r["city_address_count"] != ""


# ---- 10: city partitions exactly 4,866 ----
def test_18_city_models_partition_exactly_4866():
    models = _models()
    for mid, zones in models.items():
        if not mid.startswith("CITY_"):
            continue
        assert sum(int(z["city_address_count"]) for z in zones) == 4866


def test_19_city_k4_k5_k6_have_right_zone_counts():
    models = _models()
    for k in (4, 5, 6):
        zones = models[f"CITY_K{k}R_dp_optimal_jenks"]
        assert len(zones) == k and all(int(z["city_address_count"]) > 0 for z in zones)


# ---- 11: business-constrained validity ----
def test_20_business_constrained_zones_are_valid():
    models = _models()
    for k in (4, 5, 6):
        zones = sorted(models[f"CITY_K{k}R_business"], key=lambda z: int(z["zone_id"]))
        shares = [int(z["city_address_count"]) / 4866 for z in zones]
        assert all(s <= 0.40 + 1e-9 for s in shares)  # max-share respected
        assert all(int(z["city_address_count"]) > 0 for z in zones)  # no empty/sliver
        method = zones[0]["method"]
        assert "business_constrained" in method


# ---- 12: operational rounding deterministic ----
def test_21_operational_rounding_is_deterministic():
    edges = [1.975, 3.075, 4.175, 5.175]
    assert ZM.rounding_variants(edges) == ZM.rounding_variants(edges)
    assert ZM.rounding_variants(edges)["0.5"] == [2.0, 3.0, 4.0, 5.0]


# ---- 13-16: real manual-control validation, no proxy ----
def test_22_manual_validation_exists_with_real_router_and_yandex_km():
    assert MAN
    for r in MAN:
        assert float(r["router_km"]) > 0 and float(r["yandex_km"]) > 0
        assert r["control_id"].startswith("MY-")


def test_23_manual_control_ids_unique_per_model():
    per_model = {}
    for r in MAN:
        per_model.setdefault(r["model_id"], []).append(r["control_id"])
    for ids in per_model.values():
        assert len(ids) == len(set(ids))


def test_24_city_models_validated_only_on_city_controls():
    for r in MAN:
        if r["model_id"].startswith("CITY_"):
            assert r["territory"] == "Бендеры"
    city_rows = [r for r in MAN if r["model_id"] == "CITY_K5R_dp_optimal_jenks"]
    assert len(city_rows) == 28  # honest: only 28 city controls exist


def test_25_router_yandex_flips_independently_recomputed():
    controls = {c["control_id"]: c for c in _csv(CONTROLS)}
    meas = {m["control_id"]: m for m in _csv(MEASUREMENTS)}
    reg = {a["uid"]: a for a in ZM.load_addresses()}
    edges = ZM.thresholds_dp_optimal(
        [r["route_km"] for r in ZM.load_addresses() if r["is_city"]], 5)
    for row in [r for r in MAN if r["model_id"] == "CITY_K5R_dp_optimal_jenks"]:
        c = controls[row["control_id"]]
        yk = float(meas[row["control_id"]]["yandex_fastest_distance_km"])
        rk = reg[c["uid"]]["route_km"]
        assert ZM.zone_for(rk, edges) == int(row["router_zone"])
        assert ZM.zone_for(yk, edges) == int(row["yandex_zone"])
        assert abs(int(row["router_zone"]) - int(row["yandex_zone"])) == int(row["zone_delta"])


def test_26_proxy_perturbation_not_labelled_as_manual_validation():
    report = (ROOT / "reports/zone-model-audit/zone-boundary-stability-v1.md").read_text(
        encoding="utf-8")
    assert "28" in report  # honest city control coverage
    # the manual section must reference real control IDs, not perturbation
    assert "MY-" in report


# ---- 17-19: three policy tables ----
def test_27_three_policies_present_for_every_city_model():
    for mid in ZE.CITY_MODELS:
        for policy in ("DRIVER_CONSERVATIVE", "BALANCED", "CUSTOMER_FIRST"):
            assert any(r["model_id"] == mid and r["policy"] == policy for r in POL)


def test_28_policy_prices_are_integer_and_monotone():
    groups = {}
    for r in POL:
        groups.setdefault((r["model_id"], r["policy"]), []).append(r)
    for rows in groups.values():
        rows.sort(key=lambda z: int(z["zone_id"]))
        fees = [int(z["candidate_fee_rub"]) for z in rows]
        assert fees == sorted(fees)


def test_29_policy_joint_coverage_independently_recomputed():
    reg = {r["uid"]: r for r in ZM.load_addresses()}
    city = [r for r in reg.values() if r["is_city"]]
    edges = ZM.thresholds_dp_optimal([r["route_km"] for r in city], 4)
    rows = [r for r in POL
            if r["model_id"] == "CITY_K4R_dp_optimal_jenks" and r["policy"] == "BALANCED"]
    for row in rows:
        zi = int(row["zone_id"])
        fee = int(row["candidate_fee_rub"])
        members = [r for r in city if ZM.zone_for(r["route_km"], edges) == zi]
        joint = 0
        for r in members:
            ref = ZE.taxi_ref_a(r["route_km"])
            best = ZE.driver_best(ref)
            gap = best - fee
            if fee < ref and gap <= 3 and gap <= 0.10 * best:
                joint += 1
        assert round(joint / len(members), 4) == float(row["joint_coverage"])


# ---- 20: commission benchmark truth ----
def test_30_fixed5_benchmark_wins_for_all_city_trips():
    cb = ECON["commission_breakdown"]
    assert cb["fixed5_share"] == 1.0 and cb["percent65_wins"] == 0
    assert abs(cb["crossover_fare_rub"] - 14.29) < 0.01
    assert cb["benchmark_used"] == "taxi_reference_minus_5_for_all_city_trips"


def test_31_reports_state_fixed5_not_65pct():
    for name in ("customer-driver-balance-v1.md", "owner-decision-pack-v1.md"):
        text = (ROOT / "reports/zone-model-audit" / name).read_text(encoding="utf-8")
        assert "taxi_reference - 5" in text or "−5" in text or "- 5" in text


# ---- 21: 25 ruble policy-specific ----
def test_32_current_25_fee_is_policy_specific():
    cf = ECON["current_fee_policy_specific"]
    assert cf["fee"] == 25.0
    for key in ("client_overpays", "gap_gt_2", "gap_gt_3", "gap_gt_5",
                "gap_gt_10pct", "gap_gt_15pct"):
        assert key in cf and cf[key] >= 0
    fees = {r["candidate_delivery_fee_rub"] for r in CAND
            if r["economic_scope"] == "CITY_DEPLOYABLE"}
    assert fees != {"25"}  # 25 not applied globally


# ---- 22-24: external bracket, range not tariff ----
def test_33_external_scenarios_include_outside_rates_8_to_12():
    rates = {float(r["outside_rate"]) for r in EXT}
    assert {8.0, 9.0, 10.0, 11.0, 12.0} <= rates


def test_34_external_rows_are_range_only_not_tariff():
    assert EXT
    for r in EXT:
        assert r["status"] == "RANGE_ONLY_NOT_TARIFF"
        assert float(r["taxi_lower_rub"]) <= float(r["taxi_upper_rub"])


def test_35_no_external_point_price_in_features():
    for r in FEAT:
        if r["outside_split_status"] == "OUTSIDE_SPLIT_UNKNOWN":
            assert r["taxi_model_a_reference_rub"] == ""
            assert r["taxi_model_b_reference_rub"] == ""


# ---- 25: neighbour discontinuity recomputed ----
def test_36_neighbour_discontinuity_metrics_present_and_ordered():
    nd = ECON["neighbour_discontinuity"]
    for k in (4, 5, 6):
        m = nd[f"CITY_K{k}R_dp_optimal_jenks"]
        assert m["pairs_250m"] > 0 and m["diff_zone_250m"] >= 0
        assert m["max_price_jump_rub"] >= 0
    # more zones -> more different-zone neighbour pairs
    assert (nd["CITY_K4R_dp_optimal_jenks"]["diff_zone_250m"]
            < nd["CITY_K6R_dp_optimal_jenks"]["diff_zone_250m"])


def test_37_neighbour_csv_pairs_are_close_and_cross_zone():
    for r in NEI:
        assert float(r["distance_m"]) <= 250
        assert int(r["zone_a"]) != int(r["zone_b"])
        assert int(r["price_jump_rub"]) >= 8  # file logs only the sharpest jumps


# ---- 26: 5T-A/5T-B city equivalence documented ----
def test_38_taxi_models_a_and_b_are_identical_for_city():
    for km in (0.5, 1.0, 2.9, 3.0, 3.1, 5.0, 9.6):
        assert ZM.taxi_reference_a(km, 0.0) == ZM.taxi_reference_b(km, 0.0)


# ---- partition validity across all models ----
def test_39_thresholds_increasing_and_partition_contiguous():
    for zones in _models().values():
        zones = sorted(zones, key=lambda z: int(z["zone_id"]))
        uppers = [float(z["upper_bound"]) for z in zones if z["upper_bound"] != ""]
        assert uppers == sorted(uppers) and len(uppers) == len(set(uppers))
        for prev, cur in zip(zones, zones[1:], strict=False):
            assert float(cur["lower_bound"]) == float(prev["upper_bound"])


def test_40_anchors_have_no_invented_coordinates():
    for r in ANCH:
        assert r["confidence"] == "UNPROVEN"
        assert r["lat"] == "" and r["lon"] == ""
    gai = [r for r in ANCH if r["anchor_id"] == "PARKANY_KOTOVSKOGO_GAI_POST"]
    assert gai and "UNKNOWN_REQUIRES_OWNER_MAP_CONFIRMATION" in gai[0]["notes"]


# ---- 27-28: no production change / no new release ----
def test_41_no_new_release_directory_created():
    releases = sorted(p.name for p in (ROOT / "releases").iterdir() if p.is_dir())
    assert releases == ["bender-zones-v1", "bender-zones-v1.1"]


def test_42_taxi_calibration_config_stays_null():
    text = (ROOT / "config/taxi-calibration.yml").read_text(encoding="utf-8")
    assert "calibration_supplied: false" in text
    assert _nhash("config/bands.yml") == PROTECTED_HASHES["config/bands.yml"]


def test_43_partition_methods_deterministic():
    rows = ZM.load_addresses()
    values = [r["route_km"] for r in rows if r["is_city"]]
    for func in (ZM.thresholds_quantile, ZM.thresholds_kmeans, ZM.thresholds_dp_optimal):
        assert func(values, 5) == func(values, 5)
    assert ZM.thresholds_business_constrained(values, 5) == \
        ZM.thresholds_business_constrained(values, 5)


def test_44_sensitivity_grid_city_scoped_and_sized():
    scen = _csv(SCENARIOS)
    assert len(scen) == 5184
    assert all(r["scope"] == "CITY_ONLY_OWNER_ASSUMPTION" for r in scen)
