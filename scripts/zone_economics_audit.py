"""Zone economics audit (candidate branch) — Bender Delivery Zones.

Consumes the model outputs and adds city-only economics on OWNER-PROVIDED
ASSUMPTIONS (not a licensed tariff; config/taxi-calibration.yml stays null).

City only: economics is computed strictly for the 4,866 pure-city addresses
(outside_km = 0). External territories keep OUTSIDE_SPLIT_UNKNOWN and receive a
lower/upper bracket only — never a point tariff, never a threshold.

Commission truth: with a minimum fare of 18 руб every city taxi_reference >= 18,
which is above the fixed-5 / 65 % crossover of 14.29 руб, so the driver's best
taxi take is ALWAYS `taxi_reference - 5` for city trips, not `0.65 * taxi_reference`.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("zone_model_audit",
                                               ROOT / "scripts/zone_model_audit.py")
ZM = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ZM)

FEATURES = ROOT / "data/interim/zone-model-address-features-v1.csv"
CANDIDATES = ROOT / "data/interim/zone-model-candidates-v1.csv"
SCENARIOS = ROOT / "data/interim/zone-economics-scenarios-v1.csv"
POLICIES = ROOT / "data/interim/zone-policy-prices-v1.csv"
EXTERNAL = ROOT / "data/interim/zone-external-bracket-scenarios-v1.csv"
NEIGHBOURS = ROOT / "data/interim/zone-neighbour-discontinuities-v1.csv"
SUMMARY_JSON = ROOT / "reports/zone-model-audit/_economics-summary-v1.json"

CITY_RATE, OUTSIDE_RATE, MIN_FARE = 6.0, 10.0, 18.0
FIXED_COMMISSION, PERCENT_KEPT, CURRENT_FEE = 5.0, 0.65, 25.0
CROSSOVER_FARE = FIXED_COMMISSION / (1 - PERCENT_KEPT)  # 14.29 руб

CITY_RATES = [5.0, 6.0, 7.0]
OUTSIDE_RATES = [8.0, 9.0, 10.0, 11.0, 12.0]
MIN_FARES = [15.0, 18.0, 20.0, 25.0]
FIXED_COMMISSIONS = [3.0, 5.0, 7.0]
PERCENT_COMMISSIONS = [0.25, 0.30, 0.35, 0.40]
CLIENT_DISCOUNTS = [("abs", 3.0), ("abs", 5.0), ("abs", 7.0),
                    ("pct", 0.10), ("pct", 0.15), ("pct", 0.20)]
DRIVER_GAPS = [("abs", 0.0), ("abs", 2.0), ("abs", 3.0), ("abs", 5.0),
               ("pct", 0.10), ("pct", 0.15)]

# City deployable models to price (natural-break + business per K).
CITY_MODELS = ["CITY_K4R_dp_optimal_jenks", "CITY_K5R_dp_optimal_jenks",
               "CITY_K6R_dp_optimal_jenks", "CITY_K4R_business",
               "CITY_K5R_business", "CITY_K6R_business"]


def taxi_ref_a(route_km, city_rate=CITY_RATE, min_fare=MIN_FARE):
    return max(min_fare, city_rate * route_km)


def driver_best(taxi_ref, fixed=FIXED_COMMISSION, pct_kept=PERCENT_KEPT):
    return max(max(0.0, taxi_ref - fixed), pct_kept * taxi_ref)


def _pct(ordered, q):
    return ZM._percentile(ordered, q)


def load_features():
    with FEATURES.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def city_rows(rows):
    return [r for r in rows if r["outside_split_status"] == "CITY_ALL_IN"]


def read_candidates():
    with CANDIDATES.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def model_edges(candidates, model_id):
    zones = sorted((r for r in candidates if r["model_id"] == model_id),
                   key=lambda z: int(z["zone_id"]))
    return [float(z["upper_bound"]) for z in zones if z["upper_bound"] != ""]


def zone_of_city(km, edges):
    return ZM.zone_for(km, edges)


def monotone_int(fees):
    out, last = [], -1
    for fee in fees:
        fee = max(int(round(fee)), last + 1)
        out.append(fee)
        last = fee
    return out


def commission_breakdown(city):
    fixed_wins = pct_wins = 0
    for r in city:
        ref = taxi_ref_a(float(r["route_km"]))
        if ref - FIXED_COMMISSION >= PERCENT_KEPT * ref:
            fixed_wins += 1
        else:
            pct_wins += 1
    return {
        "crossover_fare_rub": round(CROSSOVER_FARE, 2),
        "fixed5_wins": fixed_wins, "percent65_wins": pct_wins,
        "fixed5_share": round(fixed_wins / len(city), 4),
        "benchmark_used": "taxi_reference_minus_5_for_all_city_trips",
    }


def current_fee_policy_specific(city):
    n = len(city)
    buckets = {"client_overpays": 0, "gap_gt_2": 0, "gap_gt_3": 0, "gap_gt_5": 0,
               "gap_gt_10pct": 0, "gap_gt_15pct": 0}
    for r in city:
        km = float(r["route_km"])
        ref = taxi_ref_a(km)
        best = driver_best(ref)
        gap = best - CURRENT_FEE
        if CURRENT_FEE > ref:
            buckets["client_overpays"] += 1
        if gap > 2:
            buckets["gap_gt_2"] += 1
        if gap > 3:
            buckets["gap_gt_3"] += 1
        if gap > 5:
            buckets["gap_gt_5"] += 1
        if gap > 0.10 * best:
            buckets["gap_gt_10pct"] += 1
        if gap > 0.15 * best:
            buckets["gap_gt_15pct"] += 1
    return {"fee": CURRENT_FEE, "city_addresses": n,
            **{k: v for k, v in buckets.items()},
            **{f"{k}_share": round(v / n, 4) for k, v in buckets.items()}}


def build_policy_prices(city, candidates):
    rows = []
    for model_id in CITY_MODELS:
        edges = model_edges(candidates, model_id)
        if not edges:
            continue
        buckets = [[] for _ in range(len(edges) + 1)]
        for r in city:
            buckets[zone_of_city(float(r["route_km"]), edges) - 1].append(r)
        zone_stats = []
        for members in buckets:
            refs = sorted(taxi_ref_a(float(r["route_km"])) for r in members)
            bests = sorted(driver_best(taxi_ref_a(float(r["route_km"]))) for r in members)
            zone_stats.append({"members": members, "refs": refs, "bests": bests})
        bounds = [0.0, *edges, ""]
        for policy in ("DRIVER_CONSERVATIVE", "BALANCED", "CUSTOMER_FIRST"):
            raw = []
            for st in zone_stats:
                med_ref = _pct(st["refs"], 0.5)
                med_best = _pct(st["bests"], 0.5)
                if policy == "DRIVER_CONSERVATIVE":
                    raw.append(med_best)               # gap ~0, protect driver
                elif policy == "BALANCED":
                    raw.append(med_best - 1)            # ~1 extra client saving
                else:
                    raw.append(med_ref * 0.85)          # 15% off taxi
            fees = monotone_int(raw)
            for zi, st in enumerate(zone_stats):
                members, refs, bests = st["members"], st["refs"], st["bests"]
                fee = fees[zi]
                if not members:
                    continue
                gap_limit_abs = {"DRIVER_CONSERVATIVE": 2, "BALANCED": 3,
                                 "CUSTOMER_FIRST": 5}[policy]
                gap_limit_pct = {"DRIVER_CONSERVATIVE": None, "BALANCED": 0.10,
                                 "CUSTOMER_FIRST": 0.15}[policy]
                client_ok = sum(1 for ref in refs if fee < ref) / len(refs)
                driver_ok = 0
                for best in bests:
                    gap = best - fee
                    ok = gap <= gap_limit_abs
                    if gap_limit_pct is not None:
                        ok = ok and gap <= gap_limit_pct * best
                    driver_ok += 1 if ok else 0
                driver_ok /= len(bests)
                joint = 0
                for ref, best in zip(refs, bests, strict=True):
                    gap = best - fee
                    dok = gap <= gap_limit_abs and (
                        gap_limit_pct is None or gap <= gap_limit_pct * best)
                    joint += 1 if (fee < ref and dok) else 0
                joint /= len(refs)
                rows.append({
                    "model_id": model_id, "policy": policy, "zone_id": zi + 1,
                    "lower_bound": ZM._round(bounds[zi]),
                    "upper_bound": ZM._round(bounds[zi + 1]) if bounds[zi + 1] != "" else "",
                    "city_address_count": len(members),
                    "candidate_fee_rub": fee,
                    "median_taxi_reference_rub": ZM._round(_pct(refs, 0.5), 2),
                    "median_driver_best_taxi_take_rub": ZM._round(_pct(bests, 0.5), 2),
                    "median_client_saving_rub": ZM._round(_pct(refs, 0.5) - fee, 2),
                    "median_driver_gap_rub": ZM._round(_pct(bests, 0.5) - fee, 2),
                    "client_constraint_coverage": ZM._round(client_ok, 4),
                    "driver_constraint_coverage": ZM._round(driver_ok, 4),
                    "joint_coverage": ZM._round(joint, 4),
                    "confidence": "CITY_ONLY_OWNER_ASSUMPTION",
                    "notes": f"{policy}; gap_limit={gap_limit_abs}руб"
                    + (f"/{int(gap_limit_pct*100)}%" if gap_limit_pct else ""),
                })
    header = ["model_id", "policy", "zone_id", "lower_bound", "upper_bound",
              "city_address_count", "candidate_fee_rub", "median_taxi_reference_rub",
              "median_driver_best_taxi_take_rub", "median_client_saving_rub",
              "median_driver_gap_rub", "client_constraint_coverage",
              "driver_constraint_coverage", "joint_coverage", "confidence", "notes"]
    with POLICIES.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return rows


def fill_candidate_city_economics(candidates, policy_rows, city):
    """Fill CITY_DEPLOYABLE candidate rows with BALANCED economics + medians."""
    bal = {(r["model_id"], int(r["zone_id"])): r for r in policy_rows
           if r["policy"] == "BALANCED"}
    for r in candidates:
        if r["economic_scope"] != "CITY_DEPLOYABLE":
            continue
        key = (r["model_id"], int(r["zone_id"]))
        p = bal.get(key)
        if p is None:
            for field in ("median_effective_km", "median_taxi_reference",
                          "candidate_delivery_fee_rub", "client_median_saving_rub",
                          "driver_median_gap_rub"):
                r[field] = ""
            continue
        r["median_effective_km"] = r["median_route_km"]  # city: effective == route
        r["median_taxi_reference"] = p["median_taxi_reference_rub"]
        r["candidate_delivery_fee_rub"] = p["candidate_fee_rub"]
        r["client_median_saving_rub"] = p["median_client_saving_rub"]
        r["driver_median_gap_rub"] = p["median_driver_gap_rub"]
        r["notes"] = "city deployable; BALANCED fee shown (see zone-policy-prices for all 3)"
    with CANDIDATES.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ZM.CANDIDATE_HEADER, lineterminator="\n")
        writer.writeheader()
        writer.writerows(candidates)


def external_bracket_scenarios(rows):
    external = {}
    for r in rows:
        if r["outside_split_status"] != "OUTSIDE_SPLIT_UNKNOWN":
            continue
        external.setdefault(r["territory"], []).append(float(r["route_km"]))
    out = []
    for terr, kms in sorted(external.items()):
        ordered = sorted(kms)
        med = _pct(ordered, 0.5)
        for city_rate in CITY_RATES:
            for outside_rate in OUTSIDE_RATES:
                for min_fare in MIN_FARES:
                    lower = max(min_fare, city_rate * med)   # whole route as city
                    upper = max(min_fare, outside_rate * med)  # whole route as outside
                    out.append({
                        "territory": terr, "city_rate": city_rate,
                        "outside_rate": outside_rate, "minimum_fare": min_fare,
                        "address_count": len(kms),
                        "median_route_km": ZM._round(med),
                        "p90_route_km": ZM._round(_pct(ordered, 0.9)),
                        "taxi_lower_rub": ZM._round(lower, 2),
                        "taxi_upper_rub": ZM._round(upper, 2),
                        "driver_take_lower_rub": ZM._round(driver_best(lower), 2),
                        "driver_take_upper_rub": ZM._round(driver_best(upper), 2),
                        "direct_fee_interval_rub": f"{ZM._round(lower, 2)}..{ZM._round(upper, 2)}",
                        "status": "RANGE_ONLY_NOT_TARIFF",
                    })
    header = ["territory", "city_rate", "outside_rate", "minimum_fare",
              "address_count", "median_route_km", "p90_route_km", "taxi_lower_rub",
              "taxi_upper_rub", "driver_take_lower_rub", "driver_take_upper_rub",
              "direct_fee_interval_rub", "status"]
    with EXTERNAL.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(out)
    return len(out)


def _metres(lat1, lon1, lat2, lon2):
    dlat = (lat1 - lat2) * 111320.0
    dlon = (lon1 - lon2) * 111320.0 * math.cos(math.radians(46.8))
    return math.hypot(dlat, dlon)


def neighbour_discontinuities(city, candidates):
    pts = [(float(r["lat"]), float(r["lon"]), float(r["route_km"]),
            r["address_id"], r["street"]) for r in city]
    cell = 0.00328  # ~250 m in longitude at 46.8N
    grid = {}
    for idx, (lat, lon, *_rest) in enumerate(pts):
        grid.setdefault((int(lat / 0.002246), int(lon / cell)), []).append(idx)

    models = {m: model_edges(candidates, m) for m in
              ("CITY_K4R_dp_optimal_jenks", "CITY_K5R_dp_optimal_jenks",
               "CITY_K6R_dp_optimal_jenks")}
    fees = {}
    for m, edges in models.items():
        buckets = [[] for _ in range(len(edges) + 1)]
        for _lat, _lon, km, *_r in pts:
            buckets[zone_of_city(km, edges) - 1].append(km)
        raw = [_pct(sorted(driver_best(taxi_ref_a(k)) for k in b), 0.5) if b else 0
               for b in buckets]
        fees[m] = monotone_int(raw)

    seen = set()
    rows = []
    agg = {m: {"pairs_100m": 0, "pairs_250m": 0, "diff_zone_100m": 0,
               "diff_zone_250m": 0, "max_jump": 0, "jumps": []} for m in models}
    for cellkey, members in grid.items():
        gx, gy = cellkey
        neigh = [idx for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                 for idx in grid.get((gx + dx, gy + dy), [])]
        for i in members:
            for j in neigh:
                if j <= i:
                    continue
                key = (i, j)
                if key in seen:
                    continue
                seen.add(key)
                d = _metres(pts[i][0], pts[i][1], pts[j][0], pts[j][1])
                if d > 250:
                    continue
                for m, edges in models.items():
                    zi = zone_of_city(pts[i][2], edges)
                    zj = zone_of_city(pts[j][2], edges)
                    jump = abs(fees[m][zi - 1] - fees[m][zj - 1])
                    agg[m]["pairs_250m"] += 1
                    if d <= 100:
                        agg[m]["pairs_100m"] += 1
                    if zi != zj:
                        agg[m]["diff_zone_250m"] += 1
                        if d <= 100:
                            agg[m]["diff_zone_100m"] += 1
                        agg[m]["jumps"].append(jump)
                        if jump > agg[m]["max_jump"]:
                            agg[m]["max_jump"] = jump
                        if jump >= 8:  # only log the sharpest jumps to keep file bounded
                            rows.append({
                                "model_id": m, "address_a": pts[i][3],
                                "address_b": pts[j][3], "street_a": pts[i][4],
                                "distance_m": round(d, 1), "zone_a": zi, "zone_b": zj,
                                "fee_a_rub": fees[m][zi - 1], "fee_b_rub": fees[m][zj - 1],
                                "price_jump_rub": jump,
                            })
    header = ["model_id", "address_a", "address_b", "street_a", "distance_m",
              "zone_a", "zone_b", "fee_a_rub", "fee_b_rub", "price_jump_rub"]
    rows.sort(key=lambda r: (r["model_id"], -r["price_jump_rub"], r["address_a"]))
    with NEIGHBOURS.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    summary = {}
    for m, a in agg.items():
        jumps = sorted(a["jumps"])
        summary[m] = {
            "pairs_100m": a["pairs_100m"], "pairs_250m": a["pairs_250m"],
            "diff_zone_100m": a["diff_zone_100m"], "diff_zone_250m": a["diff_zone_250m"],
            "max_price_jump_rub": a["max_jump"],
            "p90_price_jump_rub": ZM._round(_pct(jumps, 0.9), 2) if jumps else 0,
        }
    return summary


def sensitivity_grid(city):
    kms = [float(r["route_km"]) for r in city]
    n = len(kms)
    out = []
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
                                fee = max(fee, 0.0)
                                gap = best - fee
                                gap_ok = (gap <= gval if gkind == "abs"
                                          else gap <= gval * best)
                                if ref - fee >= 0 and gap_ok:
                                    feasible += 1
                            out.append({
                                "city_rate": city_rate, "outside_rate": "n/a_city",
                                "min_fare": min_fare, "fixed_commission": fixed,
                                "percent_commission": pct,
                                "client_discount": f"{dkind}:{dval}",
                                "driver_gap_allowed": f"{gkind}:{gval}",
                                "city_addresses": n,
                                "feasible_pct": ZM._round(feasible / n, 4),
                                "scope": "CITY_ONLY_OWNER_ASSUMPTION"})
    with SCENARIOS.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(out[0].keys()),
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(out)
    return len(out)


def main():
    rows = load_features()
    city = city_rows(rows)
    candidates = read_candidates()

    policy_rows = build_policy_prices(city, candidates)
    fill_candidate_city_economics(candidates, policy_rows, city)
    scen = sensitivity_grid(city)
    ext = external_bracket_scenarios(rows)
    neigh = neighbour_discontinuities(city, candidates)

    summary = {
        "city_addresses": len(city), "external_addresses": len(rows) - len(city),
        "commission_breakdown": commission_breakdown(city),
        "current_fee_policy_specific": current_fee_policy_specific(city),
        "scenario_rows": scen, "external_bracket_rows": ext,
        "neighbour_discontinuity": neigh,
        "policy_rows": len(policy_rows),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    print(json.dumps(summary["commission_breakdown"], ensure_ascii=False))
    print(json.dumps(summary["current_fee_policy_specific"], ensure_ascii=False))
    print("neighbour:", json.dumps(neigh, ensure_ascii=False))
    print(f"policy_rows={len(policy_rows)} scenarios={scen} external={ext}")


if __name__ == "__main__":
    main()
