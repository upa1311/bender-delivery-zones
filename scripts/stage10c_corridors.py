#!/usr/bin/env python
"""Stage 10C — corridor map matching with proven CONTINUITY and DIRECTION.

Stage 10B picked one way per street greedily, silently dropped streets (Главана
vanished from Corridors A and B), accepted huge anchor gaps, and "verified"
traversal by testing whether a way id merely appeared — which let a oneway street
(Титова) be reported traversable in reverse via a loop.

Here, for every owner corridor:

  * **all** OSM ways carrying each street name are used (a street is an EDGE SET,
    not one way);
  * consecutive streets must meet at a SHARED NODE, or via a documented
    connecting edge; a gap over 50 m ⇒ `CORRIDOR_UNRESOLVED`;
  * a street that cannot be resolved is never silently omitted — the corridor is
    marked unresolved and the missing street is named (Главана is mandatory in
    Corridors A and B);
  * each street is traversed entry_node → exit_node using ONLY that street's own
    directed edges, so the traversal proves direction; a oneway street simply has
    no legal reverse traversal and can never be reported reverse-traversable by
    looping through other roads;
  * forward and reverse are computed independently.

Read-only. No OSM edit, no immutable release, no Direct, no price, no zone.
"""

from __future__ import annotations

import csv
import heapq
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage10c_graph import EdgeGraph, haversine_m  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
D = REPO / "docs/data"
CENTRAL = (29.48313, 46.82388)
MAX_GAP_M = 50.0

# Each corridor street maps to the EXACT OSM name(s) that carry it. Exact matching
# is required in both directions: substring matching both MISSED "улица Бориса
# Главана" (the owner's «Главана» — silently dropped in Stage 10B) and would have
# wrongly absorbed a different street ("улица Дружбы Народов" into "улица Дружбы").
STREET_OSM_NAMES = {
    "Тираспольская": ["Тираспольская улица"],
    "Титова": ["улица Титова"],
    "Кишинёвская": ["Кишинёвская улица"],
    "Хмельницкого": ["улица Богдана Хмельницкого"],
    "50 лет ВЛКСМ": ["улица 50 лет ВЛКСМ"],
    "Осипенко": ["улица Осипенко"],
    "Дружбы": ["улица Дружбы"],
    "Ечина": ["улица Ечина"],
    "Главана": ["улица Бориса Главана", "переулок Главана"],
    "Старого": ["улица Старого"],
    "Московская": ["Московская улица"],
    "Первомайская": ["Первомайская улица"],
    "Некрасова": ["улица Некрасова"],
    "Мира": ["улица Мира"],
}

CORRIDORS = {
    "BORISOVKA": {
        "district": "Борисовка",
        "streets": ["Тираспольская", "Титова", "Кишинёвская", "Хмельницкого",
                    "50 лет ВЛКСМ", "Осипенко"],
    },
    "KHOMUTYANOVKA_A": {
        "district": "Хомутяновка",
        "streets": ["Дружбы", "Ечина", "Главана", "Старого"],
    },
    "KHOMUTYANOVKA_B": {
        "district": "Хомутяновка",
        "streets": ["Московская", "Первомайская", "Некрасова", "Ечина", "Главана", "Старого"],
    },
    "PROTYAGAILOVKA": {
        "district": "Протягайловка",
        "streets": ["Старого", "Мира"],
    },
}
MANDATORY = {"KHOMUTYANOVKA_A": ["Главана"], "KHOMUTYANOVKA_B": ["Главана"]}


def street_edges(g: EdgeGraph, street: str) -> list[int]:
    """All directed edges of every OSM way carrying this street (EXACT names)."""
    accepted = set(STREET_OSM_NAMES.get(street, [street]))
    wanted = {wid for wid, t in g.way_tags.items() if (t.get("name") or "") in accepted}
    return [i for i, (_u, _v, _m, w) in enumerate(g.edges) if w in wanted]


def edge_nodes(g: EdgeGraph, edges: list[int]) -> set[int]:
    s = set()
    for e in edges:
        u, v, _m, _w = g.edges[e]
        s.add(u)
        s.add(v)
    return s


def restricted_path(g: EdgeGraph, allowed: set[int], start: int, goal: int):
    """Shortest path from `start` to `goal` using ONLY `allowed` directed edges.
    Proves the street itself is traversable in that direction (no outside loop)."""
    dist = {start: 0.0}
    prev: dict[int, tuple[int, int]] = {}
    pq = [(0.0, start)]
    seen = set()
    while pq:
        d, n = heapq.heappop(pq)
        if n in seen:
            continue
        seen.add(n)
        if n == goal:
            break
        for e in g.node_out.get(n, ()):
            if e not in allowed:
                continue
            _u, v, m, _w = g.edges[e]
            nd = d + m
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = (n, e)
                heapq.heappush(pq, (nd, v))
    if goal not in dist:
        return None
    ways, edges_used, cur = [], [], goal
    while cur != start:
        p, e = prev[cur]
        edges_used.append(e)
        w = g.edges[e][3]
        if not ways or ways[-1] != w:
            ways.append(w)
        cur = p
    ways.reverse()
    edges_used.reverse()
    return {"metres": round(dist[goal], 1), "way_ids": ways, "edges": edges_used}


def connect(g: EdgeGraph, nodes_a: set[int], nodes_b: set[int]):
    """A shared node, else a DOCUMENTED connecting road path between two streets.

    A straight-line gap is never accepted as a connection: when the streets do not
    share a node we route the connector over real edges and record its length and
    the ways it uses, so the owner sees exactly what lies between them.
    """
    shared = nodes_a & nodes_b
    if shared:
        n = next(iter(shared))
        return {"type": "shared_node", "node": n, "gap_m": 0.0,
                "connector_road_m": 0.0, "connector_ways": ""}
    best = None
    for a in nodes_a:
        alon, alat = g.coords[a]
        for b in nodes_b:
            blon, blat = g.coords[b]
            m = haversine_m(alat, alon, blat, blon)
            if best is None or m < best["gap_m"]:
                best = {"type": "connecting_edge", "from_node": a, "to_node": b,
                        "gap_m": round(m, 1)}
    if best is None:
        return {"type": "none", "gap_m": float("inf"), "connector_road_m": None,
                "connector_ways": ""}
    conn = restricted_path(g, set(range(len(g.edges))), best["from_node"], best["to_node"])
    best["connector_road_m"] = conn["metres"] if conn else None
    best["connector_ways"] = ",".join(str(w) for w in (conn["way_ids"][:6] if conn else []))
    if conn is None:
        best["type"] = "unroutable_gap"
    return best


def match_corridor(g: EdgeGraph, key: str, spec: dict, reverse: bool = False):
    streets = list(spec["streets"])
    if reverse:
        streets.reverse()
    sets = {}
    missing = []
    for s in streets:
        e = street_edges(g, s)
        if not e:
            missing.append(s)
        sets[s] = e

    problems = list(f"STREET_NOT_IN_GRAPH:{s}" for s in missing)
    for must in MANDATORY.get(key, []):
        if must in streets and (must in missing):
            problems.append(f"MANDATORY_STREET_MISSING:{must}")

    # junctions between consecutive streets
    links, segs = [], []
    for a, b in zip(streets, streets[1:], strict=False):
        if not sets[a] or not sets[b]:
            links.append({"from_street": a, "to_street": b, "type": "none", "gap_m": None})
            continue
        link = connect(g, edge_nodes(g, sets[a]), edge_nodes(g, sets[b]))
        links.append({"from_street": a, "to_street": b, **link})
        if link["gap_m"] > MAX_GAP_M:
            problems.append(f"GAP_{int(link['gap_m'])}m:{a}->{b}")

    # traverse each street entry->exit using ONLY its own edges (proves direction)
    approach_node = None
    src_snap = g.snap_edge(*CENTRAL)
    origin_node = g.edges[src_snap["edge"]][1]
    for i, s in enumerate(streets):
        if not sets[s]:
            segs.append({"corridor": key, "direction": "reverse" if reverse else "forward",
                         "street": s, "status": "NO_EDGES"})
            continue
        nodes = edge_nodes(g, sets[s])
        entry = (links[i - 1].get("node") or links[i - 1].get("to_node")) if i > 0 else None
        if entry is None or entry not in nodes:
            ref = approach_node if approach_node is not None else origin_node
            rlon, rlat = g.coords[ref]
            entry = min(nodes, key=lambda n: haversine_m(rlat, rlon, g.coords[n][1], g.coords[n][0]))  # noqa: E501
        if i < len(streets) - 1:
            nxt = links[i]
            exit_n = nxt.get("node") or nxt.get("from_node")
        else:
            elon, elat = g.coords[entry]
            exit_n = max(nodes, key=lambda n: haversine_m(elat, elon, g.coords[n][1], g.coords[n][0]))  # noqa: E501
        if exit_n not in nodes:
            exit_n = max(nodes, key=lambda n: haversine_m(g.coords[entry][1], g.coords[entry][0],
                                                          g.coords[n][1], g.coords[n][0]))
        allowed = set(sets[s])
        path = restricted_path(g, allowed, entry, exit_n) if entry != exit_n else {
            "metres": 0.0, "way_ids": [], "edges": []}
        tags_sample = g.way_tags.get(g.edges[sets[s][0]][3], {})
        segs.append({
            "corridor": key, "direction": "reverse" if reverse else "forward",
            "street": s, "ways_in_street": len({g.edges[e][3] for e in sets[s]}),
            "directed_edges_in_street": len(sets[s]),
            "entry_node": entry, "exit_node": exit_n,
            "traversed_within_street": bool(path),
            "traversed_metres": path["metres"] if path else None,
            "traversed_way_ids": ",".join(str(w) for w in (path["way_ids"] if path else [])),
            "oneway_tag": tags_sample.get("oneway") or "",
            "highway": tags_sample.get("highway") or "",
            "status": "OK" if path else "NO_LEGAL_TRAVERSAL_IN_DIRECTION",
        })
        if not path:
            problems.append(f"NO_LEGAL_TRAVERSAL:{s}")
        approach_node = exit_n
    verdict = "CORRIDOR_CONTINUOUS" if not problems else "CORRIDOR_UNRESOLVED"
    return verdict, problems, links, segs


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    g = EdgeGraph.load()
    rows, seg_rows, link_rows = [], [], []
    for key, spec in CORRIDORS.items():
        for reverse in (False, True):
            verdict, problems, links, segs = match_corridor(g, key, spec, reverse)
            direction = "reverse" if reverse else "forward"
            rows.append({
                "corridor": key, "district": spec["district"], "direction": direction,
                "streets_declared": len(spec["streets"]),
                "streets_resolved": sum(1 for s in segs if s.get("status") == "OK"),
                "streets_in_order": " -> ".join(spec["streets"][::-1] if reverse else spec["streets"]),  # noqa: E501
                "verdict": verdict, "problems": ";".join(problems),
                "max_gap_m": max([x["gap_m"] for x in links if x.get("gap_m") is not None], default=0),  # noqa: E501
                "mandatory_streets": ",".join(MANDATORY.get(key, [])),
                "owner_review_required": True,
            })
            seg_rows.extend(segs)
            for x in links:
                link_rows.append({"corridor": key, "direction": direction, **x})
    _csv("stage10c-corridor-verification.csv", rows)
    _csv("stage10c-corridor-segments.csv", seg_rows)
    _csv("stage10c-corridor-links.csv", link_rows)
    (D / "stage10c-graph-provenance.json").write_text(
        json.dumps(g.provenance, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    for r in rows:
        print(f"{r['corridor']:16s} {r['direction']:7s} {r['verdict']:20s} "
              f"streets {r['streets_resolved']}/{r['streets_declared']} "
              f"max_gap {r['max_gap_m']}m {r['problems'][:90]}")
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
