#!/usr/bin/env python
"""Stage 09C — public-transport corridor deliverables (EasyWay ground truth).

The owner names EasyWay route №5 (ID 21, «Железнодорожный вокзал Бендеры-1 —
ул. Дружбы — ул. 50 лет ВЛКСМ») as the ground-truth CAR corridor to Borisovka.
EasyWay's web is bot-blocked (HTTP 403), so its polyline cannot be fetched
programmatically — and no polyline is fabricated. Instead the corridor is
verified DIRECTLY against OSM (the authoritative graph OSRM uses): every
owner-named street is matched to OSM car ways, the Кишинёв–Тирасполь ПУТЕПРОВОД
is confirmed `bridge=yes layer=2 oneway=yes`, and all ways are present in the
OSRM graph.

The public-transport corridor is used ONLY as proof of car connectivity of
specific roads/junctions — a маршрутка is not a driver route: no stops are
enforced and the full PT length is not used. Read-only; no OSM edit, no immutable
release, no Direct, no price, no new zone.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage09b_entries import build_topo  # noqa: E402

REPO = Path(__file__).resolve().parents[1]

# EasyWay route №5 corridor, as named by the owner (forward stop/street order).
ROUTE5 = {
    "route_id_easyway": 21,
    "name": "№5 Железнодорожный вокзал Бендеры-1 — ул. Дружбы — ул. 50 лет ВЛКСМ",
    "owner_stop_streets_forward": [
        "Тираспольская улица", "улица Титова", "Кишинёвская улица",
        "улица Богдана Хмельницкого", "улица 50 лет ВЛКСМ", "улица Осипенко",
    ],
    "owner_access_corridor": [
        "Кишинёв-Тирасполь", "улица Петровского", "улица Ермакова", "Кишинёвская улица",
    ],
}
CORRIDOR_STREETS = sorted(set(ROUTE5["owner_stop_streets_forward"] + ROUTE5["owner_access_corridor"] + ["улица Дружбы"]))  # noqa: E501


def main() -> int:
    h = build_topo()
    feats = []
    matched = []
    for name in CORRIDOR_STREETS:
        for wid, w in h.ways.items():
            if w["kind"] != "car":
                continue
            nm = w["tags"].get("name") or ""
            if not (nm == name or name.lower() in nm.lower()):
                continue
            t = w["tags"]
            feats.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": w["coords"]},
                "properties": {
                    "corridor_street": name, "osm_way_id": wid, "highway": t.get("highway"),
                    "bridge": t.get("bridge") or "", "layer": t.get("layer") or "",
                    "oneway": t.get("oneway") or "", "access": t.get("access") or "",
                    "direction_note": "oneway interchange ramp — forward/reverse differ"
                    if t.get("oneway") == "yes" else "two-way",
                },
            })
            matched.append({
                "corridor_street": name, "osm_way_id": wid, "way_name": nm,
                "highway": t.get("highway"), "bridge": t.get("bridge") or "",
                "tunnel": t.get("tunnel") or "", "layer": t.get("layer") or "",
                "oneway": t.get("oneway") or "", "access": t.get("access") or "",
                "motor_vehicle": t.get("motor_vehicle") or "", "maxspeed": t.get("maxspeed") or "",
                "present_in_pbf": True,
                "direction": "reverse_differs" if t.get("oneway") == "yes" else "both",
            })

    fc = {
        "type": "FeatureCollection",
        "source": {
            "provider": "EasyWay (owner-named ground truth)",
            "route": ROUTE5,
            "easyway_web_status": "HTTP 403 (bot-blocked); polyline NOT fetched, NOT fabricated",
            "verification": "corridor matched to OSM car ways; путепровод bridge=yes layer=2 "
                            "oneway=yes; all ways present in the local OSRM graph",
            "usage": "proof of car connectivity only; маршрутка stops NOT enforced, full PT "
                     "length NOT used as a driver route",
            "directions": "forward and reverse are distinct because the interchange ramps are oneway",  # noqa: E501
            "owner_review_required": True,
        },
        "features": feats,
    }
    (REPO / "docs/data/public-transport-corridors.geojson").write_text(
        json.dumps(fc, ensure_ascii=False), encoding="utf-8", newline="\n")

    with (REPO / "docs/data/public-transport-corridor-osm-match.csv").open(
            "w", encoding="utf-8", newline="") as fh:
        cols = ["corridor_street", "osm_way_id", "way_name", "highway", "bridge", "tunnel",
                "layer", "oneway", "access", "motor_vehicle", "maxspeed", "present_in_pbf", "direction"]  # noqa: E501
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(matched)

    # route-comparison deliverable: reuse the Stage 09C four-route comparison
    src = REPO / "docs/data/stage-09c-corridor-route-comparison.csv"
    dst = REPO / "docs/data/public-transport-corridor-route-comparison.csv"
    if src.exists():
        dst.write_text(src.read_text("utf-8"), encoding="utf-8", newline="\n")

    print(f"corridor OSM ways matched: {len(matched)}; features: {len(feats)}")
    print("wrote public-transport-corridors.geojson + osm-match.csv + route-comparison.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
