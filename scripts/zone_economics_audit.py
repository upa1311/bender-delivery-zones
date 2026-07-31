"""Zone economics audit (candidate branch, commit 2) — Bender Delivery Zones.

Consumes commit-1 outputs and adds the taxi / effective / hybrid economics. All
taxi numbers are OWNER-PROVIDED ASSUMPTIONS, not a licensed tariff, and are used
for candidate analysis only. config/taxi-calibration.yml stays null and untouched.

Honesty rules enforced here:
  * Effective-km, taxi and hybrid economics are computed ONLY for pure-city
    addresses (outside_city_km = 0, proven). External territories keep
    OUTSIDE_SPLIT_UNKNOWN and receive a lower/upper uncertainty bracket only
    (whole route at 6 vs 10 руб./км) — never a point tariff, never a threshold.
  * The sensitivity grid is an address-level feasibility envelope over the
    owner's parameter ranges, city addresses only.
"""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZM = importlib.util.spec_from_file_location(
    "zone_model_audit", ROOT / "scripts/zone_model_audit.py"
)
_module = importlib.util.module_from_spec(ZM)
ZM.loader.exec_module(_module)
ZM = _module

FEATURES = ROOT / "data/interim/zone-model-address-features-v1.csv"
CANDIDATES = ROOT / "data/interim/zone-model-candidates-v1.csv"
SCENARIOS = ROOT / "data/interim/zone-economics-scenarios-v1.csv"
SUMMARY_JSON = ROOT / "reports/zone-model-audit/_economics-summary-v1.json"

# Owner-provided operational evidence (assumptions, not confirmed tariff).
CITY_RATE = 6.0
OUTSIDE_RATE = 10.0
MIN_FARE = 18.0
FIXED_COMMISSION = 5.0
PERCENT_KEPT = 0.65
CURRENT_DIRECT_FEE = 25.0

# Sensitivity ranges (owner-specified). Outside rate does not affect city
# economics (outside_km = 0) and is only used for the external bracket.
CITY_RATES = [5.0, 6.0, 7.0]
OUTSIDE_RATES = [8.0, 9.0, 10.0, 11.0, 12.0]
MIN_FARES = [15.0, 18.0, 20.0, 25.0]
FIXED_COMMISSIONS = [3.0, 5.0, 7.0]
PERCENT_COMMISSIONS = [0.25, 0.30, 0.35, 0.40]
CLIENT_DISCOUNTS = [("abs", 3.0), ("abs", 5.0), ("abs", 7.0),
                    ("pct", 0.10), ("pct", 0.15), ("pct", 0.20)]
DRIVER_GAPS = [("abs", 0.0), ("abs", 2.0), ("abs", 3.0), ("abs", 5.0),
               ("pct", 0.10), ("pct", 0.15)]


def taxi_ref_a(route_km: float, city_rate: float, min_fare: float) -> float:
    return max(min_fare, city_rate * route_km)


def driver_best(taxi_ref: float, fixed: float, pct_kept: float) -> float:
    return max(max(0.0, taxi_ref - fixed), pct_kept * taxi_ref)


def load_features() -> list[dict]:
    with FEATURES.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def city_rows(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["outside_split_status"] == "CITY_ALL_IN"]


def _pct(ordered: list[float], q: float) -> float:
    return ZM._percentile(ordered, q)


def zone_fee_balanced(driver_best_values: list[float]) -> int:
    """Balanced per-zone fee: median best taxi take rounded to whole rubles."""
    ordered = sorted(driver_best_values)
    return round(_pct(ordered, 0.5))


def enforce_monotone_int(fees: list[int]) -> list[int]:
    out = []
    last = -1
    for fee in fees:
        fee = max(fee, last + 1)
        out.append(fee)
        last = fee
    return out


def fill_route_model_economics(city: list[dict]) -> dict:
    """Fill economic columns of the commit-1 candidate route models (city-only)."""
    with CANDIDATES.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0].keys())

    # Precompute per-city-address economics under the primary owner assumption.
    for row in city:
        km = float(row["route_km"])
        ref = taxi_ref_a(km, CITY_RATE, MIN_FARE)
        row["_ref_a"] = ref
        row["_best"] = driver_best(ref, FIXED_COMMISSION, PERCENT_KEPT)

    models: dict[str, list[dict]] = {}
    for row in rows:
        models.setdefault(row["model_id"], []).append(row)

    edges_by_model = {}
    for model_id, zone_rows in models.items():
        zone_rows.sort(key=lambda z: int(z["zone_id"]))
        edges = [float(z["upper_bound"]) for z in zone_rows if z["upper_bound"] != ""]
        edges_by_model[model_id] = edges
        # assign city addresses to zones, compute per-zone economics
        per_zone_best = [[] for _ in zone_rows]
        per_zone_ref = [[] for _ in zone_rows]
        per_zone_km = [[] for _ in zone_rows]
        for row in city:
            km = float(row["route_km"])
            zi = ZM.zone_for(km, edges) - 1
            per_zone_best[zi].append(row["_best"])
            per_zone_ref[zi].append(row["_ref_a"])
            per_zone_km[zi].append(km)
        raw_fees = [zone_fee_balanced(b) if b else 0 for b in per_zone_best]
        fees = enforce_monotone_int(raw_fees)
        for idx, z in enumerate(zone_rows):
            best = sorted(per_zone_best[idx])
            ref = sorted(per_zone_ref[idx])
            km = sorted(per_zone_km[idx])
            fee = fees[idx]
            z["median_effective_km"] = ZM._round(_pct(km, 0.5)) if km else ""
            z["median_taxi_reference"] = ZM._round(_pct(ref, 0.5), 2) if ref else ""
            z["candidate_delivery_fee_rub"] = fee if best else ""
            z["client_median_saving_rub"] = (
                ZM._round(_pct(ref, 0.5) - fee, 2) if ref else "")
            z["driver_median_gap_rub"] = (
                ZM._round(_pct(best, 0.5) - fee, 2) if best else "")
            z["notes"] = "route partition; economics on city addresses only (owner assumption)"

    with CANDIDATES.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for zone_rows in models.values():
            writer.writerows(zone_rows)
    return edges_by_model


def build_economic_models(city: list[dict]) -> list[dict]:
    """5E / 5T-A / 5T-B / HYBRID — city-only, K=5 where applicable."""
    extra: list[dict] = []
    # metrics per city address
    for row in city:
        km = float(row["route_km"])
        row["_eff"] = km  # effective_km = in_city + 1.6667*0 (city)
        row["_ta"] = taxi_ref_a(km, CITY_RATE, MIN_FARE)
        row["_tb"] = MIN_FARE + CITY_RATE * max(0.0, km - 3.0)

    specs = [
        ("5E_city", "effective_km", "_eff"),
        ("5T_A_city", "taxi_reference_a", "_ta"),
        ("5T_B_city", "taxi_reference_b", "_tb"),
    ]
    for model_id, metric, key in specs:
        values = [row[key] for row in city]
        edges = ZM.thresholds_dp_optimal(values, 5)
        # zone assignment
        buckets: list[list[dict]] = [[] for _ in range(6)]
        for row in city:
            zi = ZM.zone_for(row[key], edges) - 1
            buckets[zi].append(row)
        bounds = [0.0, *edges, ""]
        for zi in range(5):
            group = buckets[zi]
            metric_vals = sorted(row[key] for row in group)
            best = sorted(driver_best(row["_ta"], FIXED_COMMISSION, PERCENT_KEPT)
                          for row in group)
            fee = zone_fee_balanced(best) if best else 0
            extra.append({
                "model_id": model_id, "metric": metric, "method": "dp_optimal_jenks",
                "k": 5, "zone_id": zi + 1,
                "lower_bound": ZM._round(bounds[zi]),
                "upper_bound": ZM._round(bounds[zi + 1]) if bounds[zi + 1] != "" else "",
                "address_count": len(group),
                "population_share": ZM._round(len(group) / len(city), 4),
                "median_route_km": ZM._round(_pct(sorted(float(r["route_km"])
                                   for r in group), 0.5)) if group else "",
                "median_effective_km": ZM._round(_pct(metric_vals, 0.5)) if group else "",
                "median_taxi_reference": ZM._round(_pct(sorted(r["_ta"] for r in group),
                                        0.5), 2) if group else "",
                "candidate_delivery_fee_rub": fee if best else "",
                "client_median_saving_rub": ZM._round(
                    _pct(sorted(r["_ta"] for r in group), 0.5) - fee, 2) if group else "",
                "driver_median_gap_rub": ZM._round(_pct(best, 0.5) - fee, 2) if best else "",
                "boundary_instability_count": "",
                "confidence": "CITY_ONLY_OWNER_ASSUMPTION",
                "notes": "city addresses only; external = OUTSIDE_SPLIT_UNKNOWN",
            })

    # enforce monotone fees per economic model
    grouped: dict[str, list[dict]] = {}
    for row in extra:
        grouped.setdefault(row["model_id"], []).append(row)
    for zone_rows in grouped.values():
        zone_rows.sort(key=lambda z: z["zone_id"])
        fees = enforce_monotone_int([int(z["candidate_delivery_fee_rub"])
                                     for z in zone_rows if z["candidate_delivery_fee_rub"] != ""])
        for z, fee in zip([z for z in zone_rows if z["candidate_delivery_fee_rub"] != ""],
                          fees, strict=True):
            z["candidate_delivery_fee_rub"] = fee
    return extra


def hybrid_summary(city: list[dict], rows: list[dict]) -> dict:
    """HYBRID: city route bands (K=5 DP) + one external tier per territory bracket."""
    city_values = [float(r["route_km"]) for r in city]
    city_edges = ZM.thresholds_dp_optimal(city_values, 5)
    external = [r for r in rows if r["outside_split_status"] == "OUTSIDE_SPLIT_UNKNOWN"]
    territories: dict[str, dict] = {}
    for r in external:
        km = float(r["route_km"])
        terr = territories.setdefault(r["territory"], {"count": 0, "km": []})
        terr["count"] += 1
        terr["km"].append(km)
    ext_out = {}
    for terr, info in territories.items():
        kms = sorted(info["km"])
        med = ZM._round(_pct(kms, 0.5))
        # bracket: whole route at 6 (lower) vs 10 (upper) руб/км on the median km
        ext_out[terr] = {
            "count": info["count"],
            "median_route_km": med,
            "bracket_lower_rub": ZM._round(max(MIN_FARE, CITY_RATE * med), 2),
            "bracket_upper_rub": ZM._round(max(MIN_FARE, OUTSIDE_RATE * med), 2),
            "status": "OUTSIDE_SPLIT_UNKNOWN",
        }
    return {"city_bands_km": city_edges, "external_tiers": ext_out}


def sensitivity_grid(city: list[dict]) -> list[dict]:
    """Address-level feasibility envelope over the owner's parameter grid (city)."""
    kms = [float(r["route_km"]) for r in city]
    n = len(kms)
    out: list[dict] = []
    for city_rate in CITY_RATES:
        for min_fare in MIN_FARES:
            for fixed in FIXED_COMMISSIONS:
                for pct in PERCENT_COMMISSIONS:
                    refs = [taxi_ref_a(km, city_rate, min_fare) for km in kms]
                    bests = [driver_best(r, fixed, pct) for r in refs]
                    for dkind, dval in CLIENT_DISCOUNTS:
                        for gkind, gval in DRIVER_GAPS:
                            feasible = 0
                            for ref, best in zip(refs, bests, strict=True):
                                fee = ref - dval if dkind == "abs" else ref * (1 - dval)
                                if fee < 0:
                                    fee = 0.0
                                client_saving = ref - fee
                                gap = best - fee
                                gap_ok = (gap <= gval if gkind == "abs"
                                          else gap <= gval * best)
                                if client_saving >= 0 and gap_ok:
                                    feasible += 1
                            out.append({
                                "city_rate": city_rate, "outside_rate": "n/a_city",
                                "min_fare": min_fare, "fixed_commission": fixed,
                                "percent_commission": pct,
                                "client_discount": f"{dkind}:{dval}",
                                "driver_gap_allowed": f"{gkind}:{gval}",
                                "city_addresses": n,
                                "feasible_pct": ZM._round(feasible / n, 4),
                                "scope": "CITY_ONLY_OWNER_ASSUMPTION",
                            })
    return out


def analyse_current_fee(city: list[dict]) -> dict:
    overpay = adequate = underpaid = 0
    for r in city:
        km = float(r["route_km"])
        ref = taxi_ref_a(km, CITY_RATE, MIN_FARE)
        best = driver_best(ref, FIXED_COMMISSION, PERCENT_KEPT)
        if CURRENT_DIRECT_FEE > ref:
            overpay += 1  # client pays more than a whole taxi
        elif CURRENT_DIRECT_FEE < best - 5:
            underpaid += 1  # driver gets much less than best taxi take
        else:
            adequate += 1
    return {
        "fee": CURRENT_DIRECT_FEE, "city_addresses": len(city),
        "client_overpays": overpay, "adequate": adequate,
        "driver_underpaid": underpaid,
    }


def main() -> None:
    rows = load_features()
    city = city_rows(rows)
    edges_by_model = fill_route_model_economics(city)
    economic_rows = build_economic_models(city)

    # append economic model rows to candidates file
    with CANDIDATES.open(encoding="utf-8-sig", newline="") as handle:
        existing = list(csv.DictReader(handle))
        fieldnames = list(existing[0].keys())
    with CANDIDATES.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(existing)
        for row in economic_rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    scenarios = sensitivity_grid(city)
    with SCENARIOS.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(scenarios[0].keys()),
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(scenarios)

    summary = {
        "city_addresses": len(city),
        "external_addresses": len(rows) - len(city),
        "hybrid": hybrid_summary(city, rows),
        "current_fee_analysis": analyse_current_fee(city),
        "scenario_rows": len(scenarios),
        "route_model_edges": edges_by_model,
    }
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    print(json.dumps(summary["current_fee_analysis"], ensure_ascii=False))
    print("hybrid:", json.dumps(summary["hybrid"], ensure_ascii=False))
    print("scenario rows:", len(scenarios))


if __name__ == "__main__":
    main()
