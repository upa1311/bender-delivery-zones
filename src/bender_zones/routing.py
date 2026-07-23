"""Local road routing over the OSM extract (Stage 05).

Builds an in-memory road graph from locally extracted OSM centrelines and runs
Dijkstra over it to get **actual road travel distance and time** — not
straight-line distance and not polygon area.

This is deliberately a plain in-process graph: no OSRM, no Valhalla, no
GraphHopper, no persisted routing artifact, and no delivery route planning. It
produces measurements (distance/time from an origin to a customer) that the
zoning stage consumes.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

_MAXSPEED_UNITS = {"mph": 1.609344, "km/h": 1.0, "kmh": 1.0}


def parse_maxspeed(raw: str | None) -> float | None:
    """Parse an OSM ``maxspeed`` value into km/h, or ``None`` if unusable."""
    if not raw:
        return None
    text = raw.strip().lower()
    factor = 1.0
    for unit, mult in _MAXSPEED_UNITS.items():
        if text.endswith(unit):
            factor = mult
            text = text[: -len(unit)].strip()
            break
    try:
        value = float(text)
    except ValueError:
        return None
    return value * factor if value > 0 else None


def way_speed_kmh(tags: dict, speeds: dict, default: float) -> float:
    """Speed for a way: its own maxspeed when usable, else the class default."""
    parsed = parse_maxspeed(tags.get("maxspeed"))
    if parsed:
        return parsed
    return float(speeds.get(tags.get("highway"), default))


@dataclass
class RoadGraph:
    """Undirected road graph in the local metric plane."""

    adjacency: dict = field(default_factory=dict)   # node -> [(node, metres, seconds)]
    coords: dict = field(default_factory=dict)      # node -> (x, y)

    @property
    def node_count(self) -> int:
        return len(self.adjacency)

    @property
    def edge_count(self) -> int:
        return sum(len(v) for v in self.adjacency.values()) // 2


def build_graph(ways, speeds: dict, default_speed: float, snap_m: float = 1.0) -> RoadGraph:
    """Build a road graph from ``(coords, tags)`` pairs already in metres."""
    graph = RoadGraph()

    def key(x, y):
        return (round(x / snap_m), round(y / snap_m))

    for coords, tags in ways:
        speed = way_speed_kmh(tags, speeds, default_speed)
        mps = max(speed, 1.0) * 1000.0 / 3600.0
        for (x1, y1), (x2, y2) in zip(coords, coords[1:], strict=False):
            a, b = key(x1, y1), key(x2, y2)
            if a == b:
                continue
            length = math.hypot(x2 - x1, y2 - y1)
            seconds = length / mps
            graph.adjacency.setdefault(a, []).append((b, length, seconds))
            graph.adjacency.setdefault(b, []).append((a, length, seconds))
            graph.coords.setdefault(a, (x1, y1))
            graph.coords.setdefault(b, (x2, y2))
    return graph


def dijkstra(graph: RoadGraph, sources, minimise: str = "time"):
    """Multi-source Dijkstra.

    Returns ``{node: (cost, distance_m, time_s, source)}``. ``minimise`` picks
    which quantity is optimised; the other is carried along the chosen path, so
    the reported distance is the distance of the fastest route (or vice versa).
    """
    best: dict = {}
    heap = []
    for src in sources:
        if src in graph.adjacency:
            best[src] = (0.0, 0.0, 0.0, src)
            heap.append((0.0, src, 0.0, 0.0, src))
    heapq.heapify(heap)

    while heap:
        cost, node, dist, time_s, src = heapq.heappop(heap)
        if cost > best.get(node, (math.inf,))[0]:
            continue
        for nbr, length, seconds in graph.adjacency.get(node, ()):
            step = seconds if minimise == "time" else length
            new_cost = cost + step
            if new_cost < best.get(nbr, (math.inf,))[0]:
                best[nbr] = (new_cost, dist + length, time_s + seconds, src)
                heapq.heappush(heap, (new_cost, nbr, dist + length,
                                      time_s + seconds, src))
    return best


def snap_nodes(points, graph: RoadGraph, radius_m: float):
    """Nearest graph node for each point, or ``None`` when beyond *radius*."""
    from shapely.geometry import Point
    from shapely.strtree import STRtree

    if not graph.coords:
        return [None] * len(points)
    keys = list(graph.coords)
    geoms = [Point(*graph.coords[k]) for k in keys]
    tree = STRtree(geoms)
    out = []
    for p in points:
        idx = tree.nearest(p)
        if idx is None:
            out.append(None)
            continue
        i = int(idx)
        out.append(keys[i] if geoms[i].distance(p) <= radius_m else None)
    return out


def weighted_percentile(values, weights, percentile: float) -> float | None:
    """Weighted percentile (0-100). Returns ``None`` for an empty sample."""
    pairs = [(v, w) for v, w in zip(values, weights, strict=False)
             if v is not None and w > 0]
    if not pairs:
        return None
    pairs.sort(key=lambda vw: vw[0])
    total = sum(w for _v, w in pairs)
    target = total * percentile / 100.0
    seen = 0.0
    for value, weight in pairs:
        seen += weight
        if seen >= target:
            return float(value)
    return float(pairs[-1][0])
