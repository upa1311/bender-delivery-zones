#!/usr/bin/env python
"""Stage 09 — switch-point sensitivity. The exact city/out-of-city cost switch is
owner-unknown; the Bender OSM boundary is a provisional proxy. Test three
scenarios and report which homes change zone:

  A. switch exactly at the Bender OSM boundary;
  B. switch 300 m BEFORE it (boundary buffered inward);
  C. switch 300 m AFTER it (boundary buffered outward).

An assignment is STABLE if identical in all three; unstable homes go to owner
review. No prices, no release, no Direct changes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage09_engine import (  # noqa: E402
    ORIGINS,
    equivalent_city_km,
    load_bender_boundary,
    route_full,
    segment_in_out_city,
)

REPO = Path(__file__).resolve().parents[1]
ROUTED = REPO / "docs/data/stage-09-routed.jsonl"
SUMMARY = REPO / "docs/data/stage-09-recompute-summary.json"
BUF_DEG = 300.0 / 111000.0  # ~300 m in degrees latitude


def weighted_eq(per_origin_eq: dict) -> float | None:
    w = {"central": 0.85, "bam": 0.15, "outer_other": 0.0}
    parts, tot = 0.0, 0.0
    for k, val in per_origin_eq.items():
        if val is not None:
            parts += val * w[k]
            tot += w[k]
    return round(parts / tot, 4) if tot else None


def zone_of(value, edges):
    for i, e in enumerate(edges):
        if value is not None and value <= e:
            return i + 1
    return len(edges)


def main() -> int:
    edges = json.loads(SUMMARY.read_text("utf-8"))["generalized_A_edges_km"]
    boundary = load_bender_boundary()
    inner = boundary.buffer(-BUF_DEG)   # switch 300 m before the boundary
    outer = boundary.buffer(+BUF_DEG)   # switch 300 m after it

    routed = [json.loads(x) for x in ROUTED.read_text("utf-8").splitlines() if x.strip()]
    # Only routes that actually leave the city can shift with the switch point.
    crossing = [
        r for r in routed
        if any((r["per_origin"].get(o["key"]) or {}).get("outside_city_km", 0) > 0.02 for o in ORIGINS)  # noqa: E501
    ]
    print(f"crossing addresses (switch-point sensitive): {len(crossing)}")

    unstable = []
    per_scenario_zone = {"A_boundary": {}, "B_minus300": {}, "C_plus300": {}}
    changed_ct = {"B_vs_A": 0, "C_vs_A": 0}
    for r in crossing:
        eqs = {"A_boundary": {}, "B_minus300": {}, "C_plus300": {}}
        for o in ORIGINS:
            rt = route_full((o["lon"], o["lat"]), (r["lon"], r["lat"]))
            if not rt.ok:
                for s in eqs:
                    eqs[s][o["key"]] = None
                continue
            for label, bnd in (("A_boundary", boundary), ("B_minus300", inner), ("C_plus300", outer)):  # noqa: E501
                seg = segment_in_out_city(rt.geometry, bnd)
                eqs[label][o["key"]] = equivalent_city_km(seg["in_city_km"], seg["outside_city_km"])
        za = zone_of(weighted_eq(eqs["A_boundary"]), edges)
        zb = zone_of(weighted_eq(eqs["B_minus300"]), edges)
        zc = zone_of(weighted_eq(eqs["C_plus300"]), edges)
        per_scenario_zone["A_boundary"][r["uid"]] = za
        per_scenario_zone["B_minus300"][r["uid"]] = zb
        per_scenario_zone["C_plus300"][r["uid"]] = zc
        if zb != za:
            changed_ct["B_vs_A"] += 1
        if zc != za:
            changed_ct["C_vs_A"] += 1
        if not (za == zb == zc):
            unstable.append({
                "uid": r["uid"], "settlement_ru": r["settlement_ru"],
                "district_ru": r["district_ru"], "street_ru": r["street_ru"],
                "housenumber": r["housenumber"],
                "zone_A_boundary": za, "zone_B_minus300": zb, "zone_C_plus300": zc,
            })

    out = {
        "scenarios": {
            "A_boundary": "switch at the Bender OSM boundary",
            "B_minus300": "switch 300 m before the boundary (buffered inward)",
            "C_plus300": "switch 300 m after the boundary (buffered outward)",
        },
        "generalized_A_edges_km": edges,
        "crossing_addresses": len(crossing),
        "zone_changes": changed_ct,
        "unstable_count": len(unstable),
        "stable_count": len(crossing) - len(unstable),
        "unstable_addresses": unstable[:500],
        "note": "Exact switch point is owner-unknown; unstable homes require owner "
                "review before any republish. Not money, not a Direct tariff.",
        "owner_review_required": True,
    }
    (REPO / "docs/data/stage-09-sensitivity.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(f"unstable {len(unstable)} / crossing {len(crossing)}; "
          f"B!=A {changed_ct['B_vs_A']}, C!=A {changed_ct['C_vs_A']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
