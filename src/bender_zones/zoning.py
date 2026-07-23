"""Routing-based candidate delivery zones (Stage 05).

Zones are grown on the road graph: every customer is assigned to the seed it can
be reached from fastest by ACTUAL road travel time (a network Voronoi
partition), then seeds are refined Lloyd-style. Because assignment follows the
road network, each zone is connected over the graph by construction.

Nothing here prices anything. K=4 and K=5 are both produced and neither is
chosen — that needs local routing results plus real taxi tariffs from the owner.
"""

from __future__ import annotations

import math

from .routing import RoadGraph, dijkstra


def polsby_popper(polygon) -> float | None:
    """Compactness in [0, 1]: 1.0 is a perfect circle."""
    if polygon is None or polygon.is_empty or polygon.length <= 0:
        return None
    return round(4.0 * math.pi * polygon.area / (polygon.length ** 2), 4)


def initial_seeds(customer_nodes, weights, k, coords):
    """Deterministic farthest-point init, starting from the heaviest customer."""
    unique = []
    seen = set()
    for node, _w in sorted(zip(customer_nodes, weights, strict=False),
                           key=lambda nw: (-nw[1], nw[0])):
        if node not in seen:
            seen.add(node)
            unique.append(node)
    if len(unique) <= k:
        return unique
    seeds = [unique[0]]
    while len(seeds) < k:
        best_node, best_d = None, -1.0
        for node in unique:
            if node in seeds:
                continue
            x, y = coords[node]
            dmin = min((x - coords[s][0]) ** 2 + (y - coords[s][1]) ** 2 for s in seeds)
            if dmin > best_d:
                best_d, best_node = dmin, node
        seeds.append(best_node)
    return seeds


def assign_by_travel_time(graph: RoadGraph, seeds, customer_nodes):
    """Network Voronoi: nearest seed by road travel time, per customer node."""
    result = {}
    per_seed = []
    for seed in seeds:
        per_seed.append(dijkstra(graph, [seed], minimise="time"))
    for node in set(customer_nodes):
        best_i, best_t, second_t = None, math.inf, math.inf
        for i, table in enumerate(per_seed):
            entry = table.get(node)
            if entry is None:
                continue
            t = entry[2]
            if t < best_t:
                second_t = best_t
                best_i, best_t = i, t
            elif t < second_t:
                second_t = t
        result[node] = (best_i, best_t, second_t)
    return result


def refine_seeds(assignment, customer_nodes, weights, coords, seeds):
    """Move each seed to the customer node nearest its weighted centroid."""
    groups: dict = {}
    for node, w in zip(customer_nodes, weights, strict=False):
        zone = assignment.get(node, (None,))[0]
        if zone is None:
            continue
        groups.setdefault(zone, []).append((node, w))
    new_seeds = list(seeds)
    for zone, members in groups.items():
        total = sum(w for _n, w in members) or 1.0
        cx = sum(coords[n][0] * w for n, w in members) / total
        cy = sum(coords[n][1] * w for n, w in members) / total
        best, best_d = None, math.inf
        for node, _w in members:
            x, y = coords[node]
            d = (x - cx) ** 2 + (y - cy) ** 2
            if d < best_d:
                best_d, best = d, node
        if best is not None:
            new_seeds[zone] = best
    return new_seeds


def build_zones(graph: RoadGraph, customer_nodes, weights, k, iterations=8):
    """Grow K zones over the road graph. Returns ``(assignment, seeds)``."""
    coords = graph.coords
    routable = [n for n in customer_nodes if n in graph.adjacency]
    routable_w = [w for n, w in zip(customer_nodes, weights, strict=False)
                  if n in graph.adjacency]
    if not routable:
        return {}, []
    seeds = initial_seeds(routable, routable_w, k, coords)
    assignment = {}
    for _ in range(max(1, iterations)):
        assignment = assign_by_travel_time(graph, seeds, routable)
        new_seeds = refine_seeds(assignment, routable, routable_w, coords, seeds)
        if new_seeds == seeds:
            break
        seeds = new_seeds
    assignment = assign_by_travel_time(graph, seeds, routable)
    return assignment, seeds


def assign_all_nodes(graph: RoadGraph, seeds):
    """Assign EVERY reachable graph node to its fastest seed (network Voronoi)."""
    tables = [dijkstra(graph, [s], minimise="time") for s in seeds]
    out = {}
    for node in graph.adjacency:
        best_i, best_t = None, math.inf
        for i, table in enumerate(tables):
            entry = table.get(node)
            if entry is not None and entry[2] < best_t:
                best_i, best_t = i, entry[2]
        if best_i is not None:
            out[node] = best_i
    return out


def zone_graph_components(graph: RoadGraph, nodes) -> int:
    """Number of connected components a zone forms on the road graph.

    This is the connectivity that matters for delivery: can a driver stay inside
    the zone on real roads? Polygon fragments are only a drawing artifact.
    """
    nodeset = set(nodes)
    seen, components = set(), 0
    for start in nodeset:
        if start in seen:
            continue
        components += 1
        stack = [start]
        seen.add(start)
        while stack:
            cur = stack.pop()
            for nbr, _length, _seconds in graph.adjacency.get(cur, ()):
                if nbr in nodeset and nbr not in seen:
                    seen.add(nbr)
                    stack.append(nbr)
    return components


def is_uncertain(best_time: float, second_time: float, margin_pct: float) -> bool:
    """A customer is uncertain when the runner-up zone is nearly as fast."""
    if best_time is None or second_time is None or math.isinf(second_time):
        return False
    if best_time <= 0:
        return False
    return (second_time - best_time) / best_time * 100.0 < margin_pct
