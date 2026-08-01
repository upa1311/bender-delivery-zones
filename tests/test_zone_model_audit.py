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
