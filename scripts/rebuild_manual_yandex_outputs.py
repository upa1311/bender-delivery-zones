#!/usr/bin/env python
"""Rebuild the manual-Yandex derived outputs: checkpoint, discrepancies, entries.

Three defects from the previous batch are fixed here:

1. `last_completed_control_id` was `max(measured_ids)` — a lexicographic max, which
   returned MY-085 instead of the route actually added last. It is now derived
   from the trailing batch in APPEND ORDER, never typed in. This remains correct
   even when a later manual check has an earlier calendar date than imported data.

2. Address discrepancies were only recorded when the street token happened to
   differ. Now the Yandex label is parsed into street + house and compared with
   ours on BOTH parts, so street variants, house-number mismatches, settlement
   labels and street-level-only anchors are all captured.

3. District entries are never inferred from global OSM street geometry. A route
   entry is publishable only when its measurement carries explicit evidence from
   a manual map observation. Everything else remains
   `UNKNOWN_REQUIRES_MAP_REVIEW`.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO = Path(__file__).resolve().parents[1]
D = REPO / "docs/data"
MEAS = D / "manual-yandex-measurements.csv"
CONTROLS = D / "manual-yandex-route-controls.csv"
DISC = D / "manual-yandex-address-discrepancies.csv"
ENTRIES = D / "manual-yandex-confirmed-entries.csv"
CHECKPOINT = REPO / "data/interim/manual-yandex-checkpoint.json"
UNKNOWN = "UNKNOWN_REQUIRES_MAP_REVIEW"
MANUAL_ENTRY_METHODS = {"MANUAL_MAP_OBSERVATION", "EMPTY"}
MANUAL_ENTRY_CONFIDENCES = {"CONFIRMED", "PROBABLE", "UNKNOWN"}
MANUAL_ENTRY_DEFAULTS = {
    "manual_entry_street": "",
    "manual_entry_previous_street": "",
    "manual_entry_next_street": "",
    "manual_entry_landmark": "",
    "manual_entry_evidence": "",
    "manual_entry_method": "EMPTY",
    "manual_entry_confidence": "UNKNOWN",
}
CONFIRMED_ENTRY_COLUMNS = [
    "district",
    "control_id",
    "confirmed_entry_street",
    "entry_previous_street",
    "entry_next_street",
    "entry_landmark",
    "entry_method",
    "entry_evidence",
    "confidence",
    "source",
    "owner_review_required",
]


def parse_label(label: str) -> tuple[str, str]:
    """Yandex label -> (street, house). 'улица Суворова, 21А' -> ('улица Суворова','21А')"""
    label = (label or "").strip()
    m = re.match(r"^(.*?),\s*([0-9][^,]*)$", label)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return label, ""


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower()).replace("ё", "е")


def classify(our_street: str, our_house: str, y_street: str, y_house: str,
             y_label: str) -> list[str]:
    flags = []
    if y_label.startswith(("село ", "микрорайон ", "посёлок ")):
        flags.append("SETTLEMENT_DISAGREEMENT")
        return flags
    if norm(our_street) != norm(y_street):
        flags.append("STREET_NAME_VARIANT")
    if y_house and our_house and norm(our_house) != norm(y_house):
        flags.append("HOUSE_NUMBER_DISAGREEMENT")
    if not y_house and our_house:
        flags.append("ADDRESS_ANCHOR_DISAGREEMENT")
    return flags


def normalize_manual_entry(row: dict[str, str]) -> None:
    """Add manual-entry fields and reject unsupported enum values."""
    for field, default in MANUAL_ENTRY_DEFAULTS.items():
        row[field] = (row.get(field) or default).strip()

    method = row["manual_entry_method"]
    confidence = row["manual_entry_confidence"]
    if method not in MANUAL_ENTRY_METHODS:
        raise ValueError(f"{row.get('control_id')}: unsupported manual_entry_method {method!r}")
    if confidence not in MANUAL_ENTRY_CONFIDENCES:
        raise ValueError(
            f"{row.get('control_id')}: unsupported manual_entry_confidence {confidence!r}"
        )


def is_confirmed_manual_entry(row: dict[str, str]) -> bool:
    """Return true only for a fully evidenced manual map observation."""
    return (
        row.get("manual_entry_method") == "MANUAL_MAP_OBSERVATION"
        and bool((row.get("manual_entry_street") or "").strip())
        and bool((row.get("manual_entry_evidence") or "").strip())
        and row.get("manual_entry_confidence") == "CONFIRMED"
    )


def apply_manual_entry(row: dict[str, str]) -> None:
    """Make entry fields fail closed unless manual evidence is complete."""
    normalize_manual_entry(row)
    if row["manual_entry_confidence"] == "CONFIRMED" and not is_confirmed_manual_entry(row):
        raise ValueError(
            f"{row.get('control_id')}: CONFIRMED requires MANUAL_MAP_OBSERVATION, "
            "a street and non-empty evidence"
        )

    if is_confirmed_manual_entry(row):
        row["yandex_district_entry"] = row["manual_entry_street"]
        row["yandex_district_entry_evidence"] = row["manual_entry_evidence"]
        row["yandex_district_entry_confidence"] = "CONFIRMED"
        return

    row["yandex_district_entry"] = UNKNOWN
    row["yandex_district_entry_evidence"] = ""
    row["yandex_district_entry_confidence"] = "UNKNOWN"


def confirmed_entry(row: dict[str, str]) -> dict[str, str] | None:
    """Build a publishable entry row, or return None for incomplete evidence."""
    if not is_confirmed_manual_entry(row):
        return None
    return {
        "district": row["district"],
        "control_id": row["control_id"],
        "confirmed_entry_street": row["manual_entry_street"],
        "entry_previous_street": row["manual_entry_previous_street"],
        "entry_next_street": row["manual_entry_next_street"],
        "entry_landmark": row["manual_entry_landmark"],
        "entry_method": row["manual_entry_method"],
        "entry_evidence": row["manual_entry_evidence"],
        "confidence": row["manual_entry_confidence"],
        "source": "manual-yandex-measurements.csv",
        "owner_review_required": True,
    }


def last_appended_batch(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Return the trailing explicit batch, with a same-date fallback for legacy rows."""
    if not rows:
        return []

    last_row = rows[-1]
    last_batch_id = (last_row.get("manual_batch_id") or "").strip()
    last_date = last_row["checked_date"]
    batch = []
    for row in reversed(rows):
        row_batch_id = (row.get("manual_batch_id") or "").strip()
        if last_batch_id:
            if row_batch_id != last_batch_id:
                break
        elif row_batch_id or row["checked_date"] != last_date:
            break
        batch.append(row)
    batch.reverse()
    return batch


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    rows = list(csv.DictReader(MEAS.open(encoding="utf-8")))
    controls = {c["control_id"]: c for c in csv.DictReader(CONTROLS.open(encoding="utf-8"))}
    cids = set(controls)

    cols = list(rows[0].keys())
    if "manual_batch_id" not in cols:
        cols.insert(cols.index("checked_date") + 1, "manual_batch_id")
    for extra in ("yandex_destination_street", "yandex_destination_house",
                  "yandex_district_entry_evidence", "yandex_district_entry_confidence"):
        if extra not in cols:
            cols.insert(cols.index("yandex_district_entry"), extra)
    insert_at = cols.index("yandex_district_entry_evidence")
    for extra in MANUAL_ENTRY_DEFAULTS:
        if extra not in cols:
            cols.insert(insert_at, extra)
            insert_at += 1

    disc = []
    for r in rows:
        y_street, y_house = parse_label(r["yandex_destination_label"])
        r["yandex_destination_street"] = y_street
        r["yandex_destination_house"] = y_house
        apply_manual_entry(r)

        c = controls.get(r["control_id"])
        our_street = (c["street"] if c else "").strip()
        our_house = (c["housenumber"] if c else "").strip()
        if not our_street:
            our_street = (r.get("our_address") or "").strip()
        flags = classify(our_street, our_house, y_street, y_house,
                         r["yandex_destination_label"])
        if flags:
            disc.append({
                "control_id": r["control_id"],
                "our_address": f"{our_street} {our_house}".strip(),
                "yandex_destination_label": r["yandex_destination_label"],
                "yandex_destination_street": y_street,
                "yandex_destination_house": y_house,
                "destination_lat": r["destination_lat"],
                "destination_lon": r["destination_lon"],
                "flag": ";".join(flags),
                "possible_cause": "Яндекс подписывает точку иначе; проверить привязку вручную",
                "action": "НЕ менять нашу адресную базу автоматически",
                "owner_review_required": True,
            })

    with MEAS.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    with DISC.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(disc[0].keys()))
        w.writeheader()
        w.writerows(disc)

    # Publish only fully evidenced manual map observations.
    ent = [entry for r in rows if (entry := confirmed_entry(r)) is not None]
    with ENTRIES.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CONFIRMED_ENTRY_COLUMNS)
        w.writeheader()
        w.writerows(ent)

    # Checkpoint — prefer the explicit id of the trailing appended batch. Only
    # legacy rows without an id may fall back to a trailing same-date run. Never
    # use a lexicographic control id or the maximum calendar date.
    in_set = [r for r in rows if r["control_id"] in cids]
    last_batch = last_appended_batch(in_set)
    last_batch_date = last_batch[-1]["checked_date"] if last_batch else ""
    measured = {r["control_id"] for r in in_set}
    remaining = sorted(cids - measured)
    CHECKPOINT.write_text(json.dumps({
        "total_controls": len(controls),
        "measured_controls": len(measured),
        "extra_landmark_measurements": len(rows) - len(in_set),
        "blocked_controls": sum(1 for r in rows
                                if str(r.get("calibration_status", "")).startswith(
                                    "MANUAL_CHECK_BLOCKED")),
        "remaining_controls": len(remaining),
        "last_completed_control_id": last_batch[-1]["control_id"] if last_batch else None,
        "last_batch_checked_date": last_batch_date,
        "last_batch_size": len(last_batch),
        "next_control_ids": remaining[:15],
        "updated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": "all counts and the last id are derived from the files, never typed in",
    }, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    from collections import Counter
    print(f"measurements {len(rows)} | in-set {len(measured)} | remaining {len(remaining)}")
    print(f"last_completed_control_id = {last_batch[-1]['control_id'] if last_batch else None}"
          f"  (batch of {len(last_batch)} on {last_batch_date})")
    print(f"discrepancies: {len(disc)}  flags: "
          f"{dict(Counter(f for d in disc for f in d['flag'].split(';')))}")
    print(f"entry confidence: {dict(Counter(r['yandex_district_entry_confidence'] for r in rows))}")
    print(f"confirmed entries published: {len(ent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
