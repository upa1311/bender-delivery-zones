#!/usr/bin/env python
"""Stage 10C — EDGE-VALID routing graph for a DELIVERY vehicle.

Replaces the Stage 10B node-based Dijkstra, which parsed turn restrictions but
never applied them, ignored barrier nodes, wrongly blocked `access=delivery`, and
snapped to the nearest NODE without charging the partial edge length.

What this does instead:

  * **Stateful edge-based Dijkstra.** A state is a *directed edge* (plus an active
    via-way restriction id), so turn restrictions can actually be enforced:
      - `no_*`  (no_left_turn / no_right_turn / no_straight_on / no_u_turn / …)
      - `only_*` (only the named continuation is permitted)
      - `via=node` and `via=way` (multi-way vias supported via an active-restriction
        state component)
      - `restriction:motorcar` / `restriction:motor_vehicle` override plain
        `restriction`; an `except=` list containing our vehicle class exempts us.
  * **Barrier nodes** (gate, bollard, block, lift_gate, chain, …) block passage
    THROUGH the node unless their own access tags permit a motor vehicle.
  * **Delivery access profile.** `access=delivery` / `motor_vehicle=delivery` is
    ALLOWED (a courier van is a delivery vehicle) — the Stage 10B bug. `private`
    and `customers` stay blocked for transit; `destination` is allowed. The most
    specific key wins: motorcar > motor_vehicle > vehicle > access. `*:conditional`
    values are recorded and flagged, never silently applied.
  * **Edge snapping.** A coordinate snaps to the nearest position ON an edge; the
    edge is split by a virtual node, the partial edge length IS charged to the
    route, and the perpendicular off-road distance is reported SEPARATELY.
  * **Cache provenance.** The cache key contains the PBF SHA-256, the bbox, the
    graph schema version, the access-profile version and the restriction-parser
    version; any mismatch forces a rebuild.

Read-only. No OSM edit, no immutable release, no Direct, no price, no zone.
"""

from __future__ import annotations

import hashlib
import heapq
import json
import math
import pickle
import sys
from pathlib import Path

import osmium

REPO = Path(__file__).resolve().parents[1]
FULL_PBF = REPO / "data/raw/moldova-latest.osm.pbf"
CACHE_DIR = REPO / "data/interim"
BBOX = (29.15, 46.60, 29.85, 47.02)

GRAPH_SCHEMA_VERSION = "10c.1"
ACCESS_PROFILE_VERSION = "delivery-vehicle.1"
RESTRICTION_PARSER_VERSION = "turn-restrictions.1"

VEHICLE_CLASSES = ("motorcar", "motor_vehicle", "vehicle", "access")
OUR_VEHICLE_EXCEPTIONS = {"delivery", "motorcar", "motor_vehicle", "vehicle"}

CAR_HIGHWAYS = {
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
    "residential", "living_street", "service", "road",
    "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
}
# A delivery van MAY use these; `delivery` is explicitly allowed (Stage 10B bug).
ACCESS_ALLOW = {"yes", "permissive", "designated", "destination", "delivery", "public"}
ACCESS_DENY = {"no", "private", "customers", "agricultural", "forestry", "military", "emergency"}

# Barriers that stop a motor vehicle unless their own tags say otherwise.
BARRIER_ALWAYS_BLOCK = {
    "bollard", "block", "cycle_barrier", "stile", "kissing_gate", "turnstile",
    "jersey_barrier", "log", "chain", "motorcycle_barrier", "planter", "wall",
    "fence", "hedge", "ditch", "debris",
}
# Barriers that are passable unless access says no.
BARRIER_CONDITIONAL = {"gate", "lift_gate", "swing_gate", "door", "entrance",
                       "height_restrictor", "toll_booth", "border_control", "sally_port"}

NO_TURN = {"no_left_turn", "no_right_turn", "no_straight_on", "no_u_turn",
           "no_entry", "no_exit"}
ONLY_TURN = {"only_left_turn", "only_right_turn", "only_straight_on", "only_u_turn"}


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def access_decision(tags: dict) -> tuple[bool, str, bool]:
    """(allowed, reason, conditional_flag) for a DELIVERY vehicle. Most specific wins."""
    conditional = any(f"{k}:conditional" in tags for k in VEHICLE_CLASSES)
    for key in VEHICLE_CLASSES:
        val = tags.get(key)
        if val is None:
            continue
        if val in ACCESS_ALLOW:
            return True, f"{key}={val}", conditional
        if val in ACCESS_DENY:
            return False, f"{key}={val}", conditional
    return True, "untagged", conditional


def oneway_flags(tags: dict) -> tuple[bool, bool]:
    """(forward, backward) strictly from tags."""
    ow = tags.get("oneway:motorcar") or tags.get("oneway:motor_vehicle") or tags.get("oneway")
    if ow in ("yes", "true", "1"):
        return True, False
    if ow in ("-1", "reverse"):
        return False, True
    if ow in ("no", "false", "0"):
        return True, True
    if tags.get("junction") in ("roundabout", "circular"):
        return True, False
    return True, True


def barrier_blocks(tags: dict) -> bool:
    b = tags.get("barrier")
    if not b:
        return False
    allowed, _reason, _c = access_decision(tags)
    if b in BARRIER_CONDITIONAL:
        return not allowed
    if b in BARRIER_ALWAYS_BLOCK:
        # an explicit permissive access tag re-opens it
        for key in VEHICLE_CLASSES:
            if tags.get(key) in ACCESS_ALLOW:
                return False
        return True
    return not allowed


class _Collector(osmium.SimpleHandler):
    def __init__(self, bbox):
        super().__init__()
        self.bbox = bbox
        self.segments: list[tuple[int, int, float, int, bool, bool]] = []
        self.coords: dict[int, tuple[float, float]] = {}
        self.way_tags: dict[int, dict] = {}
        self.barrier_nodes: set[int] = set()
        self.conditional_ways: list[int] = []
        self.blocked_ways = 0
        self.restrictions: list[dict] = []

    def node(self, n):
        tags = dict(n.tags)
        if tags.get("barrier") and barrier_blocks(tags):
            self.barrier_nodes.add(n.id)

    def way(self, w):
        tags = dict(w.tags)
        if tags.get("highway") not in CAR_HIGHWAYS:
            return
        allowed, _reason, conditional = access_decision(tags)
        if not allowed:
            self.blocked_ways += 1
            return
        lon0, lat0, lon1, lat1 = self.bbox
        try:
            pts = [(n.ref, n.lon, n.lat) for n in w.nodes if n.location.valid()]
        except osmium.InvalidLocationError:
            return
        if len(pts) < 2 or not any(lon0 <= x <= lon1 and lat0 <= y <= lat1 for _, x, y in pts):
            return
        if conditional:
            self.conditional_ways.append(w.id)
        fwd, bwd = oneway_flags(tags)
        self.way_tags[w.id] = tags
        for (r1, x1, y1), (r2, x2, y2) in zip(pts, pts[1:], strict=False):
            self.coords[r1] = (x1, y1)
            self.coords[r2] = (x2, y2)
            self.segments.append((r1, r2, haversine_m(y1, x1, y2, x2), w.id, fwd, bwd))

    def relation(self, r):
        tags = dict(r.tags)
        if tags.get("type") != "restriction":
            return
        kind = (tags.get("restriction:motorcar") or tags.get("restriction:motor_vehicle")
                or tags.get("restriction"))
        if not kind:
            return
        exceptions = {e.strip() for e in (tags.get("except") or "").split(";") if e.strip()}
        if exceptions & OUR_VEHICLE_EXCEPTIONS:
            return  # our delivery vehicle is exempt from this restriction
        self.restrictions.append({
            "id": r.id, "kind": kind,
            "from_ways": [m.ref for m in r.members if m.role == "from" and m.type == "w"],
            "to_ways": [m.ref for m in r.members if m.role == "to" and m.type == "w"],
            "via_nodes": [m.ref for m in r.members if m.role == "via" and m.type == "n"],
            "via_ways": [m.ref for m in r.members if m.role == "via" and m.type == "w"],
        })


class EdgeGraph:
    """Directed-edge graph with enforced turn restrictions and barriers."""

    def __init__(self, payload):
        self.__dict__.update(payload)
        self._grid: dict[tuple[int, int], list[int]] = {}
        for i, (u, v, *_rest) in enumerate(self.edges):
            lon, lat = self.coords[u]
            self._grid.setdefault((int(lon * 200), int(lat * 200)), []).append(i)
            lon2, lat2 = self.coords[v]
            key2 = (int(lon2 * 200), int(lat2 * 200))
            if key2 != (int(lon * 200), int(lat * 200)):
                self._grid.setdefault(key2, []).append(i)

    # --- build / cache --------------------------------------------------
    @staticmethod
    def cache_path(pbf_sha: str) -> Path:
        key = "|".join([pbf_sha, str(BBOX), GRAPH_SCHEMA_VERSION,
                        ACCESS_PROFILE_VERSION, RESTRICTION_PARSER_VERSION])
        return CACHE_DIR / f"stage10c-graph-{hashlib.sha256(key.encode()).hexdigest()[:16]}.pkl"

    @classmethod
    def load(cls, pbf: Path = FULL_PBF, bbox=BBOX) -> EdgeGraph:
        pbf_sha = sha256_file(pbf)
        cache = cls.cache_path(pbf_sha)
        if cache.exists():
            with cache.open("rb") as fh:
                payload = pickle.load(fh)
            if payload.get("provenance", {}).get("pbf_sha256") == pbf_sha:
                return cls(payload)
        payload = cls._build(pbf, bbox, pbf_sha)
        cache.parent.mkdir(parents=True, exist_ok=True)
        with cache.open("wb") as fh:
            pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
        return cls(payload)

    @staticmethod
    def _build(pbf: Path, bbox, pbf_sha: str) -> dict:
        c = _Collector(bbox)
        c.apply_file(str(pbf), locations=True)

        edges: list[tuple[int, int, float, int]] = []
        for a, b, m, wid, fwd, bwd in c.segments:
            if fwd:
                edges.append((a, b, m, wid))
            if bwd:
                edges.append((b, a, m, wid))
        node_out: dict[int, list[int]] = {}
        for i, (u, _v, _m, _w) in enumerate(edges):
            node_out.setdefault(u, []).append(i)

        # restriction lookups
        no_node: dict[tuple[int, int], set[int]] = {}
        only_node: dict[tuple[int, int], int] = {}
        via_way_restr: list[dict] = []
        for r in c.restrictions:
            if not r["from_ways"] or not r["to_ways"]:
                continue
            frm, to = r["from_ways"][0], r["to_ways"][0]
            if r["via_nodes"]:
                via = r["via_nodes"][0]
                if r["kind"] in NO_TURN:
                    no_node.setdefault((frm, via), set()).add(to)
                elif r["kind"] in ONLY_TURN:
                    only_node[(frm, via)] = to
            elif r["via_ways"]:
                via_way_restr.append({"id": r["id"], "kind": r["kind"], "from": frm,
                                      "to": to, "vias": list(r["via_ways"])})
        return {
            "edges": edges, "node_out": node_out, "coords": c.coords,
            "way_tags": c.way_tags, "barrier_nodes": c.barrier_nodes,
            "no_node": no_node, "only_node": only_node, "via_way_restr": via_way_restr,
            "conditional_ways": c.conditional_ways,
            "provenance": {
                "pbf_path": str(pbf.relative_to(REPO)), "pbf_sha256": pbf_sha,
                "bbox": list(bbox), "graph_schema_version": GRAPH_SCHEMA_VERSION,
                "access_profile_version": ACCESS_PROFILE_VERSION,
                "restriction_parser_version": RESTRICTION_PARSER_VERSION,
                "vehicle": "delivery van (access=delivery ALLOWED)",
                "counts": {
                    "directed_edges": len(edges), "nodes": len(node_out),
                    "ways": len(c.way_tags), "barrier_nodes_blocking": len(c.barrier_nodes),
                    "access_blocked_ways": c.blocked_ways,
                    "conditional_access_ways": len(c.conditional_ways),
                    "turn_restrictions_parsed": len(c.restrictions),
                    "restrictions_via_node_no": len(no_node),
                    "restrictions_via_node_only": len(only_node),
                    "restrictions_via_way": len(via_way_restr),
                },
            },
        }

    # --- turn legality ---------------------------------------------------
    def _turn_allowed(self, e_in: int, e_out: int) -> bool:
        u_in, v_in, _m, w_in = self.edges[e_in]
        v_out_from, v_out_to, _m2, w_out = self.edges[e_out]
        via = v_in
        if via in self.barrier_nodes:
            return False
        if w_in == w_out and v_out_to == u_in:
            return False  # immediate U-turn on the same way
        banned = self.no_node.get((w_in, via))
        if banned and w_out in banned:
            return False
        only = self.only_node.get((w_in, via))
        if only is not None and w_out != only:
            return False
        return True

    # --- snapping --------------------------------------------------------
    def snap_edge(self, lon: float, lat: float):
        """Project onto the nearest routable EDGE. Returns edge id, fraction t,
        off-road metres and the projected coordinate."""
        best = None
        for radius in (1, 2, 4, 8, 16, 40):
            gx, gy = int(lon * 200), int(lat * 200)
            cand: list[int] = []
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    cand.extend(self._grid.get((gx + dx, gy + dy), ()))
            for ei in set(cand):
                u, v, m, _w = self.edges[ei]
                x1, y1 = self.coords[u]
                x2, y2 = self.coords[v]
                dx_, dy_ = x2 - x1, y2 - y1
                denom = dx_ * dx_ + dy_ * dy_
                t = 0.0 if denom == 0 else max(0.0, min(1.0, ((lon - x1) * dx_ + (lat - y1) * dy_) / denom))  # noqa: E501
                px, py = x1 + t * dx_, y1 + t * dy_
                off = haversine_m(lat, lon, py, px)
                if best is None or off < best["off_road_m"]:
                    best = {"edge": ei, "t": t, "off_road_m": round(off, 2),
                            "proj_lon": round(px, 7), "proj_lat": round(py, 7),
                            "edge_len_m": m}
            if best is not None:
                break
        return best

    # --- routing ---------------------------------------------------------
    def dijkstra_from_snap(self, snap):
        """Edge-state Dijkstra seeded from a snapped position on an edge.
        State = (edge_id, active_via_restriction_id). Returns dist over states."""
        start_cost = (1.0 - snap["t"]) * snap["edge_len_m"]
        dist: dict[tuple[int, int], float] = {(snap["edge"], 0): start_cost}
        prev: dict[tuple[int, int], tuple[int, int] | None] = {(snap["edge"], 0): None}
        pq = [(start_cost, snap["edge"], 0)]
        seen: set[tuple[int, int]] = set()
        while pq:
            d, ei, act = heapq.heappop(pq)
            st = (ei, act)
            if st in seen:
                continue
            seen.add(st)
            _u, v, _m, w_in = self.edges[ei]
            for eo in self.node_out.get(v, ()):
                if not self._turn_allowed(ei, eo):
                    continue
                w_out = self.edges[eo][3]
                nact = act
                if act:
                    r = self.via_way_restr[act - 1]
                    if w_out == r["to"] and r["kind"] in NO_TURN:
                        continue
                    if r["kind"] in ONLY_TURN and w_out != r["to"] and w_out not in r["vias"]:
                        continue
                    nact = act if w_out in r["vias"] else 0
                else:
                    for idx, r in enumerate(self.via_way_restr, start=1):
                        if r["from"] == w_in and w_out in r["vias"]:
                            nact = idx
                            break
                nd = d + self.edges[eo][2]
                nst = (eo, nact)
                if nd < dist.get(nst, math.inf):
                    dist[nst] = nd
                    prev[nst] = st
                    heapq.heappush(pq, (nd, eo, nact))
        return dist, prev

    def distance_to(self, dist, snap_dst) -> float | None:
        """Metres from the seeded source to a snapped destination position."""
        ei = snap_dst["edge"]
        best = None
        for (e, _a), d in dist.items():
            if e != ei:
                continue
            val = d - (1.0 - snap_dst["t"]) * snap_dst["edge_len_m"]
            if val >= -1e-6 and (best is None or val < best):
                best = max(val, 0.0)
        return best

    def route(self, src_lonlat, dst_lonlat):
        s = self.snap_edge(*src_lonlat)
        t = self.snap_edge(*dst_lonlat)
        if not s or not t:
            return None
        dist, prev = self.dijkstra_from_snap(s)
        km = self.distance_to(dist, t)
        if km is None:
            return None
        # reconstruct traversed ways/nodes for the best terminating state
        best_state, best_val = None, math.inf
        for (e, a), d in dist.items():
            if e != t["edge"]:
                continue
            val = d - (1.0 - t["t"]) * t["edge_len_m"]
            if -1e-6 <= val < best_val:
                best_state, best_val = (e, a), val
        ways, nodes = [], []
        st = best_state
        while st is not None:
            e = st[0]
            u, v, _m, w = self.edges[e]
            if not ways or ways[-1] != w:
                ways.append(w)
            nodes.append(v)
            st = prev.get(st)
        ways.reverse()
        nodes.reverse()
        geom = [[self.coords[n][0], self.coords[n][1]] for n in nodes]
        return {
            "distance_km": round(max(best_val, 0.0) / 1000, 4),
            "off_road_src_m": s["off_road_m"], "off_road_dst_m": t["off_road_m"],
            "way_ids": ways, "nodes": nodes, "geometry": geom,
        }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    g = EdgeGraph.load()
    p = g.provenance
    print(json.dumps(p["counts"], indent=2))
    print("cache:", EdgeGraph.cache_path(p["pbf_sha256"]).name)
    r = g.route((29.48313, 46.82388), (29.46735, 46.83524))
    print(f"EDGE-VALID shortest central->Кишинёвская 1: {r['distance_km']} km "
          f"(off-road src {r['off_road_src_m']} m, dst {r['off_road_dst_m']} m, "
          f"{len(r['way_ids'])} ways)")
    names = []
    for w in r["way_ids"]:
        nm = g.way_tags.get(w, {}).get("name")
        if nm and (not names or names[-1] != nm):
            names.append(nm)
    print("streets:", " -> ".join(names[:14]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
