"""Owner-approved distance tariff — ANALYSIS/TEST layer only.

Implements the tariff the owner approved:

  City (Бендеры):
    route_km <= 3.0        -> 14 MDL
    route_km >  3.0        -> ceil(14 + (route_km - 3.0) * 4)

  External territories (Парканы, Гиска, Протягайловка, Северный):
    base_city_fee      = ceil(14 + max(0, route_km - 3.0) * 4)
    external_surcharge = max(5, ceil(outside_city_km * 2))   (min 5 always, even at 0)
    final_fee          = base_city_fee + external_surcharge

Route km is used at full precision; only the FINAL price is rounded up (ceil).
outside_city_km is NEVER invented: the split of a route into in-city vs outside
segments is not present in the repository data, so external addresses are recorded
as OUTSIDE_DISTANCE_UNAVAILABLE with an empty final_fee — a client-side "confirm
address / drop a map pin" fallback is out of scope here (no dispatcher pricing).

Candidate/analysis only — production, Direct, releases, routing graph, canonical
addresses, fixed-origin routes, GitHub Pages and live zones/prices are untouched.
Old zone (CITY_K5 etc.) artifacts are kept only as analytics attributes.
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

FEES_CSV = ROOT / "data/interim/owner-tariff-fees-v1.csv"
CONTROLS_CSV = ROOT / "data/interim/owner-tariff-control-addresses-v1.csv"
SUMMARY_JSON = ROOT / "reports/zone-model-audit/_owner-tariff-summary-v1.json"
OWNER_MD = ROOT / "reports/zone-model-audit/owner-tariff-model-v1.md"

CITY_TERRITORY = "Бендеры"
EXTERNAL_TERRITORIES = ("Парканы", "Гиска", "Протягайловка", "Северный")
CITY_INCLUDED_KM = 3.0
CITY_PER_KM = 4.0
CITY_BASE_FEE = 14
EXTERNAL_MIN_SURCHARGE = 5
EXTERNAL_PER_OUTSIDE_KM = 2


def base_city_fee(route_km: float) -> int:
    """City fee = flat 14 within 3 km, then ceil(14 + (km-3)*4). Full-precision km,
    ceil only on the final price."""
    return math.ceil(CITY_BASE_FEE + max(0.0, route_km - CITY_INCLUDED_KM) * CITY_PER_KM)


def external_surcharge(outside_city_km: float) -> int:
    """Approved formula: max(5, ceil(outside_km * 2)). A minimum of 5 MDL ALWAYS
    applies to an external-classified address with a permitted calculation — even
    when outside_city_km == 0 (a route that never leaves the provisional polygon).
    The "no surcharge" case is a CITY address, decided by territory, not by a zero
    outside distance."""
    return max(EXTERNAL_MIN_SURCHARGE, math.ceil(outside_city_km * EXTERNAL_PER_OUTSIDE_KM))


def final_fee(route_km, is_external, outside_city_km):
    """Returns (final_fee|"", base_city_fee, surcharge|"", status). outside_city_km
    is None when it cannot be reliably derived — no invented value, no price."""
    base = base_city_fee(route_km)
    if not is_external:
        return base, base, 0, "CITY_OK"
    if outside_city_km is None:
        return "", base, "", "OUTSIDE_DISTANCE_UNAVAILABLE"
    surcharge = external_surcharge(outside_city_km)
    return base + surcharge, base, surcharge, "EXTERNAL_OK"


def _derive_outside_city_km(_row) -> float | None:
    """The repository has no proven city-boundary crossing / route split, so the
    outside-city segment cannot be reliably computed for any address. Returns None
    (never a fabricated value). If a proven split is added later, wire it here."""
    return None


def compute_rows(features):
    rows = []
    for r in sorted(features, key=lambda r: r["address_id"]):
        km = float(r["route_km"])
        territory = r["territory"]
        is_external = territory in EXTERNAL_TERRITORIES
        outside = _derive_outside_city_km(r) if is_external else 0.0
        fee, base, surcharge, status = final_fee(km, is_external, outside)
        row = {
            "address_id": r["address_id"], "territory": territory,
            "route_km": ZE.ZM._round(km),
            "outside_city_km": "" if (is_external and outside is None) else ZE.ZM._round(outside),
            "base_city_fee": base, "external_surcharge": surcharge,
            "final_fee": fee, "calculation_status": status,
            "geographic_zone_analytics_only": r["current_zone_id"],
        }
        # economics comparison vs the old BALANCED math (owner tariff may diverge)
        if status in ("CITY_OK", "EXTERNAL_OK"):
            ref = ZE.taxi_ref_a(km)
            best = ZE.driver_best(ref)
            row["taxi_reference"] = ZE.ZM._round(ref, 2)
            row["client_saving"] = ZE.ZM._round(ref - fee, 2)
            row["driver_gap"] = ZE.ZM._round(best - fee, 2)
            row["passes_old_balanced"] = (
                (ref - fee) >= 5 and (best - fee) <= 3 and (best - fee) <= 0.10 * best)
        else:
            row["taxi_reference"] = ""
            row["client_saving"] = ""
            row["driver_gap"] = ""
            row["passes_old_balanced"] = ""
        rows.append(row)
    return rows


def _controls(rows):
    """>=20 control addresses: near the 3.0 km boundary, near/mid/far city, one per
    external territory, and boundary cases — selected deterministically from data."""
    city = [r for r in rows if r["calculation_status"] == "CITY_OK"]
    city.sort(key=lambda r: float(r["route_km"]))
    picks = []

    def nearest(target):
        return min(city, key=lambda r: abs(float(r["route_km"]) - target))

    for target in (0.5, 1.0, 1.5, 2.0, 2.5, 2.9, 2.99, 3.0, 3.01, 3.05, 3.1, 3.25,
                   3.5, 3.75, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 8.0):
        picks.append(nearest(target))
    picks.append(city[0])       # closest city
    picks.append(city[-1])      # farthest city
    for terr in EXTERNAL_TERRITORIES:
        ext = [r for r in rows if r["territory"] == terr]
        if ext:
            picks.append(ext[0])
    # dedupe by address_id, keep order
    seen, out = set(), []
    for r in picks:
        if r["address_id"] not in seen:
            seen.add(r["address_id"])
            out.append(r)
    return out


def _stats(vals):
    vals = sorted(vals)
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "min": vals[0], "median": ZE._pct(vals, 0.5), "max": vals[-1]}


def main():
    feats = ZE.load_features()
    rows = compute_rows(feats)

    header = ["address_id", "territory", "route_km", "outside_city_km", "base_city_fee",
              "external_surcharge", "final_fee", "calculation_status",
              "geographic_zone_analytics_only", "taxi_reference", "client_saving",
              "driver_gap", "passes_old_balanced"]
    with FEES_CSV.open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=header, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    controls = _controls(rows)
    with CONTROLS_CSV.open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=header, lineterminator="\n")
        w.writeheader()
        w.writerows(controls)

    city = [r for r in rows if r["calculation_status"] == "CITY_OK"]
    city_fees = [r["final_fee"] for r in city]
    external = {}
    for terr in EXTERNAL_TERRITORIES:
        ext = [r for r in rows if r["territory"] == terr]
        auto = [r["final_fee"] for r in ext if r["calculation_status"] == "EXTERNAL_OK"]
        external[terr] = {
            "addresses": len(ext),
            "auto_calculated": len(auto),
            "outside_distance_unavailable": sum(
                1 for r in ext if r["calculation_status"] == "OUTSIDE_DISTANCE_UNAVAILABLE"),
            "fee_stats": _stats(auto),
        }
    unavailable = sum(1 for r in rows
                      if r["calculation_status"] == "OUTSIDE_DISTANCE_UNAVAILABLE")
    fee_distribution = {}
    for f in city_fees:
        fee_distribution[f] = fee_distribution.get(f, 0) + 1
    balanced_fail = sum(1 for r in city if r["passes_old_balanced"] is False)

    summary = {
        "formula": {
            "city_within_3km": "14 MDL",
            "city_beyond_3km": "ceil(14 + (route_km - 3.0) * 4)",
            "external_surcharge": "max(5, ceil(outside_city_km * 2)); min 5 always for external",
            "final_external": "base_city_fee + external_surcharge",
            "rounding": "full-precision km; ceil applied only to the final price",
        },
        "city_addresses": len(city),
        "city_fee_stats": _stats(city_fees),
        "city_fee_distribution": dict(sorted(fee_distribution.items())),
        "external": external,
        "outside_distance_unavailable_total": unavailable,
        "outside_city_km_source": (
            "NONE — no proven city-boundary route split exists in the data; "
            "outside_city_km left blank, status OUTSIDE_DISTANCE_UNAVAILABLE, "
            "final_fee empty. Not invented."),
        "old_balanced_city_failures": balanced_fail,
        "note": "Analysis/test layer only; production/Direct/releases/zones/prices untouched.",
    }
    SUMMARY_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    _write_owner_md(summary, controls)
    print(json.dumps({k: summary[k] for k in
                      ("city_addresses", "outside_distance_unavailable_total",
                       "old_balanced_city_failures")}, ensure_ascii=False))


def _write_owner_md(summary, controls):
    f = summary["formula"]
    lines = [
        "# Owner-approved distance tariff — analysis layer v1", "",
        "Analysis/test layer only. Production, Direct, releases, routing graph,",
        "canonical addresses, fixed-origin routes, GitHub Pages and live zones/prices",
        "are untouched. Every number below is generated from",
        "`data/interim/owner-tariff-fees-v1.csv`.", "",
        "## Formula", "",
        f"- City ≤ 3.0 km: **{f['city_within_3km']}**",
        f"- City > 3.0 km: **{f['city_beyond_3km']}**",
        f"- External surcharge: **{f['external_surcharge']}**",
        f"- External final: **{f['final_external']}**",
        f"- Rounding: {f['rounding']}", "",
        "## City (Бендеры)", "",
        f"- Addresses: **{summary['city_addresses']}**",
        f"- Fee min/median/max: **{summary['city_fee_stats']['min']} / "
        f"{summary['city_fee_stats']['median']} / {summary['city_fee_stats']['max']}** MDL", "",
        "### Fee distribution (city)", "",
        "| Fee MDL | Addresses |", "|---:|---:|",
    ]
    for fee, cnt in summary["city_fee_distribution"].items():
        lines.append(f"| {fee} | {cnt} |")
    lines += ["", "## External territories", "",
              "| Territory | Addresses | Auto-calculated | OUTSIDE_DISTANCE_UNAVAILABLE |",
              "|---|---:|---:|---:|"]
    for terr, e in summary["external"].items():
        lines.append(f"| {terr} | {e['addresses']} | {e['auto_calculated']} | "
                     f"{e['outside_distance_unavailable']} |")
    lines += ["", f"outside_city_km source: {summary['outside_city_km_source']}", "",
              "## Control addresses", "",
              "| address_id | territory | route_km | base | surcharge | final_fee | status |",
              "|---|---|---:|---:|---:|---:|---|"]
    for r in controls:
        lines.append(
            f"| {r['address_id']} | {r['territory']} | {r['route_km']} | "
            f"{r['base_city_fee']} | {r['external_surcharge']} | "
            f"{r['final_fee'] if r['final_fee'] != '' else '—'} | {r['calculation_status']} |")
    lines += ["", "## Economics vs old BALANCED", "",
              f"City addresses failing the old BALANCED math under this owner tariff: "
              f"**{summary['old_balanced_city_failures']}**. The owner-approved tariff is "
              "intentionally NOT altered to satisfy the old policy; consequences are shown "
              "in `owner-tariff-fees-v1.csv` (client_saving, driver_gap, passes_old_balanced).",
              "", "Verdict: ANALYSIS_COMPLETE / OWNER_REVIEW_REQUIRED.", ""]
    OWNER_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
