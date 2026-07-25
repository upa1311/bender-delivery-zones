#!/usr/bin/env python
"""Stage 09 — recompute K=4 on origin-weighted `equivalent_city_km` and compare
to the current v1.1 zones. Uses the SAME band optimizer as the release
(`bender_zones.bands`) with the SAME config, fed the generalized cost instead of
plain road km. Two origin weightings: A = 85/15 central/BAM (current), B = actual
85/10/5 restaurant distribution. This is an AUDIT — it proposes edges for owner
review and publishes NO release, NO price, and does not touch Direct.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bender_zones.bands import assign_band, band_edges, make_bins, optimal_bands  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
ROUTED = REPO / "docs/data/stage-09-routed.jsonl"
CURRENT_EDGES = [2.424, 4.076, 5.577, 9.692]
TARGET_DISTRICTS = {
    "Борисовка": "borisovka",
    "Хомутяновка": "khomutyanovka",
    "Парканы": "parkany-entry",
    "Гиска": "giska-entry",
}


def load_routed() -> list[dict]:
    return [json.loads(line) for line in ROUTED.read_text("utf-8").splitlines() if line.strip()]


def recompute_edges(rows, key, cfg):
    values = [r[key] for r in rows if r.get(key) is not None]
    weights = [1.0] * len(values)  # uniform demand proxy for the audit recompute
    bins = make_bins(values, weights, float(cfg["bin_width_km"]))
    bounds = optimal_bands(
        bins,
        4,
        min_weight_share=float(cfg["min_weight_share"]),
        max_weight_share=float(cfg["max_weight_share"]),
    )
    return [round(e, 3) for e in band_edges(bins, bounds)]


def zone_of(value, edges):
    return assign_band(value, edges) + 1 if value is not None else None


def reason(row, cur, newz):
    if newz == cur:
        return "stable"
    out = row.get("per_origin", {}).get("central") or {}
    if (out.get("outside_city_km") or 0) > 0.3:
        return "outside-city km upweighted (x1.667) -> costlier zone"
    if newz < cur:
        return "shorter fastest valid route than catalog basis -> cheaper zone"
    return "longer in-city road distance on fastest valid route"


def main() -> int:
    cfg = yaml.safe_load((REPO / "config/bands.yml").read_text("utf-8"))["bands"]
    rows = load_routed()
    print(f"loaded {len(rows)} routed addresses")

    edges_a = recompute_edges(rows, "eq_km_A", cfg)
    edges_b = recompute_edges(rows, "eq_km_B", cfg)
    edges_raw_a = recompute_edges(rows, "raw_km_A", cfg)
    print("current v1.1 edges :", CURRENT_EDGES)
    print("recomputed raw_A   :", edges_raw_a, "(sanity: should resemble current)")
    print("generalized eqA    :", edges_a)
    print("generalized eqB    :", edges_b)

    moved_a = moved_b = 0
    detail = []
    for r in rows:
        cur = r["current_zone"]
        za = zone_of(r.get("eq_km_A"), edges_a)
        zb = zone_of(r.get("eq_km_B"), edges_b)
        if za is not None and za != cur:
            moved_a += 1
        if zb is not None and zb != cur:
            moved_b += 1
        po = r.get("per_origin", {}).get("central") or {}
        detail.append(
            {
                **r,
                "in_city_km": po.get("in_city_km"),
                "outside_city_km": po.get("outside_city_km"),
                "recalculated_zone_A": za,
                "recalculated_zone_B": zb,
                "reason_A": reason(r, cur, za),
            }
        )
    print(f"zone moves: variant A {moved_a}/{len(rows)}, variant B {moved_b}/{len(rows)}")

    # --- stage-09-current-vs-generalized.csv ---
    cols = [
        "uid", "settlement_ru", "district_ru", "street_ru", "housenumber",
        "current_zone", "in_city_km", "outside_city_km",
        "raw_km_A", "eq_km_A", "eq_km_B",
        "recalculated_zone_A", "recalculated_zone_B", "reason_A",
    ]
    csv_path = REPO / "docs/data/stage-09-current-vs-generalized.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for d in detail:
            w.writerow(d)
    print("wrote", csv_path.name)

    # --- geojson (points, with change flags) ---
    feats = []
    for d in detail:
        feats.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [d["lon"], d["lat"]]},
                "properties": {
                    k: d.get(k)
                    for k in cols
                }
                | {
                    "changed_A": d["recalculated_zone_A"] != d["current_zone"],
                    "changed_B": d["recalculated_zone_B"] != d["current_zone"],
                },
            }
        )
    gj_path = REPO / "docs/data/stage-09-current-vs-generalized.geojson"
    gj_path.write_text(
        json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )
    print("wrote", gj_path.name, len(feats), "features")

    # --- per-district audit CSVs ---
    (REPO / "reports/stage-09").mkdir(parents=True, exist_ok=True)
    audit_cols = [
        "settlement_ru", "district_ru", "street_ru", "housenumber", "current_zone",
        "central_km", "bam_km", "current_expected_km",
        "in_city_km", "outside_city_km", "crosses_boundary", "reenters_city",
        "first_exit_lonlat", "eq_km_A", "recalculated_zone_A", "qa_flag",
    ]
    for dname, slug in TARGET_DISTRICTS.items():
        sub = [d for d in detail if d["district_ru"] == dname]
        path = REPO / f"reports/stage-09/{slug}-audit.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=audit_cols, extrasaction="ignore")
            w.writeheader()
            for d in sub:
                po = d.get("per_origin", {}).get("central") or {}
                w.writerow(
                    {
                        "settlement_ru": d["settlement_ru"],
                        "district_ru": d["district_ru"],
                        "street_ru": d["street_ru"],
                        "housenumber": d["housenumber"],
                        "current_zone": d["current_zone"],
                        "central_km": po.get("distance_km"),
                        "bam_km": (d.get("per_origin", {}).get("bam") or {}).get("distance_km"),
                        "current_expected_km": d["catalog_expected_km"],
                        "in_city_km": d["in_city_km"],
                        "outside_city_km": d["outside_city_km"],
                        "crosses_boundary": po.get("crosses_boundary"),
                        "reenters_city": po.get("reenters_city"),
                        "first_exit_lonlat": po.get("first_exit_lonlat"),
                        "eq_km_A": d["eq_km_A"],
                        "recalculated_zone_A": d["recalculated_zone_A"],
                        "qa_flag": _qa_flag(d),
                    }
                )
        print(f"wrote {path.name}: {len(sub)} rows")

    summary = {
        "current_edges_km": CURRENT_EDGES,
        "recomputed_raw_A_edges_km": edges_raw_a,
        "generalized_A_edges_km": edges_a,
        "generalized_B_edges_km": edges_b,
        "outside_city_multiplier": 5 / 3,
        "weighting_A": "central 0.85 / BAM 0.15 (current basis)",
        "weighting_B": "central 0.85 / BAM 0.10 / outer 0.05 (actual origins)",
        "zone_moves_A": moved_a,
        "zone_moves_B": moved_b,
        "n_addresses": len(rows),
        "provenance": {
            "city_km_rate_owner_words": 6,
            "outside_km_rate_owner_words": 10,
            "switch_point": "exact point unknown; current Bender OSM boundary is a provisional proxy",  # noqa: E501
            "owner_review_required": True,
            "not_money": True,
        },
    }
    (REPO / "docs/data/stage-09-recompute-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    print("wrote stage-09-recompute-summary.json")
    return 0


def _qa_flag(d) -> str:
    flags = []
    po = d.get("per_origin", {}).get("central") or {}
    if po.get("reenters_city"):
        flags.append("route_leaves_and_reenters_city")
    if d["recalculated_zone_A"] != d["current_zone"]:
        flags.append(f"zone_move_{d['current_zone']}->{d['recalculated_zone_A']}")
    if (po.get("outside_city_km") or 0) > 0 and d["settlement_ru"] == "Бендеры":
        flags.append("in_city_address_with_outside_route_segment")
    return ";".join(flags)


if __name__ == "__main__":
    raise SystemExit(main())
