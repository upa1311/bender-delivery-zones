#!/usr/bin/env python
"""Stage 10B — road-truth summary generated FROM the verification files.

Stage 10's `owner_corridors()` returned hardcoded literals ("osm_match_ways": 67,
"osrm_traversable": True, …). Nothing here is hardcoded: every corridor fact is
read from `stage10b-corridor-verification.csv` / `-segments.csv`, the graph proof
from `stage10b-graph-proof.json`, and the overstated counts are RECOMPUTED against
the TRUE distance-optimal Dijkstra (not `alternatives=3`).

Read-only. No OSM edit, no immutable release, no Direct, no price, no zone.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage09_engine import load_address_points, nearest_osm_place  # noqa: E402
from stage10b_graph import CarGraph  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
D = REPO / "docs/data"
CENTRAL = (29.48313, 46.82388)


def read_csv(name):
    p = D / name
    return list(csv.DictReader(p.open(encoding="utf-8"))) if p.exists() else []


def current_km_index():
    """Current (OSRM fastest) km per uid, from the earlier stage files."""
    idx = {}
    for r in read_csv("stage-09c-khomutyanovka-comparison.csv"):
        idx[r["uid"]] = float(r["current_route_km"])
    for r in read_csv("stage-09c-protyagailovka-comparison.csv"):
        idx[r["uid"]] = float(r["current_route_km"])
    for r in read_csv("stage-09b-metric-comparison.csv"):
        try:
            idx.setdefault(r["uid"], float(r["central_B_distance_km"]))
        except (KeyError, ValueError):
            pass
    return idx


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    g = CarGraph.load()
    proof = json.loads((D / "stage10b-graph-proof.json").read_text("utf-8"))
    corridors = read_csv("stage10b-corridor-verification.csv")
    segments = read_csv("stage10b-corridor-segments.csv")

    # --- TRUE shortest for every verified home: ONE origin Dijkstra ---
    src, src_m = g.snap(*CENTRAL)
    dist, _pn, _pw = g.dijkstra(src)
    pts = [p for p in load_address_points()
           if p["service_status"] in ("standard", "low_density")
           and p["address_status"] == "verified_osm_address"]
    cur = current_km_index()

    per_district: dict[str, dict] = {}
    rows = []
    for p in pts:
        d = (nearest_osm_place(p["lat"], p["lon"])[0]
             if p["settlement_ru"] == "Бендеры" else p["settlement_ru"])
        if d not in ("Борисовка", "Хомутяновка", "Протягайловка", "Парканы", "Гиска"):
            continue
        n, snap_m = g.snap(p["lon"], p["lat"])
        if n not in dist:
            continue
        true_km = round(dist[n] / 1000, 4)
        c = cur.get(p["uid"])
        st = per_district.setdefault(d, {"n": 0, "with_current": 0, "overstated": 0,
                                         "sum_gap": 0.0, "max_gap": 0.0})
        st["n"] += 1
        over = False
        if c is not None:
            st["with_current"] += 1
            gap = round(c - true_km, 4)
            if c > 1.10 * true_km:
                st["overstated"] += 1
                over = True
            st["sum_gap"] += max(gap, 0.0)
            st["max_gap"] = max(st["max_gap"], gap)
        rows.append({"uid": p["uid"], "district": d, "street": p["street_ru"],
                     "house": p["housenumber"], "current_zone": p["zone_id"],
                     "snap_m": snap_m, "true_shortest_km": true_km,
                     "current_osrm_km": c,
                     "current_minus_true_km": round(c - true_km, 4) if c is not None else None,
                     "overstated_gt_10pct": over, "owner_review_required": True})
    _csv("stage10b-true-shortest-by-address.csv", rows)

    over_rows = [{"district": k, "homes": v["n"], "with_current_km": v["with_current"],
                  "overstated_gt_10pct": v["overstated"],
                  "mean_excess_km": round(v["sum_gap"] / v["with_current"], 4) if v["with_current"] else None,  # noqa: E501
                  "max_excess_km": round(v["max_gap"], 4),
                  "basis": "current OSRM fastest vs TRUE distance-optimal Dijkstra (own graph)"}
                 for k, v in sorted(per_district.items())]
    _csv("stage10b-overstated-by-district.csv", over_rows)

    # --- road-truth verdicts, all fields taken FROM the files ---
    rt = []
    for c in corridors:
        segs = [s for s in segments if s["corridor"] == c["corridor"]]
        traversed_ok = (c["forward_all_mandatory_ways_traversed"] == "True"
                        and c["reverse_all_mandatory_ways_traversed"] == "True")
        verdict = ("CORRIDOR_FULLY_TRAVERSABLE_BOTH_DIRECTIONS" if traversed_ok
                   else "OSM_CONNECTIVITY_BROKEN")
        rt.append({
            "corridor": c["corridor"], "district": c["district"],
            "streets_in_order": c["streets_in_order"],
            "mandatory_way_count": len(segs),
            "mandatory_way_ids": c["mandatory_way_ids"],
            "forward_km": c["forward_km"], "reverse_km": c["reverse_km"],
            "all_mandatory_ways_traversed_fwd": c["forward_all_mandatory_ways_traversed"],
            "all_mandatory_ways_traversed_rev": c["reverse_all_mandatory_ways_traversed"],
            "detour_arrival_problems": c["forward_problems"] or c["reverse_problems"] or "",
            "oneway_asymmetric_by_TAGS": c["oneway_asymmetric_by_TAGS"],
            "turn_restrictions_touching_corridor": c["turn_restrictions_touching_corridor"],
            "true_shortest_free_km": c["true_shortest_free_km"],
            "road_truth_verdict": verdict,
            "graph_proof": proof["verdict"],
            "graph_sha256": proof["raw_moldova_pbf"]["sha256"][:16] + "…",
            "cross_engine": "INSUFFICIENT_EVIDENCE (GraphHopper/Valhalla/ORS need JVM/Docker)",
            "source": "generated from stage10b-corridor-*.csv (no hardcoded values)",
            "owner_review_required": True,
        })
    _csv("stage10b-road-truth.csv", rt)

    print("graph proof:", proof["verdict"], "| origin snap", src_m, "m")
    for r in rt:
        print(f"  {r['corridor']:18s} ways={r['mandatory_way_count']} "
              f"fwd={r['forward_km']}km rev={r['reverse_km']}km {r['road_truth_verdict']}")
    print("overstated vs TRUE shortest:")
    for o in over_rows:
        print(f"  {o['district']:14s} {o['overstated_gt_10pct']}/{o['with_current_km']} "
              f"(mean excess {o['mean_excess_km']} km, max {o['max_excess_km']} km)")
    return 0


def _csv(name, rows):
    p = D / name
    if not rows:
        p.write_text("", encoding="utf-8")
        return
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
