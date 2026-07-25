#!/usr/bin/env python
"""Stage 10B — independent car routing graph + TRUE distance-optimized shortest paths.

Stage 10 called `min(fastest, alternatives=3)` the "shortest route". That is not a
shortest path — OSRM's alternatives are heuristic detours around the fastest
route. This module builds an INDEPENDENT car graph straight from the OSM PBF and
runs a real Dijkstra minimising METRES, so "shortest" is mathematically the global
distance-optimal path over the same road network OSRM uses.

Directionality and access come from the actual OSM TAGS (oneway / oneway:motor
vehicle / junction=roundabout / access / motor_vehicle / vehicle), never inferred
from a distance difference. Every returned path carries the exact sequence of
traversed OSM way IDs, so a corridor can be *verified*, not assumed.

The graph is clipped to a bbox around Bender for tractability; `boundary_margin_km`
reports how close any computed route came to that clip, so a route that could have
been affected by the clip is detectable (and none may be silently truncated).

Read-only. No OSM edit, no immutable release, no Direct, no price, no zone.
"""

from __future__ import annotations

import heapq
import math
import pickle
import sys
from pathlib import Path

import osmium

REPO = Path(__file__).resolve().parents[1]
FULL_PBF = REPO / "data/raw/moldova-latest.osm.pbf"
CACHE = REPO / "data/interim/stage10b-cargraph.pkl"

# Generous clip around Bender + Parkany/Giska/Protyagailovka (~55 x 45 km).
BBOX = (29.15, 46.60, 29.85, 47.02)  # lon_min, lat_min, lon_max, lat_max

CAR_HIGHWAYS = {
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
    "residential", "living_street", "service", "road",
    "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
}
BLOCKED_ACCESS = {"no", "private", "customers", "delivery", "agricultural", "forestry"}
ALLOWED_OVERRIDE = {"yes", "permissive", "designated", "destination"}


def car_allowed(tags: dict) -> bool:
    """Car access strictly from OSM tags (most specific key wins)."""
    for key in ("motor_vehicle", "vehicle", "access"):
        val = tags.get(key)
        if val is None:
            continue
        if val in ALLOWED_OVERRIDE:
            return True
        if val in BLOCKED_ACCESS:
            return False
    return True


def oneway_flags(tags: dict) -> tuple[bool, bool]:
    """(forward_allowed, backward_allowed) from OSM tags only."""
    ow = tags.get("oneway:motor_vehicle") or tags.get("oneway")
    if ow in ("yes", "true", "1"):
        return True, False
    if ow in ("-1", "reverse"):
        return False, True
    if ow in ("no", "false", "0"):
        return True, True
    if tags.get("junction") in ("roundabout", "circular"):
        return True, False
    return True, True


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class _Collector(osmium.SimpleHandler):
    def __init__(self, bbox):
        super().__init__()
        self.bbox = bbox
        self.edges: list[tuple[int, int, float, int, bool, bool]] = []
        self.coords: dict[int, tuple[float, float]] = {}
        self.way_tags: dict[int, dict] = {}
        self.restrictions = 0

    def way(self, w) -> None:
        tags = dict(w.tags)
        if tags.get("highway") not in CAR_HIGHWAYS:
            return
        if not car_allowed(tags):
            return
        lon0, lat0, lon1, lat1 = self.bbox
        try:
            pts = [(n.ref, n.lon, n.lat) for n in w.nodes if n.location.valid()]
        except osmium.InvalidLocationError:
            return
        if len(pts) < 2:
            return
        if not any(lon0 <= lon <= lon1 and lat0 <= lat <= lat1 for _, lon, lat in pts):
            return
        fwd, bwd = oneway_flags(tags)
        self.way_tags[w.id] = tags
        for (r1, x1, y1), (r2, x2, y2) in zip(pts, pts[1:], strict=False):
            self.coords[r1] = (x1, y1)
            self.coords[r2] = (x2, y2)
            self.edges.append((r1, r2, haversine_m(y1, x1, y2, x2), w.id, fwd, bwd))

    def relation(self, r) -> None:
        if dict(r.tags).get("type") == "restriction":
            self.restrictions += 1


class CarGraph:
    """Adjacency over OSM node ids, distance-weighted, way-id tagged."""

    def __init__(self, coords, adj, way_tags, bbox, restrictions):
        self.coords = coords              # node_id -> (lon, lat)
        self.adj = adj                    # node_id -> [(nbr, metres, way_id)]
        self.way_tags = way_tags          # way_id -> tags
        self.bbox = bbox
        self.restrictions = restrictions
        self._grid: dict[tuple[int, int], list[int]] = {}
        for nid, (lon, lat) in coords.items():
            self._grid.setdefault((int(lon * 200), int(lat * 200)), []).append(nid)

    # --- construction ---------------------------------------------------
    @classmethod
    def build(cls, pbf: Path = FULL_PBF, bbox=BBOX) -> CarGraph:
        c = _Collector(bbox)
        c.apply_file(str(pbf), locations=True)
        adj: dict[int, list[tuple[int, float, int]]] = {}
        for a, b, m, wid, fwd, bwd in c.edges:
            if fwd:
                adj.setdefault(a, []).append((b, m, wid))
            if bwd:
                adj.setdefault(b, []).append((a, m, wid))
            adj.setdefault(a, adj.get(a, []))
            adj.setdefault(b, adj.get(b, []))
        return cls(c.coords, adj, c.way_tags, bbox, c.restrictions)

    @classmethod
    def load(cls, pbf: Path = FULL_PBF, bbox=BBOX, cache: Path = CACHE) -> CarGraph:
        if cache.exists():
            with cache.open("rb") as fh:
                d = pickle.load(fh)
            if d.get("bbox") == list(bbox):
                return cls(d["coords"], d["adj"], d["way_tags"], bbox, d["restrictions"])
        g = cls.build(pbf, bbox)
        cache.parent.mkdir(parents=True, exist_ok=True)
        with cache.open("wb") as fh:
            pickle.dump({"coords": g.coords, "adj": g.adj, "way_tags": g.way_tags,
                         "bbox": list(bbox), "restrictions": g.restrictions}, fh,
                        protocol=pickle.HIGHEST_PROTOCOL)
        return g

    # --- queries --------------------------------------------------------
    def snap(self, lon: float, lat: float) -> tuple[int, float]:
        """Nearest routable graph node + snap distance in metres."""
        best, best_m = None, float("inf")
        for radius in (1, 2, 4, 8, 16, 40):
            gx, gy = int(lon * 200), int(lat * 200)
            cand: list[int] = []
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    cand.extend(self._grid.get((gx + dx, gy + dy), ()))
            for nid in cand:
                if not self.adj.get(nid):
                    continue
                nlon, nlat = self.coords[nid]
                m = haversine_m(lat, lon, nlat, nlon)
                if m < best_m:
                    best, best_m = nid, m
            if best is not None:
                break
        return best, round(best_m, 1)

    def dijkstra(self, source: int, targets: set[int] | None = None):
        """Distance-optimal (metres) Dijkstra. Returns (dist, prev_node, prev_way)."""
        dist = {source: 0.0}
        prev_node: dict[int, int] = {}
        prev_way: dict[int, int] = {}
        seen: set[int] = set()
        remaining = set(targets) if targets else None
        pq = [(0.0, source)]
        while pq:
            d, u = heapq.heappop(pq)
            if u in seen:
                continue
            seen.add(u)
            if remaining is not None:
                remaining.discard(u)
                if not remaining:
                    break
            for v, m, wid in self.adj.get(u, ()):
                nd = d + m
                if nd < dist.get(v, float("inf")):
                    dist[v] = nd
                    prev_node[v] = u
                    prev_way[v] = wid
                    heapq.heappush(pq, (nd, v))
        return dist, prev_node, prev_way

    def path(self, source: int, target: int, prev_node, prev_way):
        """Reconstruct (nodes, ordered unique way ids, [lon,lat] geometry)."""
        if target != source and target not in prev_node:
            return None
        nodes, ways = [target], []
        cur = target
        while cur != source:
            ways.append(prev_way[cur])
            cur = prev_node[cur]
            nodes.append(cur)
        nodes.reverse()
        ways.reverse()
        ordered: list[int] = []
        for w in ways:
            if not ordered or ordered[-1] != w:
                ordered.append(w)
        geom = [[self.coords[n][0], self.coords[n][1]] for n in nodes]
        return {"nodes": nodes, "way_ids": ordered, "geometry": geom}

    def shortest(self, src_lonlat, dst_lonlat):
        """TRUE global distance-optimal path between two coordinates."""
        s, s_m = self.snap(*src_lonlat)
        t, t_m = self.snap(*dst_lonlat)
        if s is None or t is None:
            return None
        dist, pn, pw = self.dijkstra(s, targets={t})
        if t not in dist:
            return None
        p = self.path(s, t, pn, pw)
        p.update({"distance_km": round(dist[t] / 1000, 4),
                  "snap_src_m": s_m, "snap_dst_m": t_m,
                  "boundary_margin_km": self.boundary_margin_km(p["geometry"])})
        return p

    def boundary_margin_km(self, geometry) -> float:
        """Smallest distance from the route to the bbox clip (clip-safety check)."""
        lon0, lat0, lon1, lat1 = self.bbox
        best = float("inf")
        for lon, lat in geometry:
            best = min(best, (lon - lon0) * 76, (lon1 - lon) * 76,
                       (lat - lat0) * 111, (lat1 - lat) * 111)
        return round(best, 2)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    g = CarGraph.load()
    print(f"nodes={len(g.adj)} coords={len(g.coords)} ways={len(g.way_tags)} "
          f"turn_restriction_relations={g.restrictions}")
    central = (29.48313, 46.82388)
    kish1 = (29.46735, 46.83524)
    p = g.shortest(central, kish1)
    print(f"TRUE shortest central->Кишинёвская 1: {p['distance_km']} km, "
          f"{len(p['way_ids'])} ways, snap {p['snap_src_m']}/{p['snap_dst_m']} m, "
          f"bbox margin {p['boundary_margin_km']} km")
    names = []
    for w in p["way_ids"]:
        nm = g.way_tags.get(w, {}).get("name")
        if nm and (not names or names[-1] != nm):
            names.append(nm)
    print("streets:", " -> ".join(names[:12]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
