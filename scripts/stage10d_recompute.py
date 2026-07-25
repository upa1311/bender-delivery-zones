#!/usr/bin/env python
"""Stage 10D — recompute every verified address with correct bidirectional snaps.

Stage 10C seeded only ONE directed edge per snap and accepted arrival only on
that edge, so any address whose segment happened to be indexed in the other
direction looked UNREACHABLE. Here each address snaps to one physical position
and ALL of its legal directed states, and arrival is accepted from every legal
direction.

Endpoint-only ways (`access=delivery` / `destination`) are not transit: the public
network is solved once, then each restricted component is solved locally, seeded
from the public distances at its boundary — so a van may enter a restricted area
to serve an address inside it, but never cut through it.

Read-only. No OSM edit, no immutable release, no Direct, no price, no zone.
"""

from __future__ import annotations

import csv
import heapq
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage09_engine import load_address_points, nearest_osm_place  # noqa: E402
from stage10d_graph import Graph  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
D = REPO / "docs/data"
CENTRAL = (29.48313, 46.82388)
DISTRICTS = {"Борисовка", "Хомутяновка", "Протягайловка", "Парканы", "Гиска", "Северный"}


def solve_restricted_components(g: Graph, best: dict[int, float]) -> dict[int, float]:
    """Extend public distances into each endpoint-only component from its boundary."""
    by_comp: dict[int, list[int]] = {}
    for pid, comp in g.phys_component.items():
        by_comp.setdefault(comp, []).append(pid)
    extra: dict[int, float] = {}
    for _comp, pids in by_comp.items():
        edges = {e for pid in pids for e in g.phys_dirs[pid]}
        seed: dict[int, float] = {}
        for e in edges:
            u = g.edges[e][0]
            for pe in g.node_out.get(u, ()):
                if pe in edges:
                    continue
                d = best.get(pe)
                if d is not None and d < seed.get(u, math.inf):
                    seed[u] = d
        if not seed:
            continue
        dist = dict(seed)
        pq = [(d, n) for n, d in seed.items()]
        heapq.heapify(pq)
        seen = set()
        while pq:
            d, n = heapq.heappop(pq)
            if n in seen:
                continue
            seen.add(n)
            for e in g.node_out.get(n, ()):
                if e not in edges:
                    continue
                nd = d + g.edges[e][2]
                v = g.edges[e][1]
                if nd < extra.get(e, math.inf):
                    extra[e] = nd
                if nd < dist.get(v, math.inf):
                    dist[v] = nd
                    heapq.heappush(pq, (nd, v))
    return extra


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    g = Graph.load()
    src = g.snap(*CENTRAL)
    print(f"origin off-road {src['off_road_m']} m, {len(src['states'])} directed states")
    best = g.best_by_edge(g.dijkstra(src, set()))
    best.update({e: d for e, d in solve_restricted_components(g, best).items()
                 if d < best.get(e, math.inf)})
    print(f"reachable directed edges: {len(best)} / {len(g.edges)}")

    prev_km: dict[str, float] = {}
    for name, col in (("stage10c-edge-valid-by-address.csv", "edge_valid_km"),):
        p = D / name
        if p.exists():
            for r in csv.DictReader(p.open(encoding="utf-8")):
                try:
                    prev_km[r["uid"]] = float(r[col])
                except (KeyError, ValueError, TypeError):
                    pass

    rows, stats = [], {}
    for a in load_address_points():
        if a["service_status"] not in ("standard", "low_density"):
            continue
        if a["address_status"] != "verified_osm_address":
            continue
        d = (nearest_osm_place(a["lat"], a["lon"])[0]
             if a["settlement_ru"] == "Бендеры" else a["settlement_ru"])
        if a.get("district_ru") == "Северный":
            d = "Северный"
        if d not in DISTRICTS:
            continue
        st = stats.setdefault(d, {"n": 0, "routable": 0, "sum_off": 0.0, "states": 0})
        st["n"] += 1
        snap = g.snap(a["lon"], a["lat"])
        km = None
        if snap:
            st["sum_off"] += snap["off_road_m"]
            st["states"] += len(snap["states"])
            metres = g.arrive(best, snap)
            same = g.same_segment_distance(src, snap)
            vals = [x for x in (metres, same) if x is not None]
            if vals:
                km = round(min(vals) / 1000, 4)
                st["routable"] += 1
        rows.append({
            "uid": a["uid"], "district": d, "street": a["street_ru"],
            "house": a["housenumber"], "current_zone": a["zone_id"],
            "km_10d": km, "off_road_m": snap["off_road_m"] if snap else None,
            "directed_states": len(snap["states"]) if snap else 0,
            "km_10c": prev_km.get(a["uid"]),
            "status": "OK" if km is not None else "UNREACHABLE",
            "owner_review_required": True,
        })

    _csv("stage10d-by-address.csv", rows)
    summary = [{"district": k,
                "addresses": v["n"], "routable": v["routable"],
                "unreachable": v["n"] - v["routable"],
                "mean_directed_states_per_snap": round(v["states"] / v["n"], 2) if v["n"] else None,
                "mean_off_road_m": round(v["sum_off"] / v["n"], 2) if v["n"] else None,
                "basis": "bidirectional multi-state snap + endpoint-aware access + "
                         "turn restrictions + barriers",
                "owner_review_required": True}
               for k, v in sorted(stats.items())]
    _csv("stage10d-recompute-summary.csv", summary)
    for s in summary:
        print(f"  {s['district']:14s} n={s['addresses']:4d} routable={s['routable']:4d} "
              f"unreachable={s['unreachable']:3d} states/snap={s['mean_directed_states_per_snap']}")
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
