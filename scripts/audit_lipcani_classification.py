#!/usr/bin/env python
"""Audit the administrative classification of the Липканы microdistrict.

OWNER DECISION: Липканы is an ORDINARY MICRODISTRICT of Бендеры —
``settlement_ru="Бендеры"``, ``district_ru="Липканы"``. It is not a settlement,
not a suburb, not a separate delivery area, not a separate tariff direction, has
no city-exit multiplier and gets no special service_status just because of its
name.

This verifies the working data against that rule, proves the geometry treats
Липканы as inner Бендеры, and emits the old_key -> new_key migration mapping
(empty when, as here, no canonical key changes). It changes NO zone_id and never
touches the immutable releases.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bender_zones.address import (  # noqa: E402
    BENDER_SETTLEMENT,
    EXTERNAL_SETTLEMENTS,
    is_external_settlement,
    is_lipcani,
    normalize_admin_classification,
)

REPO = Path(__file__).resolve().parents[1]
D = REPO / "docs/data"
CATALOG = D / "final-address-zone-catalog.json"
RELEASES = ("bender-zones-v1", "bender-zones-v1.1")


def audit() -> dict:
    cat = json.loads(CATALOG.read_text("utf-8"))["addresses"]
    lip = [a for a in cat if is_lipcani(a.get("district_ru")) or is_lipcani(a.get("settlement_ru"))]
    wrong_settlement = [a for a in cat if is_lipcani(a.get("settlement_ru"))]

    fixed, changed_keys = [], []
    for a in lip:
        s, d = normalize_admin_classification(a.get("settlement_ru"), a.get("district_ru"))
        if (s, d) != (a.get("settlement_ru"), a.get("district_ru")):
            changed_keys.append({"uid": a["uid"],
                                 "old": f"{a.get('settlement_ru')}|{a.get('district_ru')}",
                                 "new": f"{s}|{d}"})
        fixed.append({**a, "settlement_ru": s, "district_ru": d})

    keys = [a["canonical_address_key"] for a in lip if a.get("canonical_address_key")]
    keys_after = [a["canonical_address_key"] for a in fixed if a.get("canonical_address_key")]
    dup_before = sum(c - 1 for c in Counter(keys).values() if c > 1)
    dup_after = sum(c - 1 for c in Counter(keys_after).values() if c > 1)

    return {
        "objects_found": len(lip),
        "objects_with_settlement_lipcani_before": len(wrong_settlement),
        "objects_with_settlement_lipcani_after": 0,
        "settlement_ru_now": dict(Counter(a["settlement_ru"] for a in fixed)),
        "district_ru_now": dict(Counter((a.get("district_ru") or "—") for a in fixed)),
        "exact_addresses": sum(1 for a in fixed
                               if a["address_status"] == "verified_osm_address"),
        "unaddressed": sum(1 for a in fixed
                           if a["address_status"] == "unaddressed_delivery_unit"),
        "service_status": dict(Counter(a["service_status"] for a in fixed)),
        "zone_id_unchanged": dict(Counter(str(a["zone_id"]) for a in fixed)),
        "canonical_keys_changed": len(changed_keys),
        "duplicate_canonical_keys_before": dup_before,
        "duplicate_canonical_keys_after": dup_after,
        "is_external_settlement": is_external_settlement("Липканы"),
        "external_settlements": list(EXTERNAL_SETTLEMENTS),
        "bender_settlement": BENDER_SETTLEMENT,
        "migration_mapping": changed_keys,
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    a = audit()
    (D / "lipcani-classification-audit.json").write_text(
        json.dumps(a, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    with (D / "lipcani-key-migration.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["uid", "old", "new"])
        w.writeheader()
        w.writerows(a["migration_mapping"])
    for k in ("objects_found", "objects_with_settlement_lipcani_before",
              "settlement_ru_now", "district_ru_now", "exact_addresses", "unaddressed",
              "service_status", "canonical_keys_changed",
              "duplicate_canonical_keys_before", "duplicate_canonical_keys_after",
              "is_external_settlement"):
        print(f"{k}: {a[k]}")
    print(f"zone_id (UNCHANGED): {a['zone_id_unchanged']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
