#!/usr/bin/env python
"""Stage 10D — transit corridors: stops are LANDMARKS, not a street chain.

Stage 10C turned the owner's bus-stop names into a mandatory street sequence and
then declared the corridor "unresolved" because consecutive stop-streets do not
touch. That conclusion was unsound: a stop list is a set of landmarks, not a
guaranteed ordered list of streets, and the real corridor is the operator's
polyline.

Until the EasyWay polyline (forward and reverse) is available and map-matched to
OSM edges, this reports `TRANSIT_POLYLINE_MISSING` and draws NO conclusion about
continuity or breaks. What it does compute — as supporting information only — is,
for each pair of consecutive landmark streets, the minimal LEGAL ROAD PATH
between them using the full legality engine (barriers + turn restrictions +
endpoint-aware access), searched from ALL candidate nodes of one street to ALL of
the other, rather than picking the nearest straight-line pair first.

Read-only. No OSM edit, no immutable release, no Direct, no price, no zone.
"""

from __future__ import annotations

import csv
import heapq
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage10d_graph import Graph  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
D = REPO / "docs/data"

STREET_OSM_NAMES = {
    "Тираспольская": ["Тираспольская улица"], "Титова": ["улица Титова"],
    "Кишинёвская": ["Кишинёвская улица"], "Хмельницкого": ["улица Богдана Хмельницкого"],
    "50 лет ВЛКСМ": ["улица 50 лет ВЛКСМ"], "Осипенко": ["улица Осипенко"],
    "Дружбы": ["улица Дружбы"], "Ечина": ["улица Ечина"],
    "Главана": ["улица Бориса Главана", "переулок Главана"], "Старого": ["улица Старого"],
    "Московская": ["Московская улица"], "Первомайская": ["Первомайская улица"],
    "Некрасова": ["улица Некрасова"], "Мира": ["улица Мира"],
}
CORRIDORS = {
    "BORISOVKA": {"district": "Борисовка", "landmarks":
                  ["Тираспольская", "Титова", "Кишинёвская", "Хмельницкого",
                   "50 лет ВЛКСМ", "Осипенко"]},
    "KHOMUTYANOVKA_A": {"district": "Хомутяновка", "landmarks":
                        ["Дружбы", "Ечина", "Главана", "Старого"]},
    "KHOMUTYANOVKA_B": {"district": "Хомутяновка", "landmarks":
                        ["Московская", "Первомайская", "Некрасова", "Ечина",
                         "Главана", "Старого"]},
    "PROTYAGAILOVKA": {"district": "Протягайловка", "landmarks": ["Старого", "Мира"]},
}


def street_edges(g: Graph, street: str) -> list[int]:
    names = set(STREET_OSM_NAMES.get(street, [street]))
    ways = {w for w, t in g.way_tags.items() if (t.get("name") or "") in names}
    return [i for i, e in enumerate(g.edges) if e[3] in ways]


def nodes_of(g: Graph, edges: list[int]) -> set[int]:
    s = set()
    for e in edges:
        s.add(g.edges[e][0])
        s.add(g.edges[e][1])
    return s


def legal_path_between(g: Graph, from_nodes: set[int], to_nodes: set[int]):
    """Minimal LEGAL road path from ANY node of A to ANY node of B.

    Multi-source Dijkstra over the full legality engine — never 'nearest
    straight-line pair first'. Turn restrictions need an incoming edge, so the
    search is seeded on every edge leaving a source node.
    """
    dist: dict[tuple, float] = {}
    pq = []
    for n in from_nodes:
        for e in g.node_out.get(n, ()):
            if not g._edge_ok(e, set()):
                continue
            key = (e, None)
            if g.edges[e][2] < dist.get(key, math.inf):
                dist[key] = g.edges[e][2]
                heapq.heappush(pq, (g.edges[e][2], e, None))
    seen = set()
    while pq:
        d, e, via = heapq.heappop(pq)
        if (e, via) in seen:
            continue
        seen.add((e, via))
        u, v, _l, w_in, _p = g.edges[e]
        if v in to_nodes:
            return round(d, 1)
        for eo in g.node_out.get(v, ()):
            if not g._edge_ok(eo, set()) or not g._turn_ok(e, eo):
                continue
            nvia, blocked = g._via_next(via, w_in, g.edges[eo][3])
            if blocked:
                continue
            nd = d + g.edges[eo][2]
            key = (eo, nvia)
            if nd < dist.get(key, math.inf):
                dist[key] = nd
                heapq.heappush(pq, (nd, eo, nvia))
    return None


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    g = Graph.load()
    rows, links = [], []
    for key, spec in CORRIDORS.items():
        present, absent = [], []
        sets = {}
        for s in spec["landmarks"]:
            e = street_edges(g, s)
            sets[s] = e
            (present if e else absent).append(s)
        for a, b in zip(spec["landmarks"], spec["landmarks"][1:], strict=False):
            if not sets[a] or not sets[b]:
                continue
            m = legal_path_between(g, nodes_of(g, sets[a]), nodes_of(g, sets[b]))
            links.append({
                "corridor": key, "from_landmark": a, "to_landmark": b,
                "minimal_legal_road_path_m": m,
                "note": "supporting information only — NOT a continuity verdict",
                "owner_review_required": True,
            })
        rows.append({
            "corridor": key, "district": spec["district"],
            "landmarks_are_stops_not_streets": True,
            "landmark_count": len(spec["landmarks"]),
            "landmark_streets_present_in_graph": len(present),
            "landmark_streets_absent": ",".join(absent),
            "verdict": "TRANSIT_POLYLINE_MISSING",
            "required_to_conclude": "EasyWay stop coordinates + forward and reverse "
                                    "polyline, map-matched to OSM edges",
            "easyway_status": "web bot-blocked (HTTP 403); polyline NOT fetched, NOT fabricated",
            "continuity_conclusion": "NONE — not asserted without the polyline",
            "owner_review_required": True,
        })
    _csv("stage10d-corridor-status.csv", rows)
    _csv("stage10d-corridor-legal-connectors.csv", links)
    (D / "stage10d-graph-provenance.json").write_text(
        json.dumps(g.provenance, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    for r in rows:
        print(f"{r['corridor']:16s} {r['verdict']} landmarks_present="
              f"{r['landmark_streets_present_in_graph']}/{r['landmark_count']}")
    for x in links:
        print(f"   {x['from_landmark']:14s} -> {x['to_landmark']:14s} "
              f"legal road path {x['minimal_legal_road_path_m']} m")
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
