#!/usr/bin/env python
"""Stage 10B — CORRIDOR-CONSTRAINED ROUTING TRUTH.

Fixes the Stage 10 shortcuts:
  * a corridor is no longer forced by ONE waypoint — it is resolved to an ORDERED
    list of OSM way IDs with mandatory graph nodes, and the route must traverse
    every mandatory way, in order, in the required direction;
  * arrival at a waypoint by an outside detour is REJECTED: after routing we read
    the actually-traversed way IDs and verify each mandatory way is really on the
    path (`DETOUR_ARRIVAL` otherwise);
  * forward and reverse are computed separately;
  * oneway / access come from real OSM tags (never from a distance difference);
  * turn restrictions touching the corridor are read from OSM relations;
  * the comparison baseline is the TRUE distance-optimal Dijkstra path over the
    same car graph — not `alternatives=3`;
  * every result is WRITTEN TO FILES and consumed from them (no hardcoded values).

Read-only. No OSM edit, no immutable release, no Direct, no price, no zone.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import osmium

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage10b_graph import CarGraph, haversine_m, oneway_flags  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
D = REPO / "docs/data"
FULL_PBF = REPO / "data/raw/moldova-latest.osm.pbf"
RESTR_CACHE = REPO / "data/interim/stage10b-restrictions.json"
CENTRAL = (29.48313, 46.82388)

# Owner-confirmed corridors. Landmarks (пл. Героев / Пивзавод / Маслоэкстракционный
# завод / Роддом / больница) are BUS STOPS, not streets: they are recorded as
# anchors and the corridor is enforced on the streets that carry them.
CORRIDORS = {
    "BORISOVKA": {
        "streets": ["Тираспольская улица", "улица Титова", "Кишинёвская улица",
                    "улица Богдана Хмельницкого", "улица 50 лет ВЛКСМ", "улица Осипенко"],
        "anchors": ["Борисовский рынок"],
        "district": "Борисовка",
    },
    "KHOMUTYANOVKA_A": {
        "streets": ["улица Дружбы", "улица Ечина", "улица Главана", "улица Старого"],
        "anchors": ["пл. Героев", "Молдплодовощ", "Пивзавод (ул. Дружбы 7)",
                    "Маслоэкстракционный завод", "Роддом", "Городская больница"],
        "district": "Хомутяновка",
    },
    "KHOMUTYANOVKA_B": {
        "streets": ["Московская улица", "Первомайская улица", "улица Некрасова",
                    "улица Ечина", "улица Главана", "улица Старого"],
        "anchors": ["Центральный рынок", "Строймаркет Луч", "Роддом", "Городская больница"],
        "district": "Хомутяновка",
    },
    "PROTYAGAILOVKA": {
        "streets": ["улица Старого", "улица Мира"],
        "anchors": ["точный въезд в Протягайловку (из entries)"],
        "district": "Протягайловка",
    },
}


class _Restrictions(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.rows = []

    def relation(self, r):
        tags = dict(r.tags)
        if tags.get("type") != "restriction":
            return
        frm = [m.ref for m in r.members if m.role == "from" and m.type == "w"]
        to = [m.ref for m in r.members if m.role == "to" and m.type == "w"]
        via_w = [m.ref for m in r.members if m.role == "via" and m.type == "w"]
        via_n = [m.ref for m in r.members if m.role == "via" and m.type == "n"]
        self.rows.append({"relation_id": r.id,
                          "restriction": tags.get("restriction") or tags.get("restriction:motorcar") or "",  # noqa: E501
                          "from_ways": frm, "to_ways": to, "via_ways": via_w, "via_nodes": via_n})


def load_restrictions() -> list[dict]:
    if RESTR_CACHE.exists():
        return json.loads(RESTR_CACHE.read_text("utf-8"))
    h = _Restrictions()
    h.apply_file(str(FULL_PBF))
    RESTR_CACHE.parent.mkdir(parents=True, exist_ok=True)
    RESTR_CACHE.write_text(json.dumps(h.rows, ensure_ascii=False), encoding="utf-8", newline="\n")
    return h.rows


def ways_named(g: CarGraph, name: str) -> list[int]:
    out = []
    for wid, tags in g.way_tags.items():
        nm = tags.get("name") or ""
        if nm == name or (name.lower() in nm.lower() and nm):
            out.append(wid)
    return out


def way_endpoints(g: CarGraph, wid: int) -> list[int]:
    """Graph nodes belonging to this way (ordered by adjacency appearance)."""
    nodes = []
    for n, edges in g.adj.items():
        for _v, _m, w in edges:
            if w == wid:
                nodes.append(n)
                break
    return nodes


def resolve_chain(g: CarGraph, streets: list[str], start_lonlat) -> list[dict]:
    """Greedy chain: for each street pick the way nearest the running anchor and
    orient it, producing an ORDERED list of mandatory ways with entry/exit nodes."""
    anchor_node, _ = g.snap(*start_lonlat)
    chain = []
    for name in streets:
        cands = ways_named(g, name)
        best = None
        for wid in cands:
            nodes = way_endpoints(g, wid)
            if len(nodes) < 2:
                continue
            alon, alat = g.coords[anchor_node]
            near = min(nodes, key=lambda n: haversine_m(alat, alon, g.coords[n][1], g.coords[n][0]))
            far = max(nodes, key=lambda n: haversine_m(g.coords[near][1], g.coords[near][0],
                                                      g.coords[n][1], g.coords[n][0]))
            d = haversine_m(alat, alon, g.coords[near][1], g.coords[near][0])
            if best is None or d < best["anchor_gap_m"]:
                best = {"street": name, "way_id": wid, "entry_node": near, "exit_node": far,
                        "anchor_gap_m": round(d, 1)}
        if best:
            tags = g.way_tags.get(best["way_id"], {})
            fwd, bwd = oneway_flags(tags)
            best.update({
                "highway": tags.get("highway"), "oneway_tag": tags.get("oneway") or "",
                "oneway_forward_allowed": fwd, "oneway_backward_allowed": bwd,
                "access": tags.get("access") or "", "motor_vehicle": tags.get("motor_vehicle") or "",  # noqa: E501
                "bridge": tags.get("bridge") or "", "tunnel": tags.get("tunnel") or "",
                "layer": tags.get("layer") or "", "maxspeed": tags.get("maxspeed") or "",
            })
            chain.append(best)
            anchor_node = best["exit_node"]
    return chain


def routed_chain(g: CarGraph, waypoint_nodes: list[int]):
    """Route through mandatory nodes IN ORDER; return total km, traversed ways, geometry."""
    total_m, ways, geom, hops = 0.0, [], [], []
    for a, b in zip(waypoint_nodes, waypoint_nodes[1:], strict=False):
        if a == b:
            continue
        dist, pn, pw = g.dijkstra(a, targets={b})
        if b not in dist:
            return None
        p = g.path(a, b, pn, pw)
        total_m += dist[b]
        hops.append({"from_node": a, "to_node": b, "km": round(dist[b] / 1000, 4),
                     "way_ids": p["way_ids"]})
        for w in p["way_ids"]:
            if not ways or ways[-1] != w:
                ways.append(w)
        geom.extend(p["geometry"] if not geom else p["geometry"][1:])
    return {"distance_km": round(total_m / 1000, 4), "way_ids": ways, "geometry": geom, "hops": hops}  # noqa: E501


def verify_traversal(chain, traversed: list[int]) -> tuple[bool, list[str]]:
    """Every mandatory way must appear, in the corridor order (no detour arrival)."""
    problems, pos = [], -1
    for step in chain:
        wid = step["way_id"]
        try:
            idx = traversed.index(wid, pos + 1)
        except ValueError:
            problems.append(f"DETOUR_ARRIVAL:{step['street']}({wid}) not traversed")
            continue
        pos = idx
    return (not problems), problems


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    g = CarGraph.load()
    restrictions = load_restrictions()
    entries = list(csv.DictReader((D / "stage-09b-district-entries.csv").open(encoding="utf-8")))

    seg_rows, corridor_rows, feats = [], [], []
    for key, spec in CORRIDORS.items():
        chain = resolve_chain(g, spec["streets"], CENTRAL)
        # Protyagailovka: append the exact verified entry as the final mandatory node
        final_node = None
        if key == "PROTYAGAILOVKA":
            cand = [e for e in entries
                    if e["district_or_settlement"] == "Протягайловка"
                    and e["entry_lon"] and e["connected_to_city_graph"] == "True"]
            if cand:
                best = min(cand, key=lambda e: haversine_m(
                    g.coords[chain[-1]["exit_node"]][1], g.coords[chain[-1]["exit_node"]][0],
                    float(e["entry_lat"]), float(e["entry_lon"])))
                final_node, _ = g.snap(float(best["entry_lon"]), float(best["entry_lat"]))
                spec["anchors"] = [f"entry {best['entry_id']} {best['road_name']}"]

        # mandatory node sequence, forward and reverse
        seq = [g.snap(*CENTRAL)[0]]
        for step in chain:
            seq += [step["entry_node"], step["exit_node"]]
        if final_node:
            seq.append(final_node)
        fwd = routed_chain(g, seq)
        rev = routed_chain(g, list(reversed(seq)))
        ok_f, prob_f = verify_traversal(chain, fwd["way_ids"]) if fwd else (False, ["UNROUTABLE"])
        ok_r, prob_r = verify_traversal(list(reversed(chain)), rev["way_ids"]) if rev else (False, ["UNROUTABLE"])  # noqa: E501

        # unconstrained TRUE shortest to the corridor end (same endpoints)
        end_lonlat = g.coords[seq[-1]]
        free = g.shortest(CENTRAL, end_lonlat)

        corr_ways = {s["way_id"] for s in chain}
        rel = [r for r in restrictions
               if corr_ways & set(r["from_ways"]) or corr_ways & set(r["to_ways"])]

        corridor_rows.append({
            "corridor": key, "district": spec["district"],
            "streets_in_order": " -> ".join(s["street"] for s in chain),
            "mandatory_way_ids": ",".join(str(s["way_id"]) for s in chain),
            "mandatory_node_count": len(seq),
            "forward_km": fwd["distance_km"] if fwd else None,
            "reverse_km": rev["distance_km"] if rev else None,
            "forward_all_mandatory_ways_traversed": ok_f,
            "reverse_all_mandatory_ways_traversed": ok_r,
            "forward_problems": ";".join(prob_f), "reverse_problems": ";".join(prob_r),
            "oneway_asymmetric_by_TAGS": any(not s["oneway_backward_allowed"] for s in chain),
            "oneway_ways_by_tag": ",".join(str(s["way_id"]) for s in chain
                                           if not s["oneway_backward_allowed"]),
            "true_shortest_free_km": free["distance_km"] if free else None,
            "corridor_minus_free_km": round(fwd["distance_km"] - free["distance_km"], 4)
            if fwd and free else None,
            "turn_restrictions_touching_corridor": len(rel),
            "anchors_bus_stops_not_enforced": " | ".join(spec["anchors"]),
            "owner_review_required": True,
        })
        for s in chain:
            seg_rows.append({"corridor": key, **s})
        if fwd:
            feats.append({"type": "Feature",
                          "geometry": {"type": "LineString", "coordinates": fwd["geometry"]},
                          "properties": {"corridor": key, "kind": "corridor_forced_forward",
                                         "distance_km": fwd["distance_km"]}})
        if free:
            feats.append({"type": "Feature",
                          "geometry": {"type": "LineString", "coordinates": free["geometry"]},
                          "properties": {"corridor": key, "kind": "true_shortest_unconstrained",
                                         "distance_km": free["distance_km"]}})

    _csv("stage10b-corridor-segments.csv", seg_rows)
    _csv("stage10b-corridor-verification.csv", corridor_rows)
    (D / "stage10b-corridor-routes.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False),
        encoding="utf-8", newline="\n")

    for r in corridor_rows:
        print(f"{r['corridor']:18s} fwd {r['forward_km']}km rev {r['reverse_km']}km "
              f"all_ways_fwd={r['forward_all_mandatory_ways_traversed']} "
              f"rev={r['reverse_all_mandatory_ways_traversed']} "
              f"free_shortest={r['true_shortest_free_km']}km "
              f"oneway_by_tags={r['oneway_asymmetric_by_TAGS']} "
              f"turn_restr={r['turn_restrictions_touching_corridor']}")
        if r["forward_problems"]:
            print("   fwd problems:", r["forward_problems"][:160])
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
