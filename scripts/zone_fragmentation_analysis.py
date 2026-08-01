"""Balanced-zone fragmentation analysis (candidate branch).

Question: how many contiguous flat-fee tariff steps are needed so that EVERY zone
is 100%-coverage feasible under each policy? A contiguous set of city addresses is
policy-feasible iff its driver floor <= its client ceiling (a single flat fee then
satisfies every address). Because extending a zone to a farther address only
raises the driver floor and never raises the client ceiling, feasibility is
monotone under extension, so greedy maximal extension yields the MINIMUM number of
zones (a standard optimal-segmentation argument).

City-only, fixed-origin km, owner assumptions. Nothing here is applied to
production, Direct, releases or GitHub Pages.
"""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "zone_economics_audit", ROOT / "scripts/zone_economics_audit.py")
ZE = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ZE)

FRAG_CSV = ROOT / "data/interim/zone-balanced-fragmentation-v1.csv"
SUMMARY_JSON = ROOT / "reports/zone-model-audit/_fragmentation-summary-v1.json"


def _feasible(seg_kms, rule):
    refs = [ZE.taxi_ref_a(k) for k in seg_kms]
    bests = [ZE.driver_best(r) for r in refs]
    return ZE._driver_floor(bests, rule) <= ZE._client_ceiling(refs, rule)


def minimum_zones(sorted_kms, rule):
    """Greedy maximal contiguous partition; returns the minimal zone list."""
    zones = []
    i, n = 0, len(sorted_kms)
    while i < n:
        j = i
        while j + 1 < n and _feasible(sorted_kms[i:j + 2], rule):
            j += 1
        seg = sorted_kms[i:j + 1]
        refs = [ZE.taxi_ref_a(k) for k in seg]
        bests = [ZE.driver_best(r) for r in refs]
        floor = ZE._driver_floor(bests, rule)
        ceil = ZE._client_ceiling(refs, rule)
        zones.append({
            "lower_km": ZE.ZM._round(seg[0]),
            "upper_km": ZE.ZM._round(seg[-1]),
            "address_count": len(seg),
            "taxi_ref_lo": ZE.ZM._round(min(refs), 2),
            "taxi_ref_hi": ZE.ZM._round(max(refs), 2),
            "min_fee_required_by_driver": floor,
            "max_fee_allowed_by_client": ceil,
            "balanced_feasible_fee": floor if floor <= ceil else "",
        })
        i = j + 1
    return zones


def main():
    city = ZE.city_rows(ZE.load_features())
    kms = sorted(float(r["route_km"]) for r in city)

    counts = {pol: len(minimum_zones(kms, ZE.POLICY_RULES[pol]))
              for pol in ("DRIVER_CONSERVATIVE", "BALANCED", "CUSTOMER_FIRST")}
    balanced = minimum_zones(kms, ZE.POLICY_RULES["BALANCED"])

    header = ["zone_id", "lower_km", "upper_km", "address_count", "taxi_ref_lo",
              "taxi_ref_hi", "min_fee_required_by_driver", "max_fee_allowed_by_client",
              "balanced_feasible_fee"]
    with FRAG_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        for idx, z in enumerate(balanced, start=1):
            writer.writerow({"zone_id": idx, **z})

    summary = {
        "city_addresses": len(city),
        "minimum_zones_for_100pct_coverage": counts,
        "balanced_minimum_zones": counts["BALANCED"],
        "balanced_zone_upper_edges_km": [z["upper_km"] for z in balanced],
        "note": ("A flat-fee-per-zone BALANCED tariff needs ~14 steps for 100% "
                 "coverage — impractical; motivates a base+distance formula for the "
                 "middle/far city zones. Candidate only; not applied to production."),
    }
    SUMMARY_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    print(json.dumps(summary["minimum_zones_for_100pct_coverage"], ensure_ascii=False))
    print("balanced zones:", counts["BALANCED"])


if __name__ == "__main__":
    main()
