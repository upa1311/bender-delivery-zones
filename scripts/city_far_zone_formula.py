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

# CITY_K5 raw thresholds; zones 3-5 are route_km beyond the second edge.
K5_EDGES = [1.675, 2.875, 4.125, 5.325]
FAR_START = K5_EDGES[1]  # 2.875 km — start of zone 3


def base_distance_fee(route_km):
    """base=-5, rate=6/km, floored: fee = floor(6*km - 5)."""
    return math.floor(ZE.CITY_RATE * route_km - ZE.FIXED_COMMISSION)


def evaluate(city):
    far = [r for r in city if float(r["route_km"]) > FAR_START]
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
    rows, ok, total = evaluate(city)
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
        "scope": "CITY_K5 middle/far zones 3-5 (route_km > 2.875)",
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
