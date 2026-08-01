"""Candidate base+distance fee formula for CITY_K5 middle/far zones (3-5).

The fragmentation analysis showed a flat-fee BALANCED tariff needs ~14 steps. A
simple continuous base+distance rule avoids that: for a city address beyond the
near zones charge

    fee = floor(CITY_RATE * route_km - FIXED_COMMISSION)      # base=-5, rate=6/km

i.e. the equivalent taxi minus the 5-ruble commission, floored to whole rubles.
Because the floor rounds DOWN, client_saving = taxi_ref - fee lands in [5, 6) and
driver_gap = driver_best - fee lands in [0, 1) for EVERY address, so all BALANCED
hard constraints (saving >= 5, gap <= 3 and <= 10%) hold at 100% coverage with a
single formula instead of many flat zones.

City-only, fixed-origin km, owner assumptions. Candidate only — NOT applied to
production, Direct, releases or GitHub Pages.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "zone_economics_audit", ROOT / "scripts/zone_economics_audit.py")
ZE = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ZE)

OUT_CSV = ROOT / "data/interim/zone-k5-far-base-distance-v1.csv"
SUMMARY_JSON = ROOT / "reports/zone-model-audit/_k5-far-formula-summary-v1.json"
OPERATIONAL = ROOT / "data/interim/zone-operational-candidates-v1.csv"
OPERATIONAL_MODEL = "CITY_K5R_dp_optimal_jenks"
OPERATIONAL_ROUNDING = "0.25"


def operational_k5_edges():
    """Read the APPROVED operational CITY_K5 0.25 km edges from the operational
    candidates CSV — do not hardcode the raw K5 thresholds."""
    with OPERATIONAL.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if (row["model_id"] == OPERATIONAL_MODEL
                    and row["rounding_km"] == OPERATIONAL_ROUNDING):
                return [float(e) for e in row["edges"].split("|")]
    raise ValueError("operational CITY_K5 0.25 edges not found")


def base_distance_fee(route_km):
    """base=-5, rate=6/km, floored: fee = floor(6*km - 5)."""
    return math.floor(ZE.CITY_RATE * route_km - ZE.FIXED_COMMISSION)


def near_zone_flat_fees(city, edges):
    """Confirm the two near operational zones (<= edges[1]) each have a single
    flat BALANCED-feasible fee; return their intervals and fees."""
    rule = ZE.POLICY_RULES["BALANCED"]
    out = []
    bounds = [0.0, *edges]
    for zi in range(2):  # zones 1 and 2
        lo, hi = bounds[zi], bounds[zi + 1]
        seg = [k for k in (float(r["route_km"]) for r in city)
               if (k <= hi if zi == 0 else lo < k <= hi)]
        refs = [ZE.taxi_ref_a(k) for k in seg]
        bests = [ZE.driver_best(r) for r in refs]
        floor = ZE._driver_floor(bests, rule)
        ceil = ZE._client_ceiling(refs, rule)
        out.append({
            "zone": zi + 1, "lower_km": ZE.ZM._round(lo), "upper_km": ZE.ZM._round(hi),
            "address_count": len(seg), "flat_balanced_fee": floor,
            "feasible": floor <= ceil,
        })
    return out


def evaluate(city, far_start):
    far = [r for r in city if float(r["route_km"]) > far_start]
    rows = []
    balanced_ok = 0
    for r in sorted(far, key=lambda r: float(r["route_km"])):
        km = float(r["route_km"])
        ref = ZE.taxi_ref_a(km)
        best = ZE.driver_best(ref)
        fee = base_distance_fee(km)
        saving = ref - fee
        gap = best - fee
        ok = saving >= 5 and gap <= 3 and gap <= 0.10 * best and fee < ref
        balanced_ok += 1 if ok else 0
        rows.append({
            "address_id": r["address_id"], "route_km": ZE.ZM._round(km),
            "taxi_reference_rub": ZE.ZM._round(ref, 2),
            "driver_best_take_rub": ZE.ZM._round(best, 2),
            "formula_fee_rub": fee,
            "client_saving_rub": ZE.ZM._round(saving, 2),
            "driver_gap_rub": ZE.ZM._round(gap, 2),
            "balanced_ok": ok,
        })
    return rows, balanced_ok, len(far)


def main():
    city = ZE.city_rows(ZE.load_features())
    edges = operational_k5_edges()          # [1.75, 3.0, 4.0, 5.25]
    far_start = edges[1]                     # 3.0 km — start of operational zone 3
    near = near_zone_flat_fees(city, edges)
    rows, ok, total = evaluate(city, far_start)
    header = ["address_id", "route_km", "taxi_reference_rub", "driver_best_take_rub",
              "formula_fee_rub", "client_saving_rub", "driver_gap_rub", "balanced_ok"]
    with OUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    savings = sorted(r["client_saving_rub"] for r in rows)
    gaps = sorted(r["driver_gap_rub"] for r in rows)
    summary = {
        "formula": "fee = floor(6 * route_km - 5)  (base=-5 rub, rate=6 rub/km)",
        "operational_k5_edges_km": edges,
        "far_zone_start_km": far_start,
        "scope": f"CITY_K5 operational zones 3-5 (route_km > {far_start})",
        "near_zones_flat": near,
        "far_addresses": total,
        "balanced_ok_addresses": ok,
        "balanced_coverage": ZE.ZM._round(ok / total, 4) if total else 0,
        "client_saving_min": savings[0] if savings else None,
        "client_saving_max": savings[-1] if savings else None,
        "driver_gap_min": gaps[0] if gaps else None,
        "driver_gap_max": gaps[-1] if gaps else None,
        "note": "Candidate formula; not applied to production/Direct/release/Pages.",
    }
    SUMMARY_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
