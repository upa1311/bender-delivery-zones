#!/usr/bin/env python
"""Emit the owner-approved Кишинёвская Zone 4 -> Zone 3 correction as a PIPELINE
OVERLAY, not as an in-place edit.

`bender-zones-v1` pins docs/data/final-address-zone-catalog.csv and
final-address-zone-points.geojson by SHA-256 in its `referenced_artifacts`, so
rewriting those files would make that release irreproducible. The correction is
therefore written to a separate overlay that the NEXT release build consumes —
the working pipeline carries the fix, the published releases stay intact.

Only Кишинёвская улица is affected, house by house (possible split street; no
blanket street zone). Other districts, prices, the tariff matrix, Direct and both
immutable releases are untouched.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
D = REPO / "docs/data"
STREET = "Кишинёвская улица"
OVERLAY = D / "zone-corrections-pending.json"
BASIS = ("manual Yandex control (4.828 km via the Р2 путепровод) + distance-optimized "
         "edge-valid engine (Stage 10D); the old value came from a fastest-by-duration "
         "OSRM route of 6.565 km")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    calc = {r["uid"]: r for r in
            csv.DictReader((D / "kishinevskaya-recalculation.csv").open(encoding="utf-8"))}
    corrections, audit = [], []
    for uid, r in calc.items():
        if not r["corrected_weighted_km"] or int(r["old_zone"]) != 4:
            continue
        computed = int(r["candidate_new_zone"])
        # The owner authorised Zone 4 -> Zone 3 only. A house computing below the
        # Zone 2/3 edge still gets the authorised Zone 3 and is flagged; we never
        # jump two zones on our own initiative.
        borderline = computed != 3
        corrections.append({
            "uid": uid, "street_ru": STREET, "housenumber": r["housenumber"],
            "old_zone_id": 4, "new_zone_id": 3, "computed_zone_id": computed,
            "old_distance_km": float(r["old_distance_km"]),
            "corrected_weighted_km": float(r["corrected_weighted_km"]),
            "corrected_central_km": float(r["corrected_central_km"]),
            "borderline_computes_zone_2": borderline,
            "address_anchor_status": r["address_anchor_status"],
        })
        audit.append({
            "uid": uid, "housenumber": r["housenumber"], "old_zone": 4, "new_zone": 3,
            "computed_zone": computed,
            "old_distance_km": r["old_distance_km"],
            "corrected_weighted_km": r["corrected_weighted_km"],
            "corrected_central_km": r["corrected_central_km"],
            "borderline": "да — вычисляется Zone 2, назначен разрешённый Zone 3"
                          if borderline else "нет",
            "address_anchor_status": r["address_anchor_status"],
            "basis": BASIS, "owner_review_required": True,
        })
    corrections.sort(key=lambda c: (len(c["housenumber"]), c["housenumber"]))
    OVERLAY.write_text(json.dumps({
        "schema": "bender-zone-corrections/1",
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scope": "Кишинёвская улица only — per house, never a blanket street zone",
        "applies_to": "the NEXT release build; published releases are untouched",
        "why_an_overlay": ("bender-zones-v1 pins final-address-zone-catalog.csv and "
                           "final-address-zone-points.geojson by SHA-256, so those "
                           "working files must not be rewritten in place"),
        "basis": BASIS, "authorised_move": "Zone 4 -> Zone 3",
        "prices_tariffs_direct_changed": False,
        "other_districts_changed": False,
        "owner_review_required": True,
        "corrections": corrections,
    }, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    with (D / "kishinevskaya-zone-change-audit.csv").open("w", encoding="utf-8",
                                                          newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(audit[0].keys()))
        w.writeheader()
        w.writerows(audit)
    print(f"corrections written: {len(corrections)} (Zone 4 -> Zone 3)")
    print(f"borderline (computes Zone 2, assigned authorised Zone 3): "
          f"{sum(1 for c in corrections if c['borderline_computes_zone_2'])}")
    print(f"overlay: {OVERLAY.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
