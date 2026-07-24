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


def street_split_counts(street_bins: dict[object, list[int]], n_bins: int) -> list[float]:
    """How many streets a cut placed *before* bin ``p`` would split (unweighted)."""
    counts = [0.0] * (n_bins + 1)
    for indices in street_bins.values():
        if not indices:
            continue
        lo, hi = min(indices), max(indices)
        for p in range(lo + 1, hi + 1):
            counts[p] += 1.0
    return counts


def street_split_demand(street_units: dict[object, list[tuple[int, float]]],
                        n_bins: int) -> list[float]:
    """Confirmed-address demand a cut before bin ``p`` would separate.

    ``street_units`` maps a street to ``(bin_index, address_weight)`` pairs. The
    cost of a cut is the demand actually torn apart -- the smaller side of the
    street at that cut -- so splitting a street with 200 addresses costs far more
    than splitting one with 2 uncertain units, and a cut at the very end of a
    street (separating nobody) costs almost nothing.
    """
    cost = [0.0] * (n_bins + 1)
    for units in street_units.values():
        if not units:
            continue
        total = sum(w for _b, w in units)
        if total <= 0:
            continue
        lo = min(b for b, _w in units)
        hi = max(b for b, _w in units)
        for p in range(lo + 1, hi + 1):
            below = sum(w for b, w in units if b < p)
            cost[p] += min(below, total - below)
    return cost


def optimal_bands(bins: list[Bin], k: int, min_weight_share: float = 0.05,
                  split_at: list[float] | None = None,
                  split_penalty: float = 0.0):
    """Exact 1-D weighted DP partition into *k* ordered bands.

    Objective = within-band weighted squared deviation **plus**
    ``split_penalty`` for every street the cut runs through. A boundary that
    slices many addresses on one street therefore costs more than a boundary
    that falls between streets, while the bands stay ordered intervals on the
    cost axis — so monotonic kilometre ranges are preserved by construction.

    ``min_weight_share`` forbids economically meaningless slivers. Returns a
    list of ``(start, end)`` bin index pairs (end exclusive), ascending by cost.
    """
    n = len(bins)
    if n == 0:
        return []
    k = max(1, min(k, n))
    w, wx, wxx = _prefixes(bins)
    total = w[n]
    floor_weight = total * min_weight_share

    def cut_cost(i: int) -> float:
        """Penalty for an internal cut before bin *i* (0 and n are the ends)."""
        if split_penalty <= 0 or not split_at or i <= 0 or i >= n:
            return 0.0
        return split_penalty * split_at[i]

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
                cost = dp[b - 1][i] + _sse(i, j, w, wx, wxx) + cut_cost(i)
                if cost < best:
                    best, best_i = cost, i
            dp[b][j] = best
            back[b][j] = best_i

    if dp[k][n] == INF:               # constraint infeasible -> relax the floor
        if min_weight_share <= 0:
            return [(0, n)]
        return optimal_bands(bins, k, min_weight_share / 2.0,
                             split_at=split_at, split_penalty=split_penalty)

    bounds, j = [], n
    for b in range(k, 0, -1):
        i = back[b][j]
        bounds.append((i, j))
        j = i
    bounds.reverse()
    return bounds


def housenumber_sort_key(value: str):
    """Natural sort for house numbers: 2 < 2A < 10 < 10/1."""
    text = (value or "").strip()
    digits = ""
    for ch in text:
        if ch.isdigit():
            digits += ch
        elif digits:
            break
    return (int(digits) if digits else 10**9, text)


def housenumber_ranges(values) -> str:
    """Compact contiguous house-number ranges, e.g. ``1-15, 19, 21-25``."""
    uniq = sorted({(v or "").strip() for v in values if (v or "").strip()},
                  key=housenumber_sort_key)
    if not uniq:
        return ""
    out, run = [], [uniq[0]]

    def numeric(v):
        key = housenumber_sort_key(v)
        return key[0] if key[0] < 10**9 and v.strip().isdigit() else None

    for value in uniq[1:]:
        a, b = numeric(run[-1]), numeric(value)
        if a is not None and b is not None and b - a in (1, 2):
            run.append(value)
        else:
            out.append(run)
            run = [value]
    out.append(run)
    return ", ".join(r[0] if len(r) == 1 else f"{r[0]}-{r[-1]}" for r in out)


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
