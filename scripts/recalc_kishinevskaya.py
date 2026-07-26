#!/usr/bin/env python
"""Recalculate every exact house of Кишинёвская улица over the CONFIRMED corridor.

The manual Yandex control proved the northern part of Кишинёвская is reached over
the Р2 путепровод (Панина → Р2 → Петровского → Титова → Кишинёвская) in ~4.83 km,
while the old assignment came from a fastest-by-DURATION OSRM route of 6.565 km —
about 36 % longer. The fix is the selection metric: distances are recomputed with
the distance-optimized edge-valid engine (Stage 10D), which honours turn
restrictions, barriers and the endpoint-aware access profile.

Each house is recalculated INDIVIDUALLY — Кишинёвская may be a split street, so no
single zone is assigned to the whole street. Origin weighting matches the original
`expected_km` (central 0.85 / BAM 0.10 / outer 0.05) so old and new are comparable.

Writes the per-house table and a proposed zone change. Other districts, prices,
the tariff matrix and the immutable releases are untouched.
"""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage09_engine import ORIGINS  # noqa: E402
from stage10d_graph import Graph  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
D = REPO / "docs/data"
STREET = "Кишинёвская улица"
ZONE_EDGES = [2.424, 4.076, 5.577, 9.692]
PUTEPROVOD = (29.477691, 46.840768)   # Кишинёв–Тирасполь bridge, layer 2
YANDEX_CONTROL = {"lat": 46.83524, "lon": 29.46735, "km": 4.828,
                  "label": "Кишинёвская улица, 13"}


def zone_of(km: float) -> int:
    for i, e in enumerate(ZONE_EDGES):
        if km <= e:
            return i + 1
    return 4


def haversine_m(a, b, c, d):
    R = 6371008.8
    p1, p2 = math.radians(a), math.radians(c)
    dp, dl = math.radians(c - a), math.radians(d - b)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def houses() -> list[dict]:
    out = []
    for f in json.loads((D / "final-address-zone-points.geojson").read_text("utf-8"))["features"]:
        p = f["properties"]
        if (p.get("street_ru") or "") != STREET:
            continue
        if p.get("address_status") != "verified_osm_address" or not p.get("housenumber"):
            continue
        lon, lat = f["geometry"]["coordinates"]
        out.append({"uid": p["uid"], "house": p["housenumber"], "lat": lat, "lon": lon,
                    "old_zone": p["zone_id"], "old_expected_km": p.get("expected_km"),
                    "service_status": p.get("service_status")})
    out.sort(key=lambda h: (len(h["house"]), h["house"]))
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    g = Graph.load()

    # one distance-optimized solve per origin, plus one from the путепровод so we
    # can prove the confirmed corridor is what the corrected route actually uses
    solved = {}
    for o in ORIGINS:
        snap = g.snap(o["lon"], o["lat"])
        solved[o["key"]] = (g.best_by_edge(g.dijkstra(snap, set())), o["weight"])
    p_snap = g.snap(*PUTEPROVOD)
    via_best = g.best_by_edge(g.dijkstra(p_snap, set()))
    c_snap = g.snap(ORIGINS[0]["lon"], ORIGINS[0]["lat"])
    central_to_bridge = g.arrive(g.best_by_edge(g.dijkstra(c_snap, set())), p_snap)

    rows, moved = [], 0
    for h in houses():
        snap = g.snap(h["lon"], h["lat"])
        per, weighted, ok = {}, 0.0, True
        for key, (best, w) in solved.items():
            m = g.arrive(best, snap)
            if m is None:
                ok = False
                break
            per[key] = round(m / 1000, 4)
            weighted += w * (m / 1000)
        if not ok:
            rows.append({**h, "corrected_weighted_km": None,
                         "status": "MANUAL_CHECK_BLOCKED: не удалось построить маршрут"})
            continue
        corrected = round(weighted, 4)
        central_km = per["central"]
        via_m = g.arrive(via_best, snap)
        via_corridor_km = (round((central_to_bridge + via_m) / 1000, 4)
                           if (via_m is not None and central_to_bridge is not None) else None)
        # the corridor is what the corrected route uses when forcing it costs ~nothing
        uses_corridor = (via_corridor_km is not None
                         and via_corridor_km <= central_km * 1.05)
        new_zone = zone_of(corrected)
        anchor = ("SAME_ROAD_SEGMENT_AS_YANDEX_LABEL"
                  if haversine_m(h["lat"], h["lon"],
                                 YANDEX_CONTROL["lat"], YANDEX_CONTROL["lon"]) < 120
                  else "not_compared")
        if new_zone != h["old_zone"]:
            moved += 1
        rows.append({
            "uid": h["uid"], "housenumber": h["house"],
            "lat": h["lat"], "lon": h["lon"],
            "old_distance_km": h["old_expected_km"], "old_zone": h["old_zone"],
            "corrected_central_km": central_km,
            "corrected_bam_km": per.get("bam"), "corrected_outer_km": per.get("outer_other"),
            "corrected_weighted_km": corrected,
            "candidate_new_zone": new_zone,
            "zone_changes": "да" if new_zone != h["old_zone"] else "нет",
            "route_entry": ("Панина → Р2 (путепровод) → Петровского → Титова → Кишинёвская"
                            if uses_corridor else "южный/иной коридор"),
            "corridor_km_via_putepovod": via_corridor_km,
            "uses_confirmed_corridor": "да" if uses_corridor else "нет",
            "address_anchor_status": anchor,
            "service_status": h["service_status"],
            "basis": "distance-optimized edge-valid engine (Stage 10D), origin weights "
                     "0.85 central / 0.10 BAM / 0.05 outer — same weighting as expected_km",
            "owner_review_required": True,
        })

    with (D / "kishinevskaya-recalculation.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    ok_rows = [r for r in rows if r.get("corrected_weighted_km")]
    print(f"houses recalculated: {len(ok_rows)}")
    print(f"central→путепровод: {round((central_to_bridge or 0)/1000,3)} km")
    print(f"Yandex control {YANDEX_CONTROL['km']} km  (label {YANDEX_CONTROL['label']})")
    from collections import Counter
    print("old zones:", dict(Counter(r["old_zone"] for r in ok_rows)))
    print("candidate zones:", dict(Counter(r["candidate_new_zone"] for r in ok_rows)))
    print(f"houses whose zone changes: {moved}")
    for r in ok_rows:
        print(f"  дом {r['housenumber']:6s} old {r['old_distance_km']:>6} km z{r['old_zone']} -> "
              f"{r['corrected_weighted_km']:>6} km z{r['candidate_new_zone']} "
              f"corridor={r['uses_confirmed_corridor']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
