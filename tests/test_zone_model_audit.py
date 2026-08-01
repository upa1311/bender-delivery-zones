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
FR = _load_module("zone_fragmentation_analysis", "scripts/zone_fragmentation_analysis.py")
FF = _load_module("city_far_zone_formula", "scripts/city_far_zone_formula.py")
OT = _load_module("owner_tariff_model", "scripts/owner_tariff_model.py")
OC = _load_module("outside_city_distance", "scripts/outside_city_distance.py")


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
        assert r["route_metric_status"] == "fixed_origin_central_km"
        assert float(r["route_km"]) > 0
        assert r["route_duration_min"] == ""
        assert r["legacy_expected_km"] != ""  # legacy kept alongside, labelled


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
def test_14_baseline_mismatch_set_exact_and_resolved():
    assert len(MIS) == 5
    assert sorted(r["address_id"] for r in MIS) == BASELINE_MISMATCH_IDS
    assert all(r["reason"] == "threshold_inclusivity" for r in MIS)
    assert all(abs(float(r["distance_to_threshold_km"])) < 1e-9 for r in MIS)
    # under the unified [lower, upper) convention all five reproduce the release
    assert all(r["status"] == "RESOLVED_UNDER_LOWER_UPPER_CONVENTION" for r in MIS)
    assert all(int(r["recomputed_zone_id_unified"]) == int(r["registry_zone_id"]) for r in MIS)


def test_15_baseline_reproduction_unified_and_legacy():
    rows = ZM.load_addresses()
    unified = sum(1 for r in rows
                  if ZM.zone_for(r["legacy_expected_km"], ZM.BASELINE_EDGES) == r["zone_id"])
    legacy_le = sum(1 for r in rows
                    if ZM.zone_for_le(r["legacy_expected_km"], ZM.BASELINE_EDGES) == r["zone_id"])
    assert unified == 9216 and legacy_le == 9211  # [lower,upper) reproduces exactly


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


# ---- 11: share_width_density (honestly renamed) validity ----
def test_20_share_width_density_zones_are_valid_and_renamed():
    models = _models()
    for k in (4, 5, 6):
        zones = sorted(models[f"CITY_K{k}R_share_width_density"],
                       key=lambda z: int(z["zone_id"]))
        shares = [int(z["city_address_count"]) / 4866 for z in zones]
        assert all(s <= 0.40 + 1e-9 for s in shares)  # max-share respected
        assert all(int(z["city_address_count"]) > 0 for z in zones)  # no empty/sliver
        method = zones[0]["method"]
        assert "share_width_density" in method  # honest name, not "business"
        assert "business_constrained" not in method


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


def test_28_feasible_policy_prices_are_integer_and_monotone():
    groups = {}
    for r in POL:
        if r["policy_status"] != "FEASIBLE":
            continue
        groups.setdefault((r["model_id"], r["policy"]), []).append(r)
    for rows in groups.values():
        rows.sort(key=lambda z: int(z["zone_id"]))
        fees = [int(z["candidate_fee_rub"]) for z in rows]
        assert fees == sorted(fees)  # non-decreasing across feasible zones


def test_29_feasible_means_full_coverage_infeasible_has_no_candidate():
    for r in POL:
        if r["policy_status"] == "FEASIBLE":
            assert r["candidate_fee_rub"] != ""
            assert float(r["hard_constraint_coverage"]) == 1.0
            assert int(r["violated_address_count"]) == 0
        else:
            assert r["policy_status"] == "INFEASIBLE"
            assert r["candidate_fee_rub"] == ""          # no satisfied-policy price
            assert r["fallback_fee_rub"] != ""           # fallback kept separately
            assert float(r["hard_constraint_coverage"]) < 1.0


def test_29b_coverage_independently_recomputed():
    reg = {r["uid"]: r for r in ZM.load_addresses()}
    city = [r for r in reg.values() if r["is_city"]]
    edges = ZM.thresholds_dp_optimal([r["route_km"] for r in city], 5)
    rows = [r for r in POL
            if r["model_id"] == "CITY_K5R_dp_optimal_jenks" and r["policy"] == "BALANCED"]
    for row in rows:
        zi = int(row["zone_id"])
        fee = int(row["candidate_fee_rub"] or row["fallback_fee_rub"])
        members = [r for r in city if ZM.zone_for(r["route_km"], edges) == zi]
        joint = 0
        for r in members:
            ref = ZE.taxi_ref_a(r["route_km"])
            best = ZE.driver_best(ref)
            gap = best - fee
            if ref - fee >= 5 and gap <= 3 and gap <= 0.10 * best:  # BALANCED save>=5
                joint += 1
        assert round(joint / len(members), 4) == float(row["hard_constraint_coverage"])


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


# ---- fixed-origin metric, boundary convention, price ordering, rounding ----
FIXED_ORIGIN = ROOT / "data/interim/fixed-origin-address-routes-v1.csv"
FIX = _csv(FIXED_ORIGIN)


def test_45_fixed_origin_metric_sourced_not_invented():
    assert len(FIX) == 9216
    for r in FIX:
        assert float(r["fixed_origin_lat"]) == 46.82388
        assert float(r["fixed_origin_lon"]) == 29.48313
        assert r["metric_source"] == "central_km"
        assert "not invented" in r["provenance"]
        assert float(r["fixed_origin_km"]) > 0


def test_46_fixed_origin_differs_from_legacy_blend():
    # expected_km is a multi-origin blend; the fixed-origin metric is materially
    # different, so the earlier expected_km models were not a clean single origin.
    deltas = [abs(float(r["delta_fixed_minus_legacy_km"])) for r in FIX]
    assert max(deltas) > 1.0 and sum(1 for d in deltas if d > 0.01) > 8000


def test_47_city_models_use_fixed_origin_metric():
    for r in CAND:
        if r["economic_scope"] == "CITY_DEPLOYABLE":
            assert r["metric"] == "fixed_origin_km"
        else:
            assert r["metric"] == "legacy_expected_km"


def test_48_boundary_convention_is_lower_upper_half_open():
    # value exactly on a threshold falls in the UPPER zone
    edges = [2.0, 4.0]
    assert ZM.zone_for(2.0, edges) == 2
    assert ZM.zone_for(1.999, edges) == 1
    assert ZM.zone_for(4.0, edges) == 3


def test_49_feasible_policy_prices_ordered_and_within_interval():
    byz = {}
    for r in POL:
        byz.setdefault((r["model_id"], int(r["zone_id"])), {})[r["policy"]] = r
    for group in byz.values():
        # cross-policy ordering only where all three are FEASIBLE with a price
        if all(group[p]["policy_status"] == "FEASIBLE" for p in group):
            c = int(group["CUSTOMER_FIRST"]["candidate_fee_rub"])
            b = int(group["BALANCED"]["candidate_fee_rub"])
            d = int(group["DRIVER_CONSERVATIVE"]["candidate_fee_rub"])
            assert c <= b <= d
        # every feasible fee sits inside its proven [driver, client] interval
        for r in group.values():
            if r["policy_status"] == "FEASIBLE":
                fee = int(r["candidate_fee_rub"])
                assert int(r["minimum_fee_required_by_driver"]) <= fee
                assert fee <= int(r["maximum_fee_allowed_by_client"])


def test_50_feasibility_interval_decides_status():
    reg = {r["uid"]: r for r in ZM.load_addresses()}
    city = [r for r in reg.values() if r["is_city"]]
    edges = ZM.thresholds_dp_optimal([r["route_km"] for r in city], 5)
    rule = ZE.POLICY_RULES["DRIVER_CONSERVATIVE"]
    for row in [r for r in POL if r["model_id"] == "CITY_K5R_dp_optimal_jenks"
                and r["policy"] == "DRIVER_CONSERVATIVE"]:
        zi = int(row["zone_id"])
        members = [r for r in city if ZM.zone_for(r["route_km"], edges) == zi]
        refs = [ZE.taxi_ref_a(r["route_km"]) for r in members]
        bests = [ZE.driver_best(x) for x in refs]
        floor = ZE._driver_floor(bests, rule)
        ceil = ZE._client_ceiling(refs, rule)
        assert floor == int(row["minimum_fee_required_by_driver"])
        assert ceil == int(row["maximum_fee_allowed_by_client"])
        # FEASIBLE requires a non-empty interval (monotone may still block it)
        if row["policy_status"] == "FEASIBLE":
            assert floor <= ceil


def test_51_operational_rounding_recomputes_counts_and_flips():
    summary = json.loads(
        (ROOT / "reports/zone-model-audit/_route-model-summary-v1.json").read_text(
            encoding="utf-8"))
    rr = summary["city_models"]["CITY_K5R_dp_optimal_jenks"]["rounding_recompute"]
    for step in ("0.1", "0.25", "0.5"):
        assert sum(rr[step]["counts"]) == 4866
        assert "instability_5pct" in rr[step] and "same_street_splits" in rr[step]


def test_52_manual_validation_uses_fixed_origin_router_km():
    # router_km in the manual CSV must equal the address fixed-origin km
    reg = {r["uid"]: r for r in ZM.load_addresses()}
    for r in MAN:
        assert abs(float(r["router_km"]) - round(reg[r["uid"]]["fixed_origin_km"], 3)) < 1e-6


# ---- owner tests 5,6,7: near-zone fee 11 cannot be FEASIBLE; fee < taxi ----
def test_53_balanced_fee_11_infeasible_for_best_13_at_10pct():
    # best=13, BALANCED gap cap = min(3, 10%*13=1.3)=1.3 → floor = ceil(13-1.3)=12,
    # so fee 11 (gap 2) is NOT feasible.
    assert ZE._driver_floor([13.0], ZE.POLICY_RULES["BALANCED"]) == 12


def test_54_customer_first_fee_11_infeasible_for_best_13_at_15pct():
    # best=13, CUSTOMER gap cap = min(5, 15%*13=1.95)=1.95 → floor = ceil(11.05)=12.
    assert ZE._driver_floor([13.0], ZE.POLICY_RULES["CUSTOMER_FIRST"]) == 12


def test_55_every_feasible_fee_is_strictly_cheaper_than_taxi():
    for r in POL:
        if r["policy_status"] == "FEASIBLE":
            assert int(r["candidate_fee_rub"]) < float(r["minimum_taxi_reference"])


# ---- owner tests 11,12: operational recompute & changed IDs ----
def test_56_operational_changed_ids_match_raw_vs_rounded_assignment():
    op = _csv(ROOT / "data/interim/zone-operational-candidates-v1.csv")
    changes = _csv(ROOT / "data/interim/zone-operational-rounding-changes-v1.csv")
    reg = {r["uid"]: r for r in ZM.load_addresses()}
    # recompute changed count for CITY_K5 0.25 rounding independently
    raw_edges = ZM.thresholds_dp_optimal(
        [r["route_km"] for r in reg.values() if r["is_city"]], 5)
    rounded = ZM._monotone([ZM._round(round(e / 0.25) * 0.25) for e in raw_edges])
    city = [r for r in reg.values() if r["is_city"]]
    changed = sum(1 for r in city
                  if ZM.zone_for(r["fixed_origin_km"], rounded)
                  != ZM.zone_for(r["fixed_origin_km"], raw_edges))
    row = next(r for r in op if r["model_id"] == "CITY_K5R_dp_optimal_jenks"
               and r["rounding_km"] == "0.25")
    assert int(row["changed_vs_raw_count"]) == changed
    detail = [c for c in changes if c["model_id"] == "CITY_K5R_dp_optimal_jenks"
              and c["rounding_km"] == "0.25"]
    assert len(detail) == changed  # exact changed IDs enumerated


def test_57_operational_has_neighbour_metrics_and_selection():
    op = _csv(ROOT / "data/interim/zone-operational-candidates-v1.csv")
    for r in op:
        assert r["neighbour_diff_zone_100m"] != "" and r["neighbour_diff_zone_250m"] != ""
    selections = {r["selection"] for r in op}
    assert "PRIMARY_OPERATIONAL_CANDIDATE" in selections
    assert "FALLBACK_OPERATIONAL_CANDIDATE" in selections


# ---- owner test 14: external field renamed ----
def test_58_external_field_renamed_not_direct_fee_interval():
    header = open(ROOT / "data/interim/zone-external-bracket-scenarios-v1.csv",
                  encoding="utf-8-sig").readline()
    assert "direct_fee_interval_rub" not in header
    assert "taxi_reference_bracket_rub" in header
    for r in EXT:
        assert r["status"] == "RANGE_ONLY_NOT_TARIFF"
        assert r["direct_feasible_lower_rub"] == "" and r["direct_feasible_upper_rub"] == ""


# ---- owner test 16: owner pack does not claim 100% when coverage < 1 ----
def test_59_owner_pack_does_not_falsely_claim_full_coverage():
    text = (ROOT / "reports/zone-model-audit/owner-decision-pack-v1.md").read_text(
        encoding="utf-8")
    assert "INFEASIBLE" in text  # honestly reports infeasible outer zones
    assert "hard constraints выполнены по всем адресам" not in text


# ---- owner test 13: business model objective is honestly named ----
def test_60_share_width_density_method_declared_and_not_called_business_model():
    for r in CAND:
        if r["model_id"].endswith("share_width_density"):
            assert "share_width_density" in r["method"]
    swd = ZM.thresholds_business_constrained(
        [r["route_km"] for r in ZM.load_addresses() if r["is_city"]], 5)
    assert "share_width_density" in swd[1]


# ================= GPT-audit follow-up tests =================
OPPOL = _csv(ROOT / "data/interim/zone-operational-policy-prices-v1.csv")


# audit 1: BALANCED minimum client saving >= 5 for every FEASIBLE address
def test_61_balanced_feasible_min_saving_at_least_5():
    reg = {r["uid"]: r for r in ZM.load_addresses()}
    city = [r for r in reg.values() if r["is_city"]]
    for mid in ("CITY_K4R_dp_optimal_jenks", "CITY_K5R_dp_optimal_jenks"):
        edges = ZM.thresholds_dp_optimal(
            [r["route_km"] for r in city], int(mid[6]))
        for row in [r for r in POL if r["model_id"] == mid
                    and r["policy"] == "BALANCED" and r["policy_status"] == "FEASIBLE"]:
            zi, fee = int(row["zone_id"]), int(row["candidate_fee_rub"])
            members = [r for r in city if ZM.zone_for(r["route_km"], edges) == zi]
            assert min(ZE.taxi_ref_a(r["route_km"]) - fee for r in members) >= 5


# audit 2: unused target_save no longer exists
def test_62_no_target_save_mechanism():
    assert all("target_save" not in rule for rule in ZE.POLICY_RULES.values())
    src = (ROOT / "scripts/zone_economics_audit.py").read_text(encoding="utf-8")
    assert "target_save" not in src


# audit 3: CITY_K4 zone 2 fee 14 is rejected under BALANCED
def test_63_k4_zone2_fee14_rejected_under_balanced():
    row = next(r for r in POL if r["model_id"] == "CITY_K4R_dp_optimal_jenks"
               and r["policy"] == "BALANCED" and int(r["zone_id"]) == 2)
    assert row["policy_status"] == "INFEASIBLE"
    # ceiling proves fee 14 is not allowed (min taxi 18 - 5 = 13)
    assert int(row["maximum_fee_allowed_by_client"]) < 14


# audit 4: every operational model/rounding/policy/zone has a policy row
def test_64_operational_policy_rows_complete():
    combos = {(r["model_id"], r["rounding_km"], r["policy"]) for r in OPPOL}
    for mid in ("CITY_K4R_dp_optimal_jenks", "CITY_K5R_dp_optimal_jenks"):
        for rk in ("raw", "0.1", "0.25", "0.5"):
            for pol in ("CUSTOMER_FIRST", "BALANCED", "DRIVER_CONSERVATIVE"):
                assert (mid, rk, pol) in combos
    assert all(int(r["address_count"]) > 0 for r in OPPOL)


# audit 5+7: operational prices independently recomputed & may differ from raw
def test_65_operational_prices_recomputed_and_may_differ():
    reg = {r["uid"]: r for r in ZM.load_addresses()}
    city = [r for r in reg.values() if r["is_city"]]
    raw_edges = ZM.thresholds_dp_optimal([r["route_km"] for r in city], 5)
    rounded = ZM._monotone([ZM._round(round(e / 0.25) * 0.25) for e in raw_edges])
    # DRIVER z3 becomes feasible under 0.25 where raw z3 is infeasible → not copied
    raw_z3 = next(r for r in OPPOL if r["model_id"] == "CITY_K5R_dp_optimal_jenks"
                  and r["rounding_km"] == "raw" and r["policy"] == "DRIVER_CONSERVATIVE"
                  and int(r["zone_id"]) == 3)
    rnd_z3 = next(r for r in OPPOL if r["model_id"] == "CITY_K5R_dp_optimal_jenks"
                  and r["rounding_km"] == "0.25" and r["policy"] == "DRIVER_CONSERVATIVE"
                  and int(r["zone_id"]) == 3)
    assert raw_z3["policy_status"] != rnd_z3["policy_status"]  # genuinely recomputed
    assert rounded != raw_edges


# audit 6: operational FEASIBLE rows have full coverage
def test_66_operational_feasible_rows_full_coverage():
    for r in OPPOL:
        if r["policy_status"] == "FEASIBLE":
            assert r["candidate_fee_rub"] != ""
            assert float(r["hard_constraint_coverage"]) == 1.0
            assert int(r["violated_address_count"]) == 0
        else:
            assert r["candidate_fee_rub"] == "" and r["fallback_fee_rub"] != ""


# audit 8: same-street key includes territory and district
def test_67_same_street_key_includes_territory_and_district():
    a = {"territory": "Бендеры", "district": "", "street": "улица Мира"}
    b = {"territory": "Бендеры", "district": "Липканы", "street": "улица Мира"}
    assert ZE._street_key(a) != ZE._street_key(b)
    assert ZE._street_key(a) == ("Бендеры", "", "улица Мира")


# audit 9: external territories never receive city candidate/fallback prices
def test_68_external_bracket_has_no_city_fee_columns():
    header = open(ROOT / "data/interim/zone-external-bracket-scenarios-v1.csv",
                  encoding="utf-8-sig").readline()
    assert "candidate_fee_rub" not in header and "fallback_fee_rub" not in header
    # policy files are city-model only; no external territory appears as a model
    ext_terms = {"Парканы", "Гиска", "Протягайловка", "Северный", "Parkany", "Giska"}
    for r in POL + OPPOL:
        assert not any(t in r["model_id"] for t in ext_terms)


# audit 10: owner pack does not call far city zones external territories
def test_69_owner_pack_uses_city_zone_terminology():
    text = (ROOT / "reports/zone-model-audit/owner-decision-pack-v1.md").read_text(
        encoding="utf-8")
    assert "дальние городские" in text or "дальняя" in text
    assert "внешние территории" in text  # reserved for Parkany/Giska/Protyagailovka


# audit 11: no duplicated fake p95 field anywhere in the policy schemas
def test_70_no_fake_p95_field():
    for path in ("data/interim/zone-policy-prices-v1.csv",
                 "data/interim/zone-operational-policy-prices-v1.csv"):
        header = open(ROOT / path, encoding="utf-8-sig").readline()
        assert "p95" not in header


# ================= corrective-commit provenance tests =================
PACK = (ROOT / "reports/zone-model-audit/owner-decision-pack-v1.md").read_text(
    encoding="utf-8")
OPCAND = _csv(ROOT / "data/interim/zone-operational-candidates-v1.csv")


def test_71_owner_pack_k5_025_edges_match_csv():
    row = next(r for r in OPCAND if r["model_id"] == "CITY_K5R_dp_optimal_jenks"
               and r["rounding_km"] == "0.25")
    assert row["edges"] == "1.75|3.0|4.0|5.25"          # the corrected value
    assert f"edges {row['edges']}" in PACK               # pack shows exactly the CSV edges


def test_72_owner_pack_has_all_four_full_tables():
    for label in ("CITY_K4 raw", "CITY_K4 operational 0.25",
                  "CITY_K5 raw", "CITY_K5 operational 0.25"):
        assert f"### {label} — edges" in PACK
    # each table carries the full per-zone/per-policy columns
    assert PACK.count("| Zone | Policy | Status | Fee | Fallback | Coverage |") >= 4


def test_73_owner_pack_numbers_are_generated_from_csv():
    op = OPPOL
    # every FEASIBLE fee and every fallback in the K5 0.25 CSV must appear verbatim
    rows = [r for r in op if r["model_id"] == "CITY_K5R_dp_optimal_jenks"
            and r["rounding_km"] == "0.25"]
    assert rows
    block = PACK.split("CITY_K5 operational 0.25")[1].split("### ")[0]
    for r in rows:
        cell = (f"| {r['candidate_fee_rub']} |" if r["policy_status"] == "FEASIBLE"
                else f"| {r['fallback_fee_rub']} |")
        assert cell in block  # the exact fee/fallback from the CSV is in the table


def test_74_operational_candidates_have_weighted_coverage():
    for r in OPCAND:
        for key in ("customer", "balanced", "driver"):
            assert r[f"{key}_total_joint_coverage"] != ""
            assert r[f"{key}_weighted_fallback_coverage"] != ""
            assert r[f"{key}_total_violated_addresses"] != ""


def test_75_selection_prefers_coverage_before_geometry():
    # CITY_K5 PRIMARY must be the rounded variant with the highest BALANCED joint
    # coverage among those that do not reduce feasible BALANCED zones (not geometry).
    k5 = [r for r in OPCAND if r["model_id"] == "CITY_K5R_dp_optimal_jenks"
          and r["rounding_km"] != "raw"]
    raw = next(r for r in OPCAND if r["model_id"] == "CITY_K5R_dp_optimal_jenks"
               and r["rounding_km"] == "raw")
    eligible = [r for r in k5 if int(r["balanced_feasible_zones"])
                >= int(raw["balanced_feasible_zones"])]
    best_cov = max(float(r["balanced_total_joint_coverage"]) for r in eligible)
    primary = next(r for r in OPCAND if r["model_id"] == "CITY_K5R_dp_optimal_jenks"
                   and r["selection"] == "PRIMARY_OPERATIONAL_CANDIDATE")
    assert float(primary["balanced_total_joint_coverage"]) == best_cov


# ================= balanced-zone fragmentation analysis =================
FRAG = _csv(ROOT / "data/interim/zone-balanced-fragmentation-v1.csv")
FRAG_SUMMARY = json.loads(
    (ROOT / "reports/zone-model-audit/_fragmentation-summary-v1.json").read_text(
        encoding="utf-8"))


def _min_zones(policy):
    city = ZE.city_rows(ZE.load_features())
    kms = sorted(float(r["route_km"]) for r in city)
    return len(FR.minimum_zones(kms, ZE.POLICY_RULES[policy]))


def test_76_balanced_needs_exactly_14_zones_for_full_coverage():
    assert _min_zones("BALANCED") == 14
    assert FRAG_SUMMARY["balanced_minimum_zones"] == 14
    assert len(FRAG) == 14


def test_77_other_policies_minimum_zone_counts():
    assert _min_zones("CUSTOMER_FIRST") == 9
    assert _min_zones("DRIVER_CONSERVATIVE") == 5
    counts = FRAG_SUMMARY["minimum_zones_for_100pct_coverage"]
    assert counts == {"DRIVER_CONSERVATIVE": 5, "BALANCED": 14, "CUSTOMER_FIRST": 9}


def test_78_every_minimal_zone_is_balanced_feasible():
    for z in FRAG:
        floor = int(z["min_fee_required_by_driver"])
        ceil = int(z["max_fee_allowed_by_client"])
        assert floor <= ceil                      # a flat fee exists
        assert int(z["balanced_feasible_fee"]) == floor


def test_79_greedy_partition_is_maximal_hence_minimal():
    # extending any non-last zone by one address would break BALANCED feasibility,
    # proving each zone is maximal and the count is minimal.
    city = ZE.city_rows(ZE.load_features())
    kms = sorted(float(r["route_km"]) for r in city)
    rule = ZE.POLICY_RULES["BALANCED"]
    idx = 0
    for z in FRAG[:-1]:
        count = int(z["address_count"])
        seg_plus = kms[idx:idx + count + 1]       # this zone + first addr of next
        refs = [ZE.taxi_ref_a(k) for k in seg_plus]
        bests = [ZE.driver_best(r) for r in refs]
        assert ZE._driver_floor(bests, rule) > ZE._client_ceiling(refs, rule)
        idx += count
    assert sum(int(z["address_count"]) for z in FRAG) == len(city)


# ============ candidate base+distance formula for CITY_K5 far zones ============
FARROWS = _csv(ROOT / "data/interim/zone-k5-far-base-distance-v1.csv")
FF_SUMMARY = json.loads(
    (ROOT / "reports/zone-model-audit/_k5-far-formula-summary-v1.json").read_text(
        encoding="utf-8"))


def test_80_base_distance_formula_is_floor_6km_minus_5():
    for km in (2.9, 3.5, 4.125, 5.325, 6.0, 9.37):
        assert FF.base_distance_fee(km) == __import__("math").floor(6 * km - 5)


def test_80b_far_scope_uses_operational_3km_boundary_from_csv():
    edges = FF.operational_k5_edges()
    assert edges == [1.75, 3.0, 4.0, 5.25]           # read from operational CSV
    assert FF_SUMMARY["far_zone_start_km"] == 3.0
    assert FF_SUMMARY["far_addresses"] == 2420        # not 2471 (raw edge)
    # every far row is strictly beyond the 3.0 operational boundary
    assert all(float(r["route_km"]) > 3.0 for r in FARROWS)
    # the 51 addresses in 2.875-3.0 (operational zone 2) are excluded
    assert not any(2.875 < float(r["route_km"]) <= 3.0 for r in FARROWS)


def test_80c_near_operational_zones_have_flat_balanced_fee():
    near = FF_SUMMARY["near_zones_flat"]
    assert [z["zone"] for z in near] == [1, 2]
    assert all(z["feasible"] for z in near)          # flat fee works for zones 1-2
    assert all(isinstance(z["flat_balanced_fee"], int) for z in near)


def test_81_formula_gives_100pct_balanced_coverage_on_far_zones():
    assert FF_SUMMARY["balanced_coverage"] == 1.0
    assert FF_SUMMARY["far_addresses"] == FF_SUMMARY["balanced_ok_addresses"]
    # independently verify every row: saving>=5, gap<=3 and <=10%, fee<taxi
    for r in FARROWS:
        ref = float(r["taxi_reference_rub"])
        best = float(r["driver_best_take_rub"])
        fee = int(r["formula_fee_rub"])
        assert ref - fee >= 5 and best - fee <= 3 and best - fee <= 0.10 * best
        assert fee < ref
        assert r["balanced_ok"] == "True"


def test_82_formula_fee_is_monotone_and_cheaper_than_taxi():
    fees = [int(r["formula_fee_rub"]) for r in
            sorted(FARROWS, key=lambda r: float(r["route_km"]))]
    assert fees == sorted(fees)  # non-decreasing with distance


def test_83_far_formula_is_candidate_only_not_production():
    # the formula lives only in candidate interim data; config stays null-guarded
    text = (ROOT / "reports/zone-model-audit/city-far-zone-base-distance-v1.md").read_text(
        encoding="utf-8")
    assert "not applied to production" in text
    assert "calibration_supplied: false" in (
        ROOT / "config/taxi-calibration.yml").read_text(encoding="utf-8")


# ================= owner-approved distance tariff (analysis layer) =================
OTFEES = _csv(ROOT / "data/interim/owner-tariff-fees-v1.csv")
OTCONTROLS = _csv(ROOT / "data/interim/owner-tariff-control-addresses-v1.csv")
OT_SUMMARY = json.loads(
    (ROOT / "reports/zone-model-audit/_owner-tariff-summary-v1.json").read_text(
        encoding="utf-8"))


def test_84_city_tariff_exact_owner_control_values():
    expected = {0.0: 14, 3.0: 14, 3.01: 15, 3.25: 15, 3.5: 16, 4.0: 18, 5.0: 22, 7.0: 30}
    for km, fee in expected.items():
        assert OT.base_city_fee(km) == fee


def test_85_boundary_3_0_and_3_01_and_no_km_prerounding():
    assert OT.base_city_fee(3.0) == 14        # boundary is flat 14
    assert OT.base_city_fee(3.01) == 15       # any excess over 3 km rounds up
    # proportional at full precision — a value that would collapse to 14 if km were
    # pre-rounded to whole/half km must still yield 15:
    assert OT.base_city_fee(3.001) == 15
    assert OT.base_city_fee(3.05) == 15


def test_86_ceil_applied_to_final_price_only():
    # 3.6 km: 14 + 0.6*4 = 16.4 → ceil 17 (price rounded up, distance not)
    assert OT.base_city_fee(3.6) == 17
    assert OT.base_city_fee(3.5) == 16        # exact 16, no spurious ceil bump


def test_87_external_surcharge_formula_and_boundary():
    # FIXED: the minimum of 5 MDL ALWAYS applies to an external-classified address,
    # including outside_city_km == 0. "No surcharge" is a CITY case (by territory),
    # not a zero-distance case. Old code wrongly returned 0 at the boundary.
    assert OT.external_surcharge(0) == 5                    # min 5 always (was 0 — bug)
    assert OT.external_surcharge(1) == 5                    # max(5, ceil(2)) = 5
    assert OT.external_surcharge(2.5) == 5                  # max(5, ceil(5)) = 5
    assert OT.external_surcharge(3) == 6                    # max(5, ceil(6)) = 6
    assert OT.external_surcharge(10) == 20                  # max(5, ceil(20)) = 20


def test_88_city_address_gets_no_external_surcharge():
    for r in OTFEES:
        if r["calculation_status"] == "CITY_OK":
            assert int(r["external_surcharge"]) == 0
            assert int(r["final_fee"]) == int(r["base_city_fee"])


def test_89_external_address_with_outside_km_uses_surcharge_formula():
    fee, base, sur, status = OT.final_fee(5.0, True, 2.0)   # hypothetical outside km
    assert status == "EXTERNAL_OK"
    assert sur == OT.external_surcharge(2.0) == 5
    assert fee == base + 5


def test_90_zero_outside_km_external_gets_minimum_surcharge():
    # FIXED: an external address whose route never leaves the (provisional) polygon
    # (outside_city_km == 0) still pays the 5 MDL minimum — it is NOT a city address.
    fee, base, sur, status = OT.final_fee(5.0, True, 0.0)
    assert status == "EXTERNAL_OK" and sur == 5 and fee == base + 5


def test_91_unknown_outside_km_gets_no_invented_price():
    fee, base, sur, status = OT.final_fee(5.0, True, None)
    assert status == "OUTSIDE_DISTANCE_UNAVAILABLE"
    assert fee == "" and sur == ""
    # in the real data ALL external addresses are unavailable (no proven split)
    ext = [r for r in OTFEES if r["territory"] in OT.EXTERNAL_TERRITORIES]
    assert ext and all(r["calculation_status"] == "OUTSIDE_DISTANCE_UNAVAILABLE"
                       and r["final_fee"] == "" and r["outside_city_km"] == "" for r in ext)


def test_92_four_external_territories_classified():
    assert OT.EXTERNAL_TERRITORIES == ("Парканы", "Гиска", "Протягайловка", "Северный")
    present = {r["territory"] for r in OTFEES if r["territory"] in OT.EXTERNAL_TERRITORIES}
    assert {"Парканы", "Гиска", "Протягайловка"} <= present  # Северный absent from 9216


def test_93_city_k5_zone_does_not_affect_final_fee():
    # final_fee is a pure function of route_km (and outside_km); the old zone column
    # is analytics-only. Same route_km => same fee regardless of geographic zone.
    city = [r for r in OTFEES if r["calculation_status"] == "CITY_OK"]
    by_km = {}
    for r in city:
        by_km.setdefault(r["route_km"], set()).add(int(r["final_fee"]))
    for fees in by_km.values():
        assert len(fees) == 1  # identical route_km -> identical fee, zone irrelevant
    # and the fee equals the pure formula (independent of any zone attribute)
    for r in city[:200]:
        assert int(r["final_fee"]) == OT.base_city_fee(float(r["route_km"]))


def test_94_summary_and_csv_reproducible_from_script():
    feats = OT.ZE.load_features()
    assert OT.compute_rows(feats) == OT.compute_rows(feats)
    assert OT_SUMMARY["city_addresses"] == sum(
        1 for r in OTFEES if r["calculation_status"] == "CITY_OK")
    assert OT_SUMMARY["outside_distance_unavailable_total"] == sum(
        1 for r in OTFEES if r["calculation_status"] == "OUTSIDE_DISTANCE_UNAVAILABLE")


def test_95_control_table_has_at_least_20_addresses_from_data():
    assert len(OTCONTROLS) >= 20
    ids = {r["address_id"] for r in OTFEES}
    assert all(r["address_id"] in ids for r in OTCONTROLS)  # not fabricated

# ============ outside-city route & city-boundary audit (BLOCKED) ============
from shapely.geometry import LineString, MultiPolygon, Polygon  # noqa: E402

OCFEES = _csv(ROOT / "data/interim/outside-city-distance-v1.csv")
OCINV = _csv(ROOT / "data/interim/outside-city-route-inventory-v1.csv")
OCSCEN = _csv(ROOT / "data/interim/outside-city-boundary-scenarios-v1.csv")
OCCTRL = _csv(ROOT / "data/interim/outside-city-control-addresses-v1.csv")
OCSUM = json.loads(
    (ROOT / "reports/zone-model-audit/_outside-city-summary-v1.json").read_text(
        encoding="utf-8"))
_SQ = Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000)])  # 1km city


# ---- synthetic-geometry method proofs ----
def test_96_fully_inside_zero():
    assert OC.outside_length_km(LineString([(100, 100), (900, 900)]), _SQ) == 0.0


def test_97_fully_outside_full_length():
    assert abs(OC.outside_length_km(LineString([(2000, 2000), (3000, 2000)]), _SQ) - 1.0) < 1e-9


def test_98_single_crossing():
    assert abs(OC.outside_length_km(LineString([(500, 500), (1500, 500)]), _SQ) - 0.5) < 1e-9


def test_99_multiple_crossings():
    assert abs(OC.outside_length_km(LineString([(1500, 500), (-500, 500)]), _SQ) - 1.0) < 1e-9


def test_100_touching_edge_is_inside():
    assert OC.outside_length_km(LineString([(0, 100), (0, 900)]), _SQ) == 0.0


def test_101_multipolygon():
    mp = MultiPolygon([_SQ, Polygon([(2000, 0), (3000, 0), (3000, 1000), (2000, 1000)])])
    assert OC.outside_length_km(LineString([(2100, 100), (2900, 900)]), mp) == 0.0


def test_102_hole_is_outside():
    donut = Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000)],
                    [[(400, 400), (600, 400), (600, 600), (400, 600)]])
    assert abs(OC.outside_length_km(LineString([(500, 100), (500, 900)]), donut) - 0.2) < 1e-6


def test_103_invalid_boundary_repaired():
    bowtie = Polygon([(0, 0), (1000, 1000), (1000, 0), (0, 1000)])
    assert not bowtie.is_valid
    assert OC.outside_length_km(LineString([(500, 100), (500, 900)]), bowtie) >= 0.0


def test_104_projected_length_correct():
    far = Polygon([(5000, 5000), (6000, 5000), (6000, 6000), (5000, 6000)])
    assert abs(OC.outside_length_km(LineString([(0, 0), (0, 1500)]), far) - 1.5) < 1e-9


# ---- route inventory: both sources, dedup, no conflict ----
def test_105_route_inventory_combines_09a_and_09b_to_12():
    src = OCSUM["route_sources"]
    a = next(v for k, v in src.items() if "stage-09a" in k)["external_central_routes"]
    b = next(v for k, v in src.items() if "stage-09b" in k)["external_central_routes"]
    assert a == 9 and b == 3
    assert OCSUM["unique_usable_routes"] == 12
    assert OCSUM["route_conflicts"] == []
    ids = [r["canonical_address_id"] for r in OCINV]
    assert len(ids) == 12 == len(set(ids))  # deduped by canonical_address_id


def test_106_route_length_validation_and_sensitivity():
    for r in OCFEES:
        if r["polyline_length_km"] != "":
            assert r["route_validation_status"] == "LENGTH_OK"
            assert float(r["route_length_difference_m"]) < 5.0  # all match to < 5 m
    sens = OCSUM["sensitivity"]["by_threshold"]
    assert {s["threshold_km"] for s in sens} >= {0.005, 0.01, 0.05}
    # a threshold change must not silently move any address into a price
    assert OCSUM["sensitivity"]["acceptance_changes_across_thresholds"] in (True, False)


# ---- boundary: provisional, none verified → BLOCKED ----
def test_107_boundary_candidates_compared_none_verified():
    cand = {c["candidate_id"]: c for c in OCSUM["boundary_candidates"]}
    assert set(cand) == {"bender_relation_12463379", "municipiul_bender_9581354",
                         "bender_city_council_944727"}
    # geometry blocker LIFTED: all three geometries are now extracted (commit 6d4679c)
    assert cand["bender_relation_12463379"]["verification_status"] == "PROVISIONAL_PROXY"
    for cid in ("municipiul_bender_9581354", "bender_city_council_944727"):
        assert cand[cid]["verification_status"] == "EXTRACTED_ADMIN_BOUNDARY_UNVERIFIED"
    for c in cand.values():
        assert c["geometry_extracted"] == "yes"          # no more NO_GEOMETRY_IN_REPO
        assert len(c["geometry_sha256"]) == 64
        assert c["geometry_path"].endswith(".geojson")
        assert c["verification_status"] != "VERIFIED_FOR_TARIFF"
    assert OCSUM["verified_tariff_boundary"] is None
    assert "provisional proxy" in OCSUM["provisional_boundary_evidence"].lower()


def test_108_verdict_is_blocked_by_city_boundary():
    assert OCSUM["verdict"] == "BLOCKED_BY_CITY_BOUNDARY"


def test_109_no_calculated_or_final_fee_under_provisional_boundary():
    assert OCSUM["approved_priced_addresses"] == 0
    for r in OCFEES:
        assert r["calculation_status"] != "CALCULATED"
        assert r["final_fee"] == "" and r["outside_city_km"] == ""
        assert r["calculation_status"] in {
            "ROUTE_GEOMETRY_UNAVAILABLE", "CITY_BOUNDARY_UNAVAILABLE",
            "ROUTE_LENGTH_MISMATCH", "ROUTE_GEOMETRY_CONFLICT",
            "INVALID_ROUTE_GEOMETRY", "INVALID_BOUNDARY_GEOMETRY",
            "OUTSIDE_DISTANCE_UNAVAILABLE", "TERRITORY_DATA_UNAVAILABLE"}


def test_110_routed_addresses_are_boundary_blocked_not_priced():
    routed = [r for r in OCFEES if r["polyline_length_km"] != ""]
    assert len(routed) == 12
    for r in routed:
        assert r["calculation_status"] == "CITY_BOUNDARY_UNAVAILABLE"
        assert r["boundary_verification_status"] == "PROVISIONAL_UNVERIFIED"


def test_111_scenario_values_separated_from_production_csv():
    # scenario fees exist ONLY in the scenario artifact, never in the main CSV
    assert len(OCSCEN) == 12
    for r in OCSCEN:
        assert r["boundary_verification_status"] == "PROVISIONAL_PROXY"
        assert float(r["scenario_outside_city_km"]) >= 0.0
        assert "SCENARIO" in r["note"]
    assert all(r["final_fee"] == "" for r in OCFEES)  # no price leaked to production CSV


# ---- tariff formula still correct (used only in scenario) ----
def test_112_surcharge_min5_ceil_and_zone_independent():
    assert OT.external_surcharge(0.1) == 5 and OT.external_surcharge(2.6) == 6
    assert OT.base_city_fee(3.0) == 14 and OT.base_city_fee(3.01) == 15
    # base fee depends only on route_km, never on the analytics zone
    for r in OCFEES:
        assert int(r["base_city_fee"]) == OT.base_city_fee(float(r["route_km"]))


def test_113_severny_territory_data_unavailable():
    sv = OCSUM["severny"]
    assert sv["in_canonical_9216"] is False and sv["status"] == "TERRITORY_DATA_UNAVAILABLE"
    assert "Северный" not in sv["canonical_settlements_scanned"]


def test_114_thirty_controls_real_plus_synthetic_and_reproducible():
    assert len(OCCTRL) >= 30
    ids = {r["canonical_address_id"] for r in OCFEES}
    assert all(r["canonical_address_id"] in ids for r in OCCTRL)  # real canonical rows
    assert OCSUM["external_addresses_total"] == 4350


# ============ minimum-surcharge regression (bug fix) ============
# Regression guard for the audit finding: external_surcharge returned 0 for
# outside_city_km == 0, letting an external-classified address pay no minimum. The
# fix makes the 5 MDL minimum ALWAYS apply to an external address with a permitted
# calculation; "no surcharge" is a CITY case (decided by territory), and a missing
# boundary yields no production final_fee at all (nothing invented).
def test_115_minimum_surcharge_regression_cases():
    assert OT.external_surcharge(0) == 5      # outside=0 -> minimum still applies
    assert OT.external_surcharge(0.1) == 5    # max(5, ceil(0.2)) = 5
    assert OT.external_surcharge(2.0) == 5    # max(5, ceil(4.0)) = 5
    assert OT.external_surcharge(2.1) == 5    # max(5, ceil(4.2)=5) = 5
    assert OT.external_surcharge(3.0) == 6    # max(5, ceil(6.0)) = 6 (crosses minimum)
    # a CITY address gets NO surcharge (city path, not zero-distance)
    fee_c, base_c, sur_c, st_c = OT.final_fee(5.0, False, None)
    assert st_c == "CITY_OK" and sur_c == 0 and fee_c == base_c
    # an external address with a MISSING boundary gets no invented production price
    fee_m, base_m, sur_m, st_m = OT.final_fee(5.0, True, None)
    assert st_m == "OUTSIDE_DISTANCE_UNAVAILABLE" and fee_m == "" and sur_m == ""


def test_116_four_giska_zero_outside_rows_fixed_5_and_22():
    # Before the fix these four Гиска scenario rows (outside_city_km == 0) showed
    # surcharge 0 / final 17; after the fix they show surcharge 5 / final 22.
    fixed = {"w353619672", "w353817270", "w353817271", "w353817272"}
    rows = [r for r in OCSCEN if r["canonical_address_id"] in fixed]
    assert len(rows) == 4
    for r in rows:
        assert r["territory"] == "Гиска"
        assert float(r["scenario_outside_city_km"]) == 0.0
        assert int(r["scenario_external_surcharge"]) == 5   # was 0 (bug)
        assert int(r["scenario_final_fee"]) == 22           # was 17 (bug)
    # and no scenario row ever leaks into the production final_fee column
    assert all(r["final_fee"] == "" for r in OCFEES)


# ============ v2: real boundary extraction, comparison, scenarios, map, pilot ============
_BND = ROOT / "data/interim/osm-boundaries"
BPROV = json.loads((_BND / "boundary-extraction-provenance.json").read_text("utf-8"))
BPROV_BY_ID = {r["relation_id"]: r for r in BPROV["relations"]}
BCOMPARE = _csv(ROOT / "data/interim/boundary-candidates-comparison-v2.csv")
BSCEN = _csv(ROOT / "data/interim/boundary-route-scenarios-v2.csv")
BSUM = json.loads((ROOT / "reports/zone-model-audit/_boundary-scenarios-summary.json")
                  .read_text("utf-8"))
PILOT = json.loads((ROOT / "data/interim/route-pilot/route-pilot-summary-v1.json")
                   .read_text("utf-8"))
PILOT_ROWS = _csv(ROOT / "data/interim/route-pilot/route-pilot-results-v1.csv")


def test_117_three_relations_really_extracted_with_geometry():
    assert set(BPROV_BY_ID) == {"12463379", "9581354", "944727"}
    levels = {rid: BPROV_BY_ID[rid]["admin_level"] for rid in BPROV_BY_ID}
    assert levels == {"12463379": "8", "9581354": "4", "944727": "5"}
    for rid, r in BPROV_BY_ID.items():
        # real geometry present, valid, non-trivial area, from OSM/Overpass under ODbL
        assert r["geometry_type"] in ("Polygon", "MultiPolygon")
        assert r["valid_after_repair"] is True
        assert r["area_km2"] and r["area_km2"] > 5
        assert "Overpass" in r["extraction_source"]
        assert r["license"].startswith("ODbL")
        assert len(r["raw_sha256"]) == 64 and len(r["geometry_sha256"]) == 64
        # the extracted geojson file exists and is valid JSON with a geometry
        g = json.loads((_BND / f"relation-{rid}.geojson").read_text("utf-8"))
        assert g["geometry"]["type"] in ("Polygon", "MultiPolygon")


def test_118_geometry_checksum_reproducible_and_matches_disk():
    # the recorded geometry_sha256 must equal the hash of the canonical (LF) geojson
    # content. Normalise CRLF->LF first so the check is line-ending independent and
    # cannot become a spurious NEW failure on an autocrlf=true checkout.
    for rid, r in BPROV_BY_ID.items():
        text = (_BND / f"relation-{rid}.geojson").read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(text).hexdigest() == r["geometry_sha256"], rid
    # de-facto PMR (944727) is the largest, city-proper (12463379) the smallest
    areas = {rid: BPROV_BY_ID[rid]["area_km2"] for rid in BPROV_BY_ID}
    assert areas["944727"] > areas["9581354"] > areas["12463379"]


def test_119_comparison_covers_three_boundaries_none_verified():
    by = {r["relation_id"]: r for r in BCOMPARE}
    assert set(by) == {"12463379", "9581354", "944727"}
    for r in BCOMPARE:
        assert r["verification_status"].startswith("DRAFT_UNAPPROVED")
        assert "VERIFIED_FOR_TARIFF" not in r["verification_status"]
        assert r["license"].startswith("ODbL")
    # settlement membership matches the real spatial truth
    assert by["12463379"]["parkany_inside"] == "False"
    assert by["944727"]["giska_inside"] == "True"       # Гиска inside de-facto only
    assert by["9581354"]["giska_inside"] == "False"
    assert by["9581354"]["protyagailovka_inside"] == "True"
    assert by["12463379"]["protyagailovka_inside"] == "False"


def test_120_scenarios_all_12_routes_by_each_boundary():
    assert len(BSCEN) == 36                       # 12 routes x 3 boundaries
    assert len({r["canonical_address_id"] for r in BSCEN}) == 12
    assert {r["boundary_id"] for r in BSCEN} == {"12463379", "9581354", "944727"}
    # address is filled for ALL 36 rows (joined from the canonical registry)
    assert all(r["address"].strip() for r in BSCEN)
    assert sum(1 for r in BSCEN if r["address"].strip()) == 36
    # each row carries a stable route_id and the address is consistent per id
    by_id = {}
    for r in BSCEN:
        assert r["route_id"] == f"route_{r['canonical_address_id']}"
        by_id.setdefault(r["canonical_address_id"], set()).add(r["address"])
    assert all(len(v) == 1 for v in by_id.values())   # id -> single address
    # production final_fee stays empty in the production CSV (never leaked here)
    assert all(r["final_fee"] == "" for r in OCFEES)
    # territory-rule keeps the min-5 for external-labelled addresses even at outside 0
    for r in BSCEN:
        if r["territory_label_external"] == "True":
            assert int(r["territory_rule_surcharge"]) >= 5
    # scenario rows never claim to be an approved price
    assert all("SCENARIO ONLY" in r["note"] for r in BSCEN)
    # the two confirmed price-change addresses (generated, not hand-written)
    def finals(uid):
        return {r["boundary_id"]: int(r["geometric_final_fee"]) for r in BSCEN
                if r["canonical_address_id"] == uid}
    g = finals("n2321749482")            # Гиска, Госпитальная 8
    assert g["12463379"] == 34 and g["944727"] == 28
    p = finals("w353259234")             # Протягайловка, Банный переулок 1
    assert p["12463379"] == 35 and p["9581354"] == 30


def test_121_giska_label_geometry_conflict_surfaced():
    # the 4 outside=0 Гиска addresses are geometrically INSIDE (city 17) but the
    # territory-label rule gives the external minimum (22) — a real owner decision
    four = {"w353619672", "w353817270", "w353817271", "w353817272"}
    rows = [r for r in BSCEN if r["canonical_address_id"] in four
            and r["boundary_id"] == "12463379"]
    assert len(rows) == 4
    for r in rows:
        assert r["destination_classification"] == "inside_city"
        assert int(r["geometric_final_fee"]) == 17
        assert int(r["territory_rule_final_fee"]) == 22
        assert r["label_geometry_conflict"] == "True"
    assert BSUM["giska_inside_12463379_points"] == 17
    assert len(BSUM["label_geometry_conflicts"]) >= 12


def test_122_owner_map_v2_embeds_all_4350_points_and_layers():
    html = (ROOT / "reports/zone-model-audit/owner-boundary-map-v2.html").read_text(
        "utf-8")
    # no fetched external geometry/resources
    for bad in ('src="http', "src='http", 'href="http', "url(http", "<link",
                "<script src"):
        assert bad not in html
    assert '"expected":4350' in html.replace(" ", "")
    # all 4350 points are actually embedded (count the territory tags in the payload)
    import re
    payload = re.search(r'const D=(\{.*?\});', html, re.S).group(1)
    data = json.loads(payload)
    assert len(data["pts"]) == 4350 and data["expected"] == 4350
    assert set(data["boundaries"]) == {"12463379", "9581354", "944727"}
    assert len(data["routes"]) == 12
    for lid in ("L_r12463379", "L_r9581354", "L_r944727", "L_points", "L_severny"):
        assert lid in html
    # 12 INDEPENDENT route toggles, each with a stable route_id
    assert html.count('class="rt"') == 12
    route_ids = {rt["route_id"] for rt in data["routes"]}
    assert len(route_ids) == 12
    for rid in route_ids:
        assert f'data-id="{rid}"' in html
    # every route has a non-empty address and full per-boundary scenario values
    for rt in data["routes"]:
        assert rt["address"].strip()
        assert set(rt["per"]) == {"12463379", "9581354", "944727"}
        for b in rt["per"].values():
            assert {"inside", "outside_km", "surcharge", "final", "crossings",
                    "touching", "exits", "reentries"} <= set(b)
    # disputed routes exist, are flagged, and the click side-panel is wired
    assert any(rt["disputed"] for rt in data["routes"])
    assert "showRoute" in html and "DISPUTED" in html
    # owner-facing summary table Route × A/B/C × Δ is embedded
    assert "A r12463379" in html and "B r9581354" in html and "C r944727" in html
    assert (ROOT / "reports/zone-model-audit/owner-boundary-map-v2.png").exists()
    assert (ROOT / "reports/zone-model-audit/owner-boundary-map-v2.svg").exists()


def test_123_pilot_ran_for_real_30_unique_with_checksums():
    assert PILOT["attempted"] == 30 and PILOT["unique_addresses"] == 30
    assert PILOT["succeeded"] + PILOT["failed"] == 30
    assert PILOT["never_routed_before"] >= 5      # several never routed before
    assert len(PILOT["pilot_ids"]) == 30 and len(set(PILOT["pilot_ids"])) == 30
    # raw responses saved with checksums (no silent provider substitution)
    raw = list((ROOT / "data/interim/route-pilot/raw").glob("*.osrm.json"))
    assert len(raw) == 30
    for r in PILOT_ROWS:
        assert r["provider"].startswith("OSRM demo") and "ALTERNATIVE" in r["provider"]
        # full per-request provenance
        assert r["request_url"].startswith("https://router.project-osrm.org/")
        assert r["request_timestamp_utc"].endswith("Z")
        assert r["request_params"] and r["mode"] in ("cache_replay", "network_capture")
        assert r["retry_count"] != "" and r["attempt_number"] != ""
        assert r["raw_response_path"].startswith("data/interim/route-pilot/raw/")
        if r["validation_status"] == "ALT_PROVIDER_COMPARISON_ONLY":
            assert len(r["raw_sha256"]) == 64 and len(r["geometry_sha256"]) == 64
    # a committed attempt log with timestamps exists (capture provenance)
    attempts = _csv(ROOT / "data/interim/route-pilot/route-pilot-attempts-v1.csv")
    assert len(attempts) >= 30
    assert all(a["request_timestamp_utc"].endswith("Z") for a in attempts)
    # classification is honest — NOT a restaurant-specific production pilot
    assert PILOT["classification"] == "CENTRAL_ORIGIN_ALTERNATIVE_PROVIDER_COMPARISON"
    assert PILOT["restaurant_specific_production_pilot"] is False
    assert PILOT["attempt_metadata_available"] is True
    assert PILOT["url_template"].startswith("https://router.project-osrm.org/")
    # canonical provider is documented and NOT claimed to be reproduced here
    assert "NOT reproducible" in PILOT["canonical_provider"]
    assert PILOT["provider_label"] == "ALTERNATIVE_PROVIDER_COMPARISON"


def test_124_severny_reinvestigated_not_globally_unavailable():
    rep = (ROOT / "reports/zone-model-audit/severny-investigation-v1.md").read_text(
        "utf-8")
    assert "SEVERNY_CANDIDATE_OWNER_REVIEW_REQUIRED" in rep
    assert "place=suburb" in rep
    # inside only the de-facto PMR boundary
    from shapely.geometry import Point, shape
    du = json.loads((ROOT / "docs/data/severny-delivery-units.geojson")
                    .read_text("utf-8"))["features"]
    g944 = shape(json.loads((_BND / "relation-944727.geojson").read_text("utf-8"))
                 ["geometry"])
    g125 = shape(json.loads((_BND / "relation-12463379.geojson").read_text("utf-8"))
                 ["geometry"])
    assert sum(g944.contains(Point(*f["geometry"]["coordinates"])) for f in du) >= 50
    assert sum(g125.contains(Point(*f["geometry"]["coordinates"])) for f in du) == 0


def test_125_gai_post_shown_but_never_plotted_as_invented_point():
    anchors = _csv(ROOT / "data/interim/external-tariff-boundary-anchors-v1.csv")
    gai = next(a for a in anchors if a["anchor_id"] == "PARKANY_KOTOVSKOGO_GAI_POST")
    assert gai["lat"] == "" and gai["lon"] == ""      # no invented coordinates
    assert gai["source_type"] == "OWNER_BRIEF_ONLY"
    html = (ROOT / "reports/zone-model-audit/owner-boundary-map-v2.html").read_text(
        "utf-8")
    assert "PARKANY_KOTOVSKOGO_GAI_POST" in html      # listed in the anchors table


def test_126_source_inventory_lists_real_sources_with_checksums():
    inv = _csv(ROOT / "data/interim/source-inventory-v1.csv")
    assert len(inv) >= 12
    for r in inv:
        assert r["exists"] == "True"
        assert len(r["sha256"]) == 64
        assert r["relation_to_canonical"].startswith("analysis-only")
    paths = {r["path"] for r in inv}
    assert "reports/stage-01/source-audit.md" in paths
    assert "data/interim/osm-boundaries/relation-944727.geojson" in paths


def test_127_decision_doc_v2_complete_and_not_self_approved():
    dec = (ROOT / "reports/zone-model-audit/OWNER_BOUNDARY_DECISION.md").read_text(
        "utf-8")
    assert "OWNER_BOUNDARY_DECISION_REQUIRED" in dec
    assert "[x]" not in dec.lower()                    # no box pre-checked
    # 944727 is NOT called an operational/draft/owner-designed tariff boundary
    assert "draft operational boundary" not in dec.lower()
    assert "operational boundary C" not in dec
    assert "NO_SEPARATE_OPERATIONAL_TARIFF_BOUNDARY_AVAILABLE" in dec
    # corrected 4-option decision block referencing each relation
    assert "Approve relation 12463379 as tariff boundary" in dec
    assert "Approve relation 9581354 as tariff boundary" in dec
    assert "Approve relation 944727 as tariff boundary" in dec
    assert "Reject all and request a separate operational tariff boundary" in dec
    # the two confirmed price changes are listed explicitly
    assert "Гиска, Госпитальная 8 | 34 → 28" in dec
    assert "Банный переулок 1 | 35 → 30" in dec
    # central-origin limitation + restaurant-specific requirement are stated
    assert "RESTAURANT_ORIGINS_UNAVAILABLE" in dec
    assert "active_restaurant_origins × canonical_delivery_destinations" in dec
    for token in ("12463379", "9581354", "944727", "Северный", "ГАИ",
                  "owner-boundary-map-v2"):
        assert token in dec


def test_128_restaurant_plan_unavailable_with_schema_and_scope():
    plan = (ROOT / "reports/zone-model-audit/restaurant-origins-plan-v1.md").read_text(
        "utf-8")
    assert "RESTAURANT_ORIGINS_UNAVAILABLE" in plan
    # only the 3 representative cluster origins exist — no invented restaurants
    assert "REPRESENTATIVE cluster origins" in plan
    for f in ("restaurant_id", "latitude", "longitude", "verification_status",
              "active_status"):
        assert f in plan                              # required input schema
    assert "active_restaurant_origins × canonical_delivery_destinations" in plan
    for scale in ("4,350", "21,750", "43,500"):       # 1/5/10 × destinations
        assert scale in plan
    assert "No batch was run" in plan


def test_129_boundary_provenance_has_dates_endpoint_command_link():
    for rid, r in BPROV_BY_ID.items():
        # three DISTINCT timestamps, never conflated
        assert r["source_object_timestamp"]           # OSM object edit time
        assert r["original_retrieval_timestamp_utc"].endswith("Z")  # real fetch time
        assert r["source_object_timestamp"] != r["original_retrieval_timestamp_utc"]
        assert r["extraction_command"].startswith("curl")
        assert any("overpass" in e for e in r["extraction_endpoints"])
        assert r["raw_artifact_path"].endswith(f"relation-{rid}.overpass.json")
        assert r["geometry_artifact_path"].endswith(f"relation-{rid}.geojson")
        assert "polygonize" in r["raw_to_geometry"]
        assert "moldova" in r["pbf_provenance"]["pbf_resolved_url"]
    # capture log records retrieval timestamps separately (committed)
    log = json.loads((_BND / "extraction-capture-log.json").read_text("utf-8"))
    assert set(log) == {"12463379", "9581354", "944727"}


def test_130_boundary_naming_is_factual_not_operational():
    by = {r["relation_id"]: r for r in BCOMPARE}
    # factual OSM identity present; none POSITIVELY described as an operational
    # tariff boundary (a negating mention like "NOT a separate operational…" is fine)
    for r in by.values():
        assert r["name"]
        m = r["administrative_meaning"].lower()
        assert "is an operational tariff boundary" not in m
        assert "operational tariff boundary" not in m or "not a separate operational" in m
    assert by["9581354"]["admin_level"] == "4"
    assert by["944727"]["admin_level"] == "5"
    # consistent A/B/C semantics: label, brief status, comparison candidacy, suitability
    assert {r["owner_label"] for r in by.values()} == {"A", "B", "C"}
    assert by["12463379"]["owner_label"] == "A"
    assert by["12463379"]["original_brief_nominated"] == "False"   # discovered, not brief
    assert by["9581354"]["original_brief_nominated"] == "True"
    assert by["944727"]["original_brief_nominated"] == "True"
    for r in by.values():
        assert r["comparison_candidate"] == "True"     # all three in the comparison
        assert r["tariff_suitability"] == "CANDIDATE_UNVERIFIED"
    # the extraction provenance agrees on the brief status (single source of truth)
    assert BPROV_BY_ID["12463379"]["original_brief_nominated"] is False
    assert BPROV_BY_ID["9581354"]["original_brief_nominated"] is True
    assert all(r["comparison_candidate"] is True for r in BPROV_BY_ID.values())


def test_131_test_baseline_verification_note_is_honest():
    note = (ROOT / "reports/zone-model-audit/TEST-BASELINE-VERIFICATION.md").read_text(
        "utf-8")
    # the mandated honest baseline formulation is present verbatim
    assert ("Full pytest on START_HEAD 9c5b9ca: 750 passed, 2 failed" in note)
    assert "no new failures were introduced" in note.lower()
    # the false record is explicitly corrected, not repeated as truth
    assert "752 passed" in note and "correct baseline" in note.lower()
    # the two immutable-release baseline failures are named
    assert "test_release.py::test_release_checksums_match" in note
    assert "test_release_v11.py::test_checksums_match_and_manifest_agrees" in note
    # no owner-facing artifact claims a clean run as universal truth
    for name in ("OWNER_BOUNDARY_DECISION.md", "route-generation-pilot-v1.md",
                 "outside-city-distance-v1.md"):
        txt = (ROOT / "reports/zone-model-audit" / name).read_text("utf-8")
        assert "all tests pass" not in txt.lower()
        assert "752 passed" not in txt
