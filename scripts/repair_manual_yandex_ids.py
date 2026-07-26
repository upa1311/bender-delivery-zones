#!/usr/bin/env python
"""Repair manual-Yandex control ids and rebuild the calibration checkpoint.

The measurements file was written with a fallback id derived from the row index,
so two different routes (Кишинёвская and Титова) both ended up as MY-002. Here
every measurement is re-matched to its control point BY COORDINATE, the stable
control_id from docs/data/manual-yandex-route-controls.csv is restored, and the
old -> new mapping is written out. No measurement is dropped and no number is
altered.

The measured count is DERIVED from the data, never typed in.
"""

from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
D = REPO / "docs/data"
CONTROLS = D / "manual-yandex-route-controls.csv"
MEAS = D / "manual-yandex-measurements.csv"
MIGRATION = D / "manual-yandex-control-id-migration.csv"
CHECKPOINT = REPO / "data/interim/manual-yandex-checkpoint.json"
MATCH_TOLERANCE_M = 60.0


def haversine_m(a, b, c, d):
    R = 6371008.8
    p1, p2 = math.radians(a), math.radians(c)
    dp, dl = math.radians(c - a), math.radians(d - b)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    controls = list(csv.DictReader(CONTROLS.open(encoding="utf-8")))
    meas = list(csv.DictReader(MEAS.open(encoding="utf-8")))

    migration, unmatched = [], []
    for m in meas:
        mlat, mlon = float(m["destination_lat"]), float(m["destination_lon"])
        best, bestd = None, math.inf
        for c in controls:
            d = haversine_m(mlat, mlon, float(c["destination_lat"]),
                            float(c["destination_lon"]))
            if d < bestd:
                best, bestd = c, d
        old = m["control_id"]
        if best is not None and bestd <= MATCH_TOLERANCE_M:
            new = best["control_id"]
            reason = (f"re-matched to the control point by coordinate "
                      f"({bestd:.1f} m); the old id came from a row-index fallback")
            m["control_id"] = new
            m["matched_control_distance_m"] = round(bestd, 1)
        else:
            # a landmark control that is not one of the 86 (e.g. the Пивзавод probe)
            new = f"MY-X{len(unmatched) + 1:02d}"
            reason = ("no control point within "
                      f"{MATCH_TOLERANCE_M:.0f} m (nearest {bestd:.0f} m) — kept as an "
                      "extra landmark measurement outside the 86")
            m["control_id"] = new
            m["matched_control_distance_m"] = ""
            unmatched.append(m)
        migration.append({"old_control_id": old, "new_control_id": new,
                          "label": m["label"], "destination_lat": mlat,
                          "destination_lon": mlon, "reason": reason})

    dups = [k for k, v in Counter(x["control_id"] for x in meas).items() if v > 1]
    if dups:
        print(f"STILL DUPLICATED after repair: {dups}")
        return 1

    cols = list(meas[0].keys())
    with MEAS.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(meas)
    # The migration file is a HISTORICAL record of every id repair. Re-running the
    # script after the ids are already correct must not erase it, so previously
    # recorded rows are preserved and only genuinely new ones are appended.
    cols = ["old_control_id", "new_control_id", "label", "destination_lat",
            "destination_lon", "reason"]
    previous = (list(csv.DictReader(MIGRATION.open(encoding="utf-8")))
                if MIGRATION.exists() else [])
    seen = {(r["old_control_id"], r["new_control_id"]) for r in previous}
    fresh = [r for r in migration
             if r["old_control_id"] != r["new_control_id"]
             and (r["old_control_id"], r["new_control_id"]) not in seen]
    with MIGRATION.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(previous + fresh)

    measured_ids = {m["control_id"] for m in meas if m["control_id"].startswith("MY-")
                    and not m["control_id"].startswith("MY-X")}
    control_ids = {c["control_id"] for c in controls}
    remaining = sorted(control_ids - measured_ids)
    blocked = [m["control_id"] for m in meas
               if str(m.get("calibration_status", "")).startswith("MANUAL_CHECK_BLOCKED")]
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT.write_text(json.dumps({
        "total_controls": len(controls),
        "measured_controls": len(measured_ids),
        "extra_landmark_measurements": len(unmatched),
        "blocked_controls": len(blocked),
        "remaining_controls": len(remaining),
        "last_completed_control_id": max(measured_ids) if measured_ids else None,
        "next_control_ids": remaining[:15],
        "updated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": "counts are derived from the data, never typed in",
    }, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    print(f"controls: {len(controls)} (unique {len(control_ids)})")
    print(f"measurements: {len(meas)}; matched to a control: {len(measured_ids)}; "
          f"extra landmark rows: {len(unmatched)}")
    print(f"duplicates after repair: {len(dups)}")
    print(f"remaining unmeasured controls: {len(remaining)}")
    for r in migration:
        if r["old_control_id"] != r["new_control_id"]:
            print(f"  {r['old_control_id']} -> {r['new_control_id']}  {r['label'][:44]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
