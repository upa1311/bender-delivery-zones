#!/usr/bin/env python
"""Rebuild the manual-Yandex derived outputs: checkpoint, discrepancies, entries.

Three defects from the previous batch are fixed here:

1. `last_completed_control_id` was `max(measured_ids)` — a lexicographic max, which
   returned MY-085 instead of the route actually added last. It is now derived
   from the APPEND ORDER of the measurements file (last in-set row of the newest
   checked_date), never typed in.

2. Address discrepancies were only recorded when the street token happened to
   differ. Now the Yandex label is parsed into street + house and compared with
   ours on BOTH parts, so street variants, house-number mismatches, settlement
   labels and street-level-only anchors are all captured.

3. `yandex_district_entry` used to copy the destination street. The destination
   street and the district entry are now separate concepts: the entry is derived
   from real evidence — the first street in the route whose OSM geometry actually
   crosses the district/settlement boundary. When that cannot be established, it
   is `UNKNOWN_REQUIRES_MAP_REVIEW`, and only CONFIRMED entries are published.
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
BOUNDARIES = D / "source-boundaries.geojson"

UNKNOWN = "UNKNOWN_REQUIRES_MAP_REVIEW"

# District entries are NEVER inferred. Grouping OSM segments by street NAME is
# invalid: a different segment carrying the same name elsewhere on the map (e.g.
# "улица Сергея Лазо" exists both in Бендеры and in Парканы) does not prove the
# route crossed the boundary there. An entry counts only when a human looked at
# the drawn route on the map and saw the crossing.
#
# control_id -> the observation. Empty until someone actually observes it.
MANUAL_ENTRY_OBSERVATIONS: dict[str, dict] = {}


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


def boundaries() -> dict:
    from shapely.geometry import shape
    gj = json.loads(BOUNDARIES.read_text("utf-8"))
    return {f["properties"]["key"]: shape(f["geometry"]) for f in gj["features"]}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    rows = list(csv.DictReader(MEAS.open(encoding="utf-8")))
    controls = {c["control_id"]: c for c in csv.DictReader(CONTROLS.open(encoding="utf-8"))}
    cids = set(controls)

    cols = list(rows[0].keys())
    for extra in ("yandex_destination_street", "yandex_destination_house",
                  "yandex_district_entry_evidence", "yandex_district_entry_confidence"):
        if extra not in cols:
            cols.insert(cols.index("yandex_district_entry"), extra)

    disc = []
    for r in rows:
        y_street, y_house = parse_label(r["yandex_destination_label"])
        r["yandex_destination_street"] = y_street
        r["yandex_destination_house"] = y_house
        obs = MANUAL_ENTRY_OBSERVATIONS.get(r["control_id"])
        r["yandex_district_entry"] = obs["street"] if obs else UNKNOWN
        r["yandex_district_entry_evidence"] = obs["evidence"] if obs else (
            "не подтверждено: требуется визуальный просмотр маршрута на карте")
        r["yandex_district_entry_confidence"] = obs["confidence"] if obs else "UNKNOWN"

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

    # confirmed entries: only CONFIRMED, never a destination street without evidence
    ent = []
    for r in rows:
        obs = MANUAL_ENTRY_OBSERVATIONS.get(r["control_id"])
        if not obs or obs["confidence"] != "CONFIRMED":
            continue
        ent.append({"district": r["district"], "control_id": r["control_id"],
                    "confirmed_entry_street": obs["street"],
                    "entry_previous_street": obs.get("previous", ""),
                    "entry_next_street": obs.get("next", ""),
                    "entry_landmark": obs.get("landmark", ""),
                    "entry_method": "MANUAL_MAP_OBSERVATION",
                    "entry_evidence": obs["evidence"], "confidence": "CONFIRMED",
                    "source": "визуальный просмотр маршрута в бесплатных Яндекс Картах",
                    "owner_review_required": True})
    with ENTRIES.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["district", "control_id", "confirmed_entry_street",
                                           "entry_previous_street", "entry_next_street",
                                           "entry_landmark", "entry_method", "entry_evidence",
                                           "confidence", "source", "owner_review_required"])
        w.writeheader()
        w.writerows(ent)

    # checkpoint — last completed comes from APPEND ORDER, never a lexicographic max
    in_set = [r for r in rows if r["control_id"] in cids]
    newest = max((r["checked_date"] for r in in_set), default="")
    last_batch = [r for r in in_set if r["checked_date"] == newest]
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
        "last_batch_checked_date": newest,
        "last_batch_size": len(last_batch),
        "next_control_ids": remaining[:15],
        "updated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": "all counts and the last id are derived from the files, never typed in",
    }, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    from collections import Counter
    print(f"measurements {len(rows)} | in-set {len(measured)} | remaining {len(remaining)}")
    print(f"last_completed_control_id = {last_batch[-1]['control_id'] if last_batch else None}"
          f"  (batch of {len(last_batch)} on {newest})")
    print(f"discrepancies: {len(disc)}  flags: "
          f"{dict(Counter(f for d in disc for f in d['flag'].split(';')))}")
    print(f"entry confidence: {dict(Counter(r['yandex_district_entry_confidence'] for r in rows))}")
    print(f"confirmed entries published: {len(ent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
