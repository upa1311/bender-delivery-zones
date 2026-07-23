"""Ordered delivery price bands over route cost (Stage 06).

Zones here are NOT geographic clusters. They are ordered cost bands over the
origin-weighted road kilometres to each delivery unit, so Zone 1 holds the
cheapest routes, Zone 2 the next range, and Zone N the farthest standard-service
range — the way a taxi meter escalates.

The partition is a one-dimensional weighted clustering solved exactly by dynamic
programming over distance bins (minimising within-band weighted squared
deviation). Because bands are intervals on the sorted cost axis, they are
monotonic, mutually exclusive and exhaustive by construction.

No spatial K-means, no network Voronoi, no customer-centred seeds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

INF = float("inf")


@dataclass
class Bin:
    value: float     # representative cost (km) for the bin
    weight: float    # summed demand weight
    count: int       # number of units


def make_bins(values, weights, bin_width: float) -> list[Bin]:
    """Aggregate unit costs into fixed-width bins, sorted ascending."""
    buckets: dict = {}
    for value, weight in zip(values, weights, strict=False):
        if value is None:
            continue
        key = int(math.floor(value / bin_width))
        b = buckets.setdefault(key, [0.0, 0.0, 0])
        b[0] += value * weight
        b[1] += weight
        b[2] += 1
    out = []
    for key in sorted(buckets):
        acc, weight, count = buckets[key]
        centre = (acc / weight) if weight > 0 else (key + 0.5) * bin_width
        out.append(Bin(value=centre, weight=weight, count=count))
    return out


def _prefixes(bins: list[Bin]):
    n = len(bins)
    w = [0.0] * (n + 1)
    wx = [0.0] * (n + 1)
    wxx = [0.0] * (n + 1)
    for i, b in enumerate(bins):
        w[i + 1] = w[i] + b.weight
        wx[i + 1] = wx[i] + b.weight * b.value
        wxx[i + 1] = wxx[i] + b.weight * b.value * b.value
    return w, wx, wxx


def _sse(i: int, j: int, w, wx, wxx) -> float:
    """Weighted squared deviation of bins [i, j)."""
    weight = w[j] - w[i]
    if weight <= 0:
        return 0.0
    mean = (wx[j] - wx[i]) / weight
    return max((wxx[j] - wxx[i]) - 2 * mean * (wx[j] - wx[i]) + mean * mean * weight, 0.0)


def optimal_bands(bins: list[Bin], k: int, min_weight_share: float = 0.05):
    """Exact 1-D weighted DP partition into *k* ordered bands.

    ``min_weight_share`` forbids economically meaningless slivers: every band
    must hold at least that share of total demand weight. Returns a list of
    ``(start, end)`` bin index pairs (end exclusive), ascending by cost.
    """
    n = len(bins)
    if n == 0:
        return []
    k = max(1, min(k, n))
    w, wx, wxx = _prefixes(bins)
    total = w[n]
    floor_weight = total * min_weight_share

    # dp[b][j] = best cost of splitting the first j bins into b bands
    dp = [[INF] * (n + 1) for _ in range(k + 1)]
    back = [[-1] * (n + 1) for _ in range(k + 1)]
    dp[0][0] = 0.0
    for b in range(1, k + 1):
        for j in range(1, n + 1):
            best, best_i = INF, -1
            for i in range(b - 1, j):
                if dp[b - 1][i] == INF:
                    continue
                if (w[j] - w[i]) < floor_weight:
                    continue
                cost = dp[b - 1][i] + _sse(i, j, w, wx, wxx)
                if cost < best:
                    best, best_i = cost, i
            dp[b][j] = best
            back[b][j] = best_i

    if dp[k][n] == INF:               # constraint infeasible -> relax the floor
        if min_weight_share <= 0:
            return [(0, n)]
        return optimal_bands(bins, k, min_weight_share / 2.0)

    bounds, j = [], n
    for b in range(k, 0, -1):
        i = back[b][j]
        bounds.append((i, j))
        j = i
    bounds.reverse()
    return bounds


def band_edges(bins: list[Bin], bounds) -> list[float]:
    """Upper cost edge of each band (last band is unbounded -> its max)."""
    return [bins[end - 1].value for _start, end in bounds]


def assign_band(value: float, upper_edges: list[float]) -> int:
    """Zone index (0-based) for a cost value. Bands are ordered and exclusive."""
    for i, edge in enumerate(upper_edges):
        if value <= edge:
            return i
    return len(upper_edges) - 1


def is_monotonic(band_values: list[list[float]]) -> bool:
    """True when every band's max is <= the next band's min (no overlap)."""
    for a, b in zip(band_values, band_values[1:], strict=False):
        if not a or not b:
            continue
        if max(a) > min(b):
            return False
    return True


def dispersion(values, weights) -> float | None:
    """Weighted standard deviation of route cost inside a band."""
    pairs = [(v, w) for v, w in zip(values, weights, strict=False)
             if v is not None and w > 0]
    if not pairs:
        return None
    total = sum(w for _v, w in pairs)
    mean = sum(v * w for v, w in pairs) / total
    var = sum(w * (v - mean) ** 2 for v, w in pairs) / total
    return math.sqrt(var)
