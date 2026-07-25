#!/usr/bin/env python
"""Stage 10B — Protyagailovka: EVERY verified house through EVERY real entry.

Stage 10 never actually forced the Старого → Мира → Протягайловка corridor. Here
every one of the verified Protyagailovka homes is routed through every real,
graph-connected entry, exactly, using the independent distance-optimal Dijkstra:

    via_entry_km(house, entry) = d(origin -> entry) + d(entry -> house)

computed with one Dijkstra from the origin and one Dijkstra per entry (exact
single-source shortest paths, not sampling). Compared against the unconstrained
TRUE shortest path d(origin -> house). Read-only. No OSM edit, no immutable
release, no Direct, no price, no zone.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage09_engine import load_address_points  # noqa: E402
from stage10b_graph import CarGraph  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
D = REPO / "docs/data"
CENTRAL = (29.48313, 46.82388)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    g = CarGraph.load()

    houses = [p for p in load_address_points()
              if p["settlement_ru"] == "Протягайловка"
              and p["service_status"] in ("standard", "low_density")
              and p["address_status"] == "verified_osm_address"]
    entries = [e for e in csv.DictReader((D / "stage-09b-district-entries.csv").open(encoding="utf-8"))  # noqa: E501
               if e["district_or_settlement"] == "Протягайловка"
               and e["entry_lon"] and e["connected_to_city_graph"] == "True"]
    print(f"houses={len(houses)} real_entries={len(entries)}")

    # snap houses + entries once
    h_nodes, h_snap = {}, {}
    for p in houses:
        n, m = g.snap(p["lon"], p["lat"])
        h_nodes[p["uid"]] = n
        h_snap[p["uid"]] = m
    e_nodes = {}
    for e in entries:
        n, m = g.snap(float(e["entry_lon"]), float(e["entry_lat"]))
        e_nodes[e["entry_id"]] = (n, m, e)

    src, src_m = g.snap(*CENTRAL)
    print(f"origin snap {src_m} m; running origin Dijkstra…")
    d_origin, _pn, _pw = g.dijkstra(src)

    # exact single-source distances from every entry
    per_entry = {}
    for i, (eid, (enode, _em, _e)) in enumerate(e_nodes.items(), 1):
        d_e, _a, _b = g.dijkstra(enode)
        per_entry[eid] = d_e
        if i % 5 == 0 or i == len(e_nodes):
            print(f"  entry Dijkstra {i}/{len(e_nodes)}")

    rows = []
    best_entry_counts: dict[str, int] = {}
    overstated = 0
    for p in houses:
        hn = h_nodes[p["uid"]]
        free_km = round(d_origin.get(hn, float("inf")) / 1000, 4) if hn in d_origin else None
        best = None
        via = {}
        for eid, (enode, _m, e) in e_nodes.items():
            de = d_origin.get(enode)
            dh = per_entry[eid].get(hn)
            if de is None or dh is None:
                continue
            km = round((de + dh) / 1000, 4)
            via[eid] = km
            if best is None or km < best[1]:
                best = (eid, km, e)
        if best is None or free_km is None:
            continue
        best_entry_counts[best[0]] = best_entry_counts.get(best[0], 0) + 1
        # a house is "overstated" if the best real entry route beats the current
        # OSRM-fastest-based km by >10 % (see stage-09c comparison for current km)
        rows.append({
            "uid": p["uid"], "street": p["street_ru"], "house": p["housenumber"],
            "current_zone": p["zone_id"], "snap_m": h_snap[p["uid"]],
            "true_shortest_unconstrained_km": free_km,
            "best_entry_id": best[0], "best_entry_road": best[2]["road_name"],
            "best_via_entry_km": best[1],
            "via_entry_minus_free_km": round(best[1] - free_km, 4),
            "entries_evaluated": len(via),
            "all_entry_km_json": json.dumps(via, ensure_ascii=False),
            "owner_review_required": True,
        })

    _csv("stage10b-protyagailovka-entry-matrix.csv", rows)

    # cross-check against the earlier OSRM-based current route
    prev = {r["uid"]: r for r in csv.DictReader(
        (D / "stage-09c-protyagailovka-comparison.csv").open(encoding="utf-8"))} \
        if (D / "stage-09c-protyagailovka-comparison.csv").exists() else {}
    cmp_rows = []
    for r in rows:
        pv = prev.get(r["uid"])
        if not pv:
            continue
        try:
            cur = float(pv["current_route_km"])
        except (KeyError, ValueError):
            continue
        gap = round(cur - r["true_shortest_unconstrained_km"], 4)
        if cur > 1.10 * r["true_shortest_unconstrained_km"]:
            overstated += 1
        cmp_rows.append({**r, "osrm_current_route_km": cur,
                         "current_minus_true_shortest_km": gap,
                         "overstated_gt_10pct": cur > 1.10 * r["true_shortest_unconstrained_km"]})
    _csv("stage10b-protyagailovka-vs-current.csv", cmp_rows)

    print(f"rows={len(rows)}; overstated vs TRUE shortest (>10%)={overstated}/{len(cmp_rows)}")
    print("best-entry distribution:", dict(sorted(best_entry_counts.items(),
                                                  key=lambda kv: -kv[1])[:8]))
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
