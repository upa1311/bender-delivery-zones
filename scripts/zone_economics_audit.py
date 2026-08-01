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
OPERATIONAL = ROOT / "data/interim/zone-operational-candidates-v1.csv"
OPERATIONAL_CHANGES = ROOT / "data/interim/zone-operational-rounding-changes-v1.csv"
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

# City deployable models to price (natural-break + share_width_density per K).
CITY_MODELS = ["CITY_K4R_dp_optimal_jenks", "CITY_K5R_dp_optimal_jenks",
               "CITY_K6R_dp_optimal_jenks", "CITY_K4R_share_width_density",
               "CITY_K5R_share_width_density", "CITY_K6R_share_width_density"]


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
    """Non-decreasing integer sequence (equal adjacent values allowed)."""
    out, last = [], -1
    for fee in fees:
        fee = max(int(round(fee)), last)
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


BOUNDARY_CONVENTION = "[lower_bound, upper_bound)"

# Per policy: driver gap caps (abs руб, pct of best) and client-saving floors
# (abs руб, pct of taxi ref). None = not applied.
POLICY_RULES = {
    "DRIVER_CONSERVATIVE": {"gap_abs": 2, "gap_pct": None, "save_abs": 1, "save_pct": None},
    "BALANCED": {"gap_abs": 3, "gap_pct": 0.10, "save_abs": 1, "save_pct": None,
                 "target_save": 5},
    "CUSTOMER_FIRST": {"gap_abs": 5, "gap_pct": 0.15, "save_abs": 5, "save_pct": 0.15},
}


def _gap_cap(best, rule):
    cap = rule["gap_abs"]
    if rule["gap_pct"] is not None:
        cap = min(cap, rule["gap_pct"] * best)
    return cap


def _save_floor(ref, rule):
    floor = rule["save_abs"]
    if rule["save_pct"] is not None:
        floor = max(floor, rule["save_pct"] * ref)
    return floor


def _driver_floor(bests, rule):
    """Lowest integer fee keeping every address's driver gap within the cap."""
    return math.ceil(max(best - _gap_cap(best, rule) for best in bests) - 1e-9)


def _client_ceiling(refs, rule):
    """Highest integer fee keeping every address's client saving at/above floor."""
    return math.floor(min(ref - _save_floor(ref, rule) for ref in refs) + 1e-9)


def _coverage(fee, refs, bests, rule):
    client_ok = sum(1 for ref in refs if ref - fee >= _save_floor(ref, rule))
    driver_ok = sum(1 for best in bests if best - fee <= _gap_cap(best, rule))
    joint = sum(
        1
        for ref, best in zip(refs, bests, strict=True)
        if ref - fee >= _save_floor(ref, rule) and best - fee <= _gap_cap(best, rule)
    )
    n = len(refs)
    return client_ok / n, driver_ok / n, joint / n, n - joint


def _fallback_fee(refs, bests, rule):
    """Integer fee maximizing joint hard-constraint coverage (tie: higher client
    coverage, then lower fee). Never labelled as a satisfied policy."""
    lo = 1
    hi = int(math.ceil(max(refs)))
    best_fee, best_key = lo, (-1.0, -1.0, -lo)
    for fee in range(lo, hi + 1):
        c, d, j, _v = _coverage(fee, refs, bests, rule)
        key = (round(j, 6), round(c, 6), -fee)
        if key > best_key:
            best_key, best_fee = key, fee
    return best_fee


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

        # Assign fees per ZONE across all three policies so both the within-policy
        # monotone rule AND the cross-policy order CUSTOMER_FIRST <= BALANCED <=
        # DRIVER_CONSERVATIVE hold by construction. Raising a fee only shrinks the
        # driver gap (still within cap) and is checked against the client ceiling,
        # so it never breaks a hard constraint; if the raise would exceed the
        # ceiling the zone is INFEASIBLE (not clamped).
        policy_order = ["CUSTOMER_FIRST", "BALANCED", "DRIVER_CONSERVATIVE"]
        prev = dict.fromkeys(policy_order, 0)
        for zi, st in enumerate(zone_stats):
            members, refs, bests = st["members"], st["refs"], st["bests"]
            if not members:
                continue
            cross_lower = 0  # CUSTOMER_FIRST <= BALANCED <= DRIVER_CONSERVATIVE
            for policy in policy_order:
                rule = POLICY_RULES[policy]
                floor_driver = _driver_floor(bests, rule)
                ceil_client = _client_ceiling(refs, rule)
                fee = max(floor_driver, prev[policy], cross_lower)
                base_feasible = floor_driver <= ceil_client
                if base_feasible and fee <= ceil_client:
                    status = "FEASIBLE"
                    candidate = fee
                    prev[policy] = fee
                    cross_lower = fee
                    c_cov = d_cov = j_cov = 1.0
                    violated = 0
                    eff_fee = fee
                    reason = ""
                else:
                    status = "INFEASIBLE"
                    candidate = ""
                    if not base_feasible:
                        reason = (
                            f"driver floor {floor_driver} > client ceiling "
                            f"{ceil_client}: no single flat fee keeps 100% within limits"
                        )
                    else:
                        reason = (
                            f"ordered/monotone floor {fee} exceeds client ceiling "
                            f"{ceil_client}"
                        )
                    eff_fee = _fallback_fee(refs, bests, rule)
                    c_cov, d_cov, j_cov, violated = _coverage(eff_fee, refs, bests, rule)
                gaps = [best - eff_fee for best in bests]
                savings = [ref - eff_fee for ref in refs]
                rows.append({
                    "model_id": model_id, "policy": policy, "zone_id": zi + 1,
                    "lower_bound": ZM._round(bounds[zi]),
                    "upper_bound": ZM._round(bounds[zi + 1]) if bounds[zi + 1] != "" else "",
                    "boundary_convention": BOUNDARY_CONVENTION,
                    "city_address_count": len(members),
                    "policy_status": status,
                    "minimum_fee_required_by_driver": floor_driver,
                    "maximum_fee_allowed_by_client": ceil_client,
                    "candidate_fee_rub": candidate,
                    "fallback_fee_rub": "" if status == "FEASIBLE" else eff_fee,
                    "hard_constraint_coverage": ZM._round(j_cov, 4),
                    "p95_constraint_coverage": ZM._round(j_cov, 4),
                    "violated_address_count": violated,
                    "minimum_taxi_reference": ZM._round(min(refs), 2),
                    "median_taxi_reference": ZM._round(_pct(refs, 0.5), 2),
                    "minimum_driver_best_take": ZM._round(min(bests), 2),
                    "median_driver_best_take": ZM._round(_pct(bests, 0.5), 2),
                    "maximum_driver_gap": ZM._round(max(gaps), 2),
                    "minimum_client_saving": ZM._round(min(savings), 2),
                    "median_client_saving": ZM._round(_pct(sorted(savings), 0.5), 2),
                    "client_constraint_coverage": ZM._round(c_cov, 4),
                    "driver_constraint_coverage": ZM._round(d_cov, 4),
                    "joint_coverage": ZM._round(j_cov, 4),
                    "notes": "FEASIBLE" if status == "FEASIBLE"
                    else f"INFEASIBLE — {reason}; fallback=FALLBACK_PARTIAL_COVERAGE",
                })
    header = ["model_id", "policy", "zone_id", "lower_bound", "upper_bound",
              "boundary_convention", "city_address_count", "policy_status",
              "minimum_fee_required_by_driver", "maximum_fee_allowed_by_client",
              "candidate_fee_rub", "fallback_fee_rub", "hard_constraint_coverage",
              "p95_constraint_coverage", "violated_address_count",
              "minimum_taxi_reference", "median_taxi_reference",
              "minimum_driver_best_take", "median_driver_best_take",
              "maximum_driver_gap", "minimum_client_saving", "median_client_saving",
              "client_constraint_coverage", "driver_constraint_coverage",
              "joint_coverage", "notes"]
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
        r["median_taxi_reference"] = p["median_taxi_reference"]
        if p["policy_status"] == "FEASIBLE":
            r["candidate_delivery_fee_rub"] = p["candidate_fee_rub"]
            r["client_median_saving_rub"] = p["median_client_saving"]
            r["driver_median_gap_rub"] = p["maximum_driver_gap"]
            r["notes"] = "BALANCED FEASIBLE; all 3 policies in zone-policy-prices"
        else:
            r["candidate_delivery_fee_rub"] = "INFEASIBLE"
            r["client_median_saving_rub"] = ""
            r["driver_median_gap_rub"] = ""
            r["notes"] = (
                f"BALANCED INFEASIBLE (fallback {p['fallback_fee_rub']}, "
                f"coverage {p['hard_constraint_coverage']}); see zone-policy-prices"
            )
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
                        "taxi_reference_bracket_rub":
                            f"{ZM._round(lower, 2)}..{ZM._round(upper, 2)}",
                        "direct_feasible_lower_rub": "",
                        "direct_feasible_upper_rub": "",
                        "status": "RANGE_ONLY_NOT_TARIFF",
                    })
    header = ["territory", "city_rate", "outside_rate", "minimum_fare",
              "address_count", "median_route_km", "p90_route_km", "taxi_lower_rub",
              "taxi_upper_rub", "driver_take_lower_rub", "driver_take_upper_rub",
              "taxi_reference_bracket_rub", "direct_feasible_lower_rub",
              "direct_feasible_upper_rub", "status"]
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


def _balanced_effective_fees(edges, city):
    """Per-zone BALANCED fee (feasible candidate, else fallback) for a given
    partition — used only for the operational neighbour price-jump metric."""
    rule = POLICY_RULES["BALANCED"]
    buckets = [[] for _ in range(len(edges) + 1)]
    for r in city:
        buckets[zone_of_city(float(r["route_km"]), edges) - 1].append(
            taxi_ref_a(float(r["route_km"])))
    fees, prev = [], 0
    for refs in buckets:
        if not refs:
            fees.append(prev)
            continue
        bests = [driver_best(x) for x in refs]
        floor_driver = _driver_floor(bests, rule)
        ceil_client = _client_ceiling(refs, rule)
        fee = max(floor_driver, prev)
        if floor_driver <= ceil_client and fee <= ceil_client:
            fees.append(fee)
            prev = fee
        else:
            fb = _fallback_fee(refs, bests, rule)
            fees.append(fb)
            prev = max(prev, fb)
    return fees


def _manual_city_agreement(edges, city_controls):
    same = sum(1 for c in city_controls
               if zone_of_city(c["router_km"], edges) == zone_of_city(c["yandex_km"], edges))
    return same, len(city_controls) - same


def _same_street_splits(edges, city):
    streets = {}
    for r in city:
        streets.setdefault(r["street"], set()).add(zone_of_city(float(r["route_km"]), edges))
    return sum(1 for zs in streets.values() if len(zs) > 1)


def _neighbour_for_edges(pts, grid, edges, fees):
    diff100 = diff250 = 0
    jumps = []
    seen = set()
    for cellkey, members in grid.items():
        gx, gy = cellkey
        neigh = [idx for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                 for idx in grid.get((gx + dx, gy + dy), [])]
        for i in members:
            for j in neigh:
                if j <= i or (i, j) in seen:
                    continue
                seen.add((i, j))
                d = _metres(pts[i][0], pts[i][1], pts[j][0], pts[j][1])
                if d > 250:
                    continue
                zi = zone_of_city(pts[i][2], edges)
                zj = zone_of_city(pts[j][2], edges)
                if zi != zj:
                    diff250 += 1
                    if d <= 100:
                        diff100 += 1
                    jumps.append(abs(fees[zi - 1] - fees[zj - 1]))
    jumps.sort()
    return diff100, diff250, (max(jumps) if jumps else 0), (_pct(jumps, 0.9) if jumps else 0)


def build_operational_candidates(city, candidates):
    reg = ZM.load_addresses()
    controls = ZM.load_manual_controls({r["uid"]: r for r in reg})
    city_controls = [c for c in controls if c["is_city"]]
    pts = [(float(r["lat"]), float(r["lon"]), float(r["route_km"]),
            r["address_id"]) for r in city]
    grid = {}
    for idx, (lat, lon, *_rest) in enumerate(pts):
        grid.setdefault((int(lat / 0.002246), int(lon / 0.00328)), []).append(idx)

    rows, change_rows = [], []
    for model_id in ("CITY_K4R_dp_optimal_jenks", "CITY_K5R_dp_optimal_jenks"):
        raw_edges = model_edges(candidates, model_id)
        raw_assign = {r["address_id"]: zone_of_city(float(r["route_km"]), raw_edges)
                      for r in city}
        variants = [("raw", raw_edges)] + [
            (str(step), ZM._monotone([ZM._round(round(e / step) * step) for e in raw_edges]))
            for step in ZM.ROUNDING_STEPS_KM]
        scored = []
        for label, edges in variants:
            buckets = [0] * (len(edges) + 1)
            changed = 0
            for r in city:
                z = zone_of_city(float(r["route_km"]), edges)
                buckets[z - 1] += 1
                if label != "raw" and z != raw_assign[r["address_id"]]:
                    changed += 1
                    change_rows.append({
                        "model_id": model_id, "rounding_km": label,
                        "address_id": r["address_id"],
                        "raw_zone": raw_assign[r["address_id"]], "rounded_zone": z})
            same, flip = _manual_city_agreement(edges, city_controls)
            fees = _balanced_effective_fees(edges, city)
            d100, d250, mx, p90 = _neighbour_for_edges(pts, grid, edges, fees)
            splits = _same_street_splits(edges, city)
            # BALANCED feasibility per zone
            feasible = infeasible = 0
            bb = [[] for _ in range(len(edges) + 1)]
            for r in city:
                bb[zone_of_city(float(r["route_km"]), edges) - 1].append(
                    taxi_ref_a(float(r["route_km"])))
            prev = 0
            for refs in bb:
                if not refs:
                    continue
                bests = [driver_best(x) for x in refs]
                fl, ce = _driver_floor(bests, POLICY_RULES["BALANCED"]), \
                    _client_ceiling(refs, POLICY_RULES["BALANCED"])
                fee = max(fl, prev)
                if fl <= ce and fee <= ce:
                    feasible += 1
                    prev = fee
                else:
                    infeasible += 1
            row = {
                "model_id": model_id, "rounding_km": label,
                "edges": "|".join(str(e) for e in edges),
                "zone_counts": "|".join(str(b) for b in buckets),
                "changed_vs_raw_count": changed,
                "manual_same": same, "manual_flip": flip,
                "same_street_splits": splits,
                "neighbour_diff_zone_100m": d100, "neighbour_diff_zone_250m": d250,
                "max_price_jump_rub": mx, "p90_price_jump_rub": ZM._round(p90, 2),
                "balanced_feasible_zones": feasible,
                "balanced_infeasible_zones": infeasible,
                "selection": "",
            }
            rows.append(row)
            if label != "raw":
                # lower is better: changes, splits, close-neighbour discontinuities, flips
                scored.append((changed + splits + d100 + flip, label, row))
        scored.sort(key=lambda t: (t[0], t[1]))
        if scored:
            scored[0][2]["selection"] = "PRIMARY_OPERATIONAL_CANDIDATE"
        if len(scored) > 1:
            scored[1][2]["selection"] = "FALLBACK_OPERATIONAL_CANDIDATE"

    header = ["model_id", "rounding_km", "edges", "zone_counts", "changed_vs_raw_count",
              "manual_same", "manual_flip", "same_street_splits",
              "neighbour_diff_zone_100m", "neighbour_diff_zone_250m",
              "max_price_jump_rub", "p90_price_jump_rub", "balanced_feasible_zones",
              "balanced_infeasible_zones", "selection"]
    with OPERATIONAL.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with OPERATIONAL_CHANGES.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["model_id", "rounding_km", "address_id", "raw_zone",
                                "rounded_zone"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(change_rows)
    return rows


def main():
    rows = load_features()
    city = city_rows(rows)
    candidates = read_candidates()

    policy_rows = build_policy_prices(city, candidates)
    fill_candidate_city_economics(candidates, policy_rows, city)
    operational_rows = build_operational_candidates(city, candidates)
    scen = sensitivity_grid(city)
    ext = external_bracket_scenarios(rows)
    neigh = neighbour_discontinuities(city, candidates)

    # feasibility summary per model/policy for the owner pack
    feasibility = {}
    for p in policy_rows:
        key = f'{p["model_id"]}|{p["policy"]}'
        f = feasibility.setdefault(key, {"feasible_zones": [], "infeasible_zones": []})
        z = int(p["zone_id"])
        if p["policy_status"] == "FEASIBLE":
            f["feasible_zones"].append({"zone": z, "fee": int(p["candidate_fee_rub"])})
        else:
            f["infeasible_zones"].append({
                "zone": z, "fallback": int(p["fallback_fee_rub"]),
                "coverage": float(p["hard_constraint_coverage"]),
                "violated": int(p["violated_address_count"])})

    operational_selected = {
        r["model_id"] + "|" + r["rounding_km"]: r["selection"]
        for r in operational_rows if r["selection"]}

    summary = {
        "city_addresses": len(city), "external_addresses": len(rows) - len(city),
        "commission_breakdown": commission_breakdown(city),
        "current_fee_policy_specific": current_fee_policy_specific(city),
        "scenario_rows": scen, "external_bracket_rows": ext,
        "neighbour_discontinuity": neigh,
        "policy_rows": len(policy_rows),
        "policy_feasibility": feasibility,
        "operational_selected": operational_selected,
    }
    SUMMARY_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    print(json.dumps(summary["commission_breakdown"], ensure_ascii=False))
    print(json.dumps(summary["current_fee_policy_specific"], ensure_ascii=False))
    print("neighbour:", json.dumps(neigh, ensure_ascii=False))
    print(f"policy_rows={len(policy_rows)} scenarios={scen} external={ext}")


if __name__ == "__main__":
    main()
