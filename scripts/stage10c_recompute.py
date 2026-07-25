#!/usr/bin/env python
"""Stage 10C — recompute EVERY verified address on the edge-valid graph.

Turn restrictions, barrier nodes, the delivery access profile and edge snapping
(partial edge length charged, off-road distance reported separately) are all in
force. One edge-state Dijkstra from the origin serves every address: the state
distances are collapsed to a best-per-edge index, so each address is an O(1)
lookup on its snapped edge.

Covers Борисовка, Хомутяновка, Протягайловка, Парканы, Гиска and Северный.
Read-only. No OSM edit, no immutable release, no Direct, no price, no zone. The
resulting numbers supersede every earlier "overstated" figure.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage09_engine import load_address_points, nearest_osm_place  # noqa: E402
from stage10c_graph import EdgeGraph  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
D = REPO / "docs/data"
CENTRAL = (29.48313, 46.82388)
DISTRICTS = {"Борисовка", "Хомутяновка", "Протягайловка", "Парканы", "Гиска", "Северный"}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    g = EdgeGraph.load()
    src = g.snap_edge(*CENTRAL)
    print(f"origin off-road {src['off_road_m']} m; edge-state Dijkstra…")
    dist, _prev = g.dijkstra_from_snap(src)
    best_by_edge: dict[int, float] = {}
    for (e, _a), d in dist.items():
        if d < best_by_edge.get(e, float("inf")):
            best_by_edge[e] = d
    print(f"reachable edges: {len(best_by_edge)} / {len(g.edges)}")

    pts = [p for p in load_address_points()
           if p["service_status"] in ("standard", "low_density")
           and p["address_status"] == "verified_osm_address"]
    prev_km = {}
    for name in ("stage-09c-khomutyanovka-comparison.csv",
                 "stage-09c-protyagailovka-comparison.csv"):
        p = D / name
        if p.exists():
            for r in csv.DictReader(p.open(encoding="utf-8")):
                try:
                    prev_km[r["uid"]] = float(r["current_route_km"])
                except (KeyError, ValueError):
                    pass
    p = D / "stage-09b-metric-comparison.csv"
    if p.exists():
        for r in csv.DictReader(p.open(encoding="utf-8")):
            try:
                prev_km.setdefault(r["uid"], float(r["central_B_distance_km"]))
            except (KeyError, ValueError):
                pass

    rows = []
    stats: dict[str, dict] = {}
    for a in pts:
        d = (nearest_osm_place(a["lat"], a["lon"])[0]
             if a["settlement_ru"] == "Бендеры" else a["settlement_ru"])
        if a.get("district_ru") == "Северный":
            d = "Северный"
        if d not in DISTRICTS:
            continue
        snap = g.snap_edge(a["lon"], a["lat"])
        st = stats.setdefault(d, {"n": 0, "routable": 0, "with_prev": 0,
                                  "overstated": 0, "sum_off": 0.0})
        st["n"] += 1
        if not snap or snap["edge"] not in best_by_edge:
            rows.append({"uid": a["uid"], "district": d, "street": a["street_ru"],
                         "house": a["housenumber"], "current_zone": a["zone_id"],
                         "edge_valid_km": None, "off_road_m": snap["off_road_m"] if snap else None,
                         "previous_osrm_km": prev_km.get(a["uid"]),
                         "status": "UNREACHABLE_ON_EDGE_VALID_GRAPH",
                         "owner_review_required": True})
            continue
        km = round(max(best_by_edge[snap["edge"]]
                       - (1.0 - snap["t"]) * snap["edge_len_m"], 0.0) / 1000, 4)
        st["routable"] += 1
        st["sum_off"] += snap["off_road_m"]
        prev = prev_km.get(a["uid"])
        over = None
        if prev is not None:
            st["with_prev"] += 1
            over = prev > 1.10 * km
            if over:
                st["overstated"] += 1
        rows.append({"uid": a["uid"], "district": d, "street": a["street_ru"],
                     "house": a["housenumber"], "current_zone": a["zone_id"],
                     "edge_valid_km": km, "off_road_m": snap["off_road_m"],
                     "previous_osrm_km": prev,
                     "previous_minus_edge_valid_km": round(prev - km, 4) if prev is not None else None,  # noqa: E501
                     "overstated_gt_10pct": over,
                     "status": "OK", "owner_review_required": True})

    _csv("stage10c-edge-valid-by-address.csv", rows)
    summary = [{"district": k, "addresses": v["n"], "routable": v["routable"],
                "with_previous_km": v["with_prev"], "overstated_gt_10pct": v["overstated"],
                "mean_off_road_m": round(v["sum_off"] / v["routable"], 2) if v["routable"] else None,  # noqa: E501
                "basis": "edge-valid graph: turn restrictions + barriers + delivery access "
                         "+ edge snapping (partial edge length charged)",
                "owner_review_required": True}
               for k, v in sorted(stats.items())]
    _csv("stage10c-recompute-summary.csv", summary)
    for s in summary:
        print(f"  {s['district']:14s} n={s['addresses']:4d} routable={s['routable']:4d} "
              f"overstated={s['overstated_gt_10pct']:4d}/{s['with_previous_km']:4d} "
              f"mean_off_road={s['mean_off_road_m']} m")
    return 0


def _csv(name, rows):
    p = D / name
    if not rows:
        p.write_text("", encoding="utf-8")
        return
    cols = sorted({k for r in rows for k in r})
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
