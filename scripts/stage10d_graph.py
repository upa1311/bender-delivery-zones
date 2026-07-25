#!/usr/bin/env python
"""Stage 10D — correct bidirectional edge snapping + endpoint-aware access.

Fixes the Stage 10C routing core:

  * **Snapping returns ONE physical position and ALL its directed states.** A
    bidirectional segment is seeded toward BOTH ends, each with its own partial
    length ((1-t)·L toward the far end, t·L toward the near end); a oneway keeps
    only the legal direction. Arrival is accepted from every legal direction, and
    source/destination on the SAME segment is handled in both orders. Nothing is
    called UNREACHABLE until every directed representation has been tried.
  * **Nearest-edge search is a real spatial index** (shapely STRtree over
    per-segment geometry with `query_nearest`), not a grid over endpoints that
    stopped at the first radius containing any endpoint.
  * **Endpoint-aware access.** `access=delivery` / `destination` ways are NOT
    global transit. They are kept in the graph, flagged, grouped into connected
    components, and may be used only inside the component that contains the
    route's own source or destination — you can enter a restricted area to serve
    an address there, never cut through it to somewhere else.
  * **Turn restrictions** support multiple `from`/`to` members (no_entry/no_exit)
    and via-WAY restrictions carry ORDERED progress through the via sequence, so
    leaving the sequence early clears the restriction correctly.

Read-only. No OSM edit, no immutable release, no Direct, no price, no zone.
"""

from __future__ import annotations

import hashlib
import heapq
import math
import pickle
import sys
from pathlib import Path

import osmium
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

REPO = Path(__file__).resolve().parents[1]
FULL_PBF = REPO / "data/raw/moldova-latest.osm.pbf"
CACHE_DIR = REPO / "data/interim"
BBOX = (29.15, 46.60, 29.85, 47.02)

GRAPH_SCHEMA_VERSION = "10d.1"
ACCESS_PROFILE_VERSION = "endpoint-aware-delivery.1"
RESTRICTION_PARSER_VERSION = "turn-restrictions-ordered-via.1"

VEHICLE_CLASSES = ("motorcar", "motor_vehicle", "vehicle", "access")
OUR_EXCEPTIONS = {"delivery", "motorcar", "motor_vehicle", "vehicle"}
CAR_HIGHWAYS = {
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
    "residential", "living_street", "service", "road",
    "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
}
PUBLIC_ALLOW = {"yes", "permissive", "designated", "public"}
ENDPOINT_ONLY = {"delivery", "destination", "customers"}   # enter only to serve here
DENY = {"no", "private", "agricultural", "forestry", "military", "emergency"}

BARRIER_ALWAYS_BLOCK = {"bollard", "block", "cycle_barrier", "stile", "kissing_gate",
                        "turnstile", "jersey_barrier", "log", "chain",
                        "motorcycle_barrier", "planter", "wall", "fence", "hedge"}
BARRIER_CONDITIONAL = {"gate", "lift_gate", "swing_gate", "door", "entrance",
                       "height_restrictor", "toll_booth", "border_control"}
NO_TURN = {"no_left_turn", "no_right_turn", "no_straight_on", "no_u_turn",
           "no_entry", "no_exit"}
ONLY_TURN = {"only_left_turn", "only_right_turn", "only_straight_on", "only_u_turn"}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def access_class(tags: dict) -> str:
    """'public' | 'endpoint_only' | 'denied' — most specific key wins."""
    for key in VEHICLE_CLASSES:
        v = tags.get(key)
        if v is None:
            continue
        if v in PUBLIC_ALLOW:
            return "public"
        if v in ENDPOINT_ONLY:
            return "endpoint_only"
        if v in DENY:
            return "denied"
    return "public"


def oneway_flags(tags: dict) -> tuple[bool, bool]:
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
    cls = access_class(tags)
    if b in BARRIER_CONDITIONAL:
        return cls == "denied"
    if b in BARRIER_ALWAYS_BLOCK:
        # blocks unless an EXPLICIT permissive access tag re-opens it: an
        # untagged bollard must still stop a car (access_class defaults to public)
        return not any(tags.get(k) in PUBLIC_ALLOW for k in VEHICLE_CLASSES)
    return cls == "denied"


class _Collector(osmium.SimpleHandler):
    def __init__(self, bbox):
        super().__init__()
        self.bbox = bbox
        self.segs: list[tuple[int, int, float, int, bool, bool, str]] = []
        self.coords: dict[int, tuple[float, float]] = {}
        self.way_tags: dict[int, dict] = {}
        self.barriers: set[int] = set()
        self.denied_ways = 0
        self.restrictions: list[dict] = []

    def node(self, n):
        t = dict(n.tags)
        if t.get("barrier") and barrier_blocks(t):
            self.barriers.add(n.id)

    def way(self, w):
        t = dict(w.tags)
        if t.get("highway") not in CAR_HIGHWAYS:
            return
        cls = access_class(t)
        if cls == "denied":
            self.denied_ways += 1
            return
        lon0, lat0, lon1, lat1 = self.bbox
        try:
            pts = [(n.ref, n.lon, n.lat) for n in w.nodes if n.location.valid()]
        except osmium.InvalidLocationError:
            return
        if len(pts) < 2 or not any(lon0 <= x <= lon1 and lat0 <= y <= lat1 for _, x, y in pts):
            return
        fwd, bwd = oneway_flags(t)
        self.way_tags[w.id] = t
        for (r1, x1, y1), (r2, x2, y2) in zip(pts, pts[1:], strict=False):
            self.coords[r1] = (x1, y1)
            self.coords[r2] = (x2, y2)
            self.segs.append((r1, r2, haversine_m(y1, x1, y2, x2), w.id, fwd, bwd, cls))

    def relation(self, r):
        t = dict(r.tags)
        if t.get("type") != "restriction":
            return
        kind = (t.get("restriction:motorcar") or t.get("restriction:motor_vehicle")
                or t.get("restriction"))
        if not kind:
            return
        if {e.strip() for e in (t.get("except") or "").split(";")} & OUR_EXCEPTIONS:
            return
        self.restrictions.append({
            "kind": kind,
            "from": [m.ref for m in r.members if m.role == "from" and m.type == "w"],
            "to": [m.ref for m in r.members if m.role == "to" and m.type == "w"],
            "via_n": [m.ref for m in r.members if m.role == "via" and m.type == "n"],
            "via_w": [m.ref for m in r.members if m.role == "via" and m.type == "w"],
        })


class Graph:
    def __init__(self, p):
        self.__dict__.update(p)
        self._tree = STRtree([LineString([self.coords[u], self.coords[v]])
                              for (u, v, _l, _w, _c) in self.phys])

    # ---------- build ----------
    @staticmethod
    def cache_path(sha: str) -> Path:
        key = "|".join([sha, str(BBOX), GRAPH_SCHEMA_VERSION,
                        ACCESS_PROFILE_VERSION, RESTRICTION_PARSER_VERSION])
        return CACHE_DIR / f"stage10d-{hashlib.sha256(key.encode()).hexdigest()[:16]}.pkl"

    @classmethod
    def load(cls, pbf: Path = FULL_PBF) -> Graph:
        sha = sha256_file(pbf)
        cache = cls.cache_path(sha)
        if cache.exists():
            with cache.open("rb") as fh:
                return cls(pickle.load(fh))
        p = cls._build(pbf, sha)
        with cache.open("wb") as fh:
            pickle.dump(p, fh, protocol=pickle.HIGHEST_PROTOCOL)
        return cls(p)

    @staticmethod
    def _build(pbf: Path, sha: str) -> dict:
        c = _Collector(BBOX)
        c.apply_file(str(pbf), locations=True)
        phys, edges, phys_dirs = [], [], []
        for u, v, ln, wid, fwd, bwd, cls in c.segs:
            pid = len(phys)
            phys.append((u, v, ln, wid, cls))
            dirs = []
            if fwd:
                dirs.append(len(edges))
                edges.append((u, v, ln, wid, pid))
            if bwd:
                dirs.append(len(edges))
                edges.append((v, u, ln, wid, pid))
            phys_dirs.append(dirs)
        node_out: dict[int, list[int]] = {}
        for i, e in enumerate(edges):
            node_out.setdefault(e[0], []).append(i)

        # endpoint-only components (union-find over restricted segments)
        parent: dict[int, int] = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        node_restricted: dict[int, list[int]] = {}
        for pid, (u, v, _l, _w, cls) in enumerate(phys):
            if cls != "endpoint_only":
                continue
            find(pid)
            for n in (u, v):
                for other in node_restricted.setdefault(n, []):
                    union(pid, other)
                node_restricted[n].append(pid)
        phys_component = {pid: find(pid) for pid, (_u, _v, _l, _w, cls) in enumerate(phys)
                          if cls == "endpoint_only"}

        # restrictions: multiple from/to, ordered via ways
        no_node: dict[tuple[int, int], set[int]] = {}
        only_node: dict[tuple[int, int], set[int]] = {}
        via_way: list[dict] = []
        for r in c.restrictions:
            if not r["from"] or not r["to"]:
                continue
            if r["via_n"] and not r["via_w"]:
                via = r["via_n"][0]
                for f in r["from"]:
                    if r["kind"] in NO_TURN:
                        no_node.setdefault((f, via), set()).update(r["to"])
                    elif r["kind"] in ONLY_TURN:
                        only_node.setdefault((f, via), set()).update(r["to"])
            elif r["via_w"]:
                via_way.append({"kind": r["kind"], "from": set(r["from"]),
                                "to": set(r["to"]), "vias": list(r["via_w"])})
        return {
            "phys": phys, "edges": edges, "phys_dirs": phys_dirs, "node_out": node_out,
            "coords": c.coords, "way_tags": c.way_tags, "barriers": c.barriers,
            "no_node": no_node, "only_node": only_node, "via_way": via_way,
            "phys_component": phys_component,
            "provenance": {
                "pbf_sha256": sha, "bbox": list(BBOX),
                "graph_schema_version": GRAPH_SCHEMA_VERSION,
                "access_profile_version": ACCESS_PROFILE_VERSION,
                "restriction_parser_version": RESTRICTION_PARSER_VERSION,
                "counts": {
                    "physical_segments": len(phys), "directed_edges": len(edges),
                    "nodes": len(node_out), "ways": len(c.way_tags),
                    "barrier_nodes": len(c.barriers), "denied_ways": c.denied_ways,
                    "endpoint_only_segments": len(phys_component),
                    "endpoint_only_components": len(set(phys_component.values())),
                    "restrictions_total": len(c.restrictions),
                    "no_via_node": len(no_node), "only_via_node": len(only_node),
                    "via_way": len(via_way),
                },
            },
        }

    # ---------- snapping ----------
    def snap(self, lon: float, lat: float, k: int = 8):
        """ONE physical position + ALL its legal directed states."""
        pt = Point(lon, lat)
        try:
            idxs = self._tree.query_nearest(pt, max_distance=0.02, all_matches=True)
        except (AttributeError, TypeError):
            idxs = [self._tree.nearest(pt)]
        idxs = list(idxs)[:64] or [self._tree.nearest(pt)]
        best = None
        for pid in idxs:
            u, v, ln, _w, _c = self.phys[pid]
            x1, y1 = self.coords[u]
            x2, y2 = self.coords[v]
            dx, dy = x2 - x1, y2 - y1
            den = dx * dx + dy * dy
            t = 0.0 if den == 0 else max(0.0, min(1.0, ((lon - x1) * dx + (lat - y1) * dy) / den))
            px, py = x1 + t * dx, y1 + t * dy
            off = haversine_m(lat, lon, py, px)
            if best is None or off < best["off_road_m"]:
                best = {"phys": pid, "t": t, "off_road_m": round(off, 2),
                        "proj": (round(px, 7), round(py, 7)), "len_m": ln}
        if best is None:
            return None
        best["states"] = []
        for e in self.phys_dirs[best["phys"]]:
            u_e = self.edges[e][0]
            # cost from the projection to this directed edge's head node
            head_is_v = (u_e == self.phys[best["phys"]][0])
            cost = (1.0 - best["t"]) * best["len_m"] if head_is_v else best["t"] * best["len_m"]
            best["states"].append({"edge": e, "cost_to_head": cost})
        return best

    # ---------- legality ----------
    def _allowed_components(self, *snaps):
        comps = set()
        for s in snaps:
            if s and s["phys"] in self.phys_component:
                comps.add(self.phys_component[s["phys"]])
        return comps

    def _edge_ok(self, e: int, allowed_comps) -> bool:
        pid = self.edges[e][4]
        comp = self.phys_component.get(pid)
        return comp is None or comp in allowed_comps

    def _turn_ok(self, e_in: int, e_out: int) -> bool:
        u_in, v_in, _l, w_in, _p = self.edges[e_in]
        _u2, v_out, _l2, w_out, _p2 = self.edges[e_out]
        if v_in in self.barriers:
            return False
        if w_in == w_out and v_out == u_in:
            return False  # immediate U-turn
        ban = self.no_node.get((w_in, v_in))
        if ban and w_out in ban:
            return False
        only = self.only_node.get((w_in, v_in))
        if only and w_out not in only:
            return False
        return True

    def _via_next(self, state_via, w_in: int, w_out: int):
        """Ordered via-way progress. Returns (new_state_or_None, blocked)."""
        if state_via is not None:
            rid, i = state_via
            r = self.via_way[rid]
            vias = r["vias"]
            if w_out == vias[i]:
                return (rid, i), False
            if i + 1 < len(vias) and w_out == vias[i + 1]:
                return (rid, i + 1), False
            if i == len(vias) - 1 and w_out in r["to"]:
                return None, r["kind"] in NO_TURN
            if r["kind"] in ONLY_TURN:
                return None, True          # left the mandated sequence
            return None, False             # early exit clears a no_* restriction
        for rid, r in enumerate(self.via_way):
            if w_in in r["from"] and w_out == r["vias"][0]:
                return (rid, 0), False
        return None, False

    # ---------- routing ----------
    def dijkstra(self, src_snap, allowed_comps, edge_filter=None):
        dist: dict[tuple, float] = {}
        pq = []
        for st in src_snap["states"]:
            e = st["edge"]
            if edge_filter and e not in edge_filter:
                continue
            if not self._edge_ok(e, allowed_comps):
                continue
            key = (e, None)
            if st["cost_to_head"] < dist.get(key, math.inf):
                dist[key] = st["cost_to_head"]
                heapq.heappush(pq, (st["cost_to_head"], e, None))
        seen = set()
        while pq:
            d, e, via = heapq.heappop(pq)
            if (e, via) in seen:
                continue
            seen.add((e, via))
            _u, v, _l, w_in, _p = self.edges[e]
            for eo in self.node_out.get(v, ()):
                if edge_filter is not None and eo not in edge_filter:
                    continue
                if not self._edge_ok(eo, allowed_comps) or not self._turn_ok(e, eo):
                    continue
                w_out = self.edges[eo][3]
                nvia, blocked = self._via_next(via, w_in, w_out)
                if blocked:
                    continue
                nd = d + self.edges[eo][2]
                key = (eo, nvia)
                if nd < dist.get(key, math.inf):
                    dist[key] = nd
                    heapq.heappush(pq, (nd, eo, nvia))
        return dist

    def best_by_edge(self, dist) -> dict[int, float]:
        out: dict[int, float] = {}
        for (e, _v), d in dist.items():
            if d < out.get(e, math.inf):
                out[e] = d
        return out

    def arrive(self, best, dst_snap) -> float | None:
        """Accept arrival from EVERY legal direction of the destination segment."""
        pid = dst_snap["phys"]
        u, _v, ln, _w, _c = self.phys[pid]
        out = None
        for e in self.phys_dirs[pid]:
            if e not in best:
                continue
            head_is_v = (self.edges[e][0] == u)
            remaining = (1.0 - dst_snap["t"]) * ln if head_is_v else dst_snap["t"] * ln
            val = best[e] - remaining
            if val >= -1e-6 and (out is None or val < out):
                out = max(val, 0.0)
        return out

    def same_segment_distance(self, s, d) -> float | None:
        """src and dst on ONE segment — legal in either order."""
        if s["phys"] != d["phys"]:
            return None
        u, _v, ln, _w, _c = self.phys[s["phys"]]
        best = None
        for e in self.phys_dirs[s["phys"]]:
            forward = (self.edges[e][0] == u)
            if forward and d["t"] >= s["t"]:
                best = min(best or math.inf, (d["t"] - s["t"]) * ln)
            if (not forward) and d["t"] <= s["t"]:
                best = min(best or math.inf, (s["t"] - d["t"]) * ln)
        return best

    def route_km(self, src_lonlat, dst_lonlat):
        s = self.snap(*src_lonlat)
        d = self.snap(*dst_lonlat)
        if not s or not d:
            return None
        comps = self._allowed_components(s, d)
        direct = self.same_segment_distance(s, d)
        best = self.best_by_edge(self.dijkstra(s, comps))
        routed = self.arrive(best, d)
        vals = [x for x in (direct, routed) if x is not None]
        if not vals:
            return None
        return {"distance_km": round(min(vals) / 1000, 4),
                "off_road_src_m": s["off_road_m"], "off_road_dst_m": d["off_road_m"],
                "same_segment": direct is not None}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    g = Graph.load()
    import json
    print(json.dumps(g.provenance["counts"], indent=2))
    r = g.route_km((29.48313, 46.82388), (29.46735, 46.83524))
    print("central -> Кишинёвская 1:", r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
