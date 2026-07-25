#!/usr/bin/env python
"""Stage 09 — verifiable district QA markers.

Districts are labelled by the NEAREST real OSM place=suburb/neighbourhood node
(no invented boundary). This emits those markers with provenance and the count of
serviceable homes nearest to each, plus Северный as owner_review (no OSM place
object). owner_review_required; no boundary is asserted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage09_engine import OSM_PLACES, load_address_points, nearest_osm_place  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
TARGET = ["Борисовка", "Хомутяновка", "Солнечный", "Птичник", "Ленинский",
          "Шёлковый", "Липканы", "Центр"]


def main() -> int:
    pts = [
        p for p in load_address_points()
        if p["service_status"] in ("standard", "low_density")
        and p["address_status"] == "verified_osm_address"
        and p["settlement_ru"] == "Бендеры"
    ]
    counts: dict[str, int] = {}
    for p in pts:
        d, _ = nearest_osm_place(p["lat"], p["lon"])
        counts[d] = counts.get(d, 0) + 1

    feats = []
    for name, (lat, lon) in OSM_PLACES.items():
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "district_ru": name,
                "source": "osm_place_suburb_or_neighbourhood_node",
                "labelling": "nearest_osm_place (marker only; boundary NOT asserted)",
                "serviceable_homes_nearest": counts.get(name, 0),
                "in_owner_district_list": name in TARGET or name in ("Липканы",),
                "owner_review_required": True,
            },
        })
    # Северный — no OSM place object; named only by marshrutka relations.
    feats.append({
        "type": "Feature",
        "geometry": None,
        "properties": {
            "district_ru": "Северный",
            "source": "no_osm_place_object_named_by_marshrutka_relations_only",
            "labelling": "owner_review (catalog district_ru is authoritative for the 57 Северный objects)",  # noqa: E501
            "owner_review_required": True,
        },
    })

    out = REPO / "docs/data/stage-09-districts.geojson"
    out.write_text(
        json.dumps({"type": "FeatureCollection",
                    "note": "District QA markers by nearest real OSM place. No "
                            "boundary is invented; Северный stays owner_review.",
                    "features": feats}, ensure_ascii=False, indent=2),
        encoding="utf-8", newline="\n")
    print("wrote", out.name)
    for f in feats:
        p = f["properties"]
        print(f"  {p['district_ru']:14s} homes={p.get('serviceable_homes_nearest','-')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
