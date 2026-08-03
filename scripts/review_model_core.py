"""Pure geometry and classification helpers for the static review model."""

from __future__ import annotations

import math
from collections import Counter


def base_price(route_km: float) -> float:
    return 14.0 if route_km <= 3.0 else 14.0 + (route_km - 3.0) * 4.0


def external_surcharge(external_km: float) -> float:
    return 0.0 if external_km <= 0 else max(5.0, external_km * 2.0)


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distance between lon/lat pairs."""
    radius_km = 6371.0088
    dlat = math.radians(b[1] - a[1])
    dlon = math.radians(b[0] - a[0])
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(a[1]))
        * math.cos(math.radians(b[1]))
        * math.sin(dlon / 2) ** 2
    )
    return 2 * radius_km * math.asin(math.sqrt(h))


def decode_polyline6(encoded: str) -> list[tuple[float, float]]:
    """Decode an OSRM polyline6 into lon/lat pairs."""
    coordinates: list[tuple[float, float]] = []
    lat = lon = index = 0
    while index < len(encoded):
        deltas = []
        for _axis in range(2):
            result = shift = 0
            while True:
                value = ord(encoded[index]) - 63
                index += 1
                result |= (value & 0x1F) << shift
                shift += 5
                if value < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        coordinates.append((lon / 1_000_000, lat / 1_000_000))
    return coordinates


def _cross(a: tuple[float, float], b: tuple[float, float]) -> float:
    return a[0] * b[1] - a[1] * b[0]


def segment_intersection_fraction(
    route_a: tuple[float, float],
    route_b: tuple[float, float],
    gate_a: tuple[float, float],
    gate_b: tuple[float, float],
    *,
    epsilon: float = 1e-12,
) -> float | None:
    """Return the fraction along a route segment where it meets the gate."""
    route_vector = (route_b[0] - route_a[0], route_b[1] - route_a[1])
    gate_vector = (gate_b[0] - gate_a[0], gate_b[1] - gate_a[1])
    offset = (gate_a[0] - route_a[0], gate_a[1] - route_a[1])
    denominator = _cross(route_vector, gate_vector)
    if abs(denominator) <= epsilon:
        return None
    route_fraction = _cross(offset, gate_vector) / denominator
    gate_fraction = _cross(offset, route_vector) / denominator
    if -epsilon <= route_fraction <= 1 + epsilon and -epsilon <= gate_fraction <= 1 + epsilon:
        return min(1.0, max(0.0, route_fraction))
    return None


def route_gate_metrics(
    route: list[tuple[float, float]],
    route_km: float,
    gate: list[tuple[float, float]],
) -> dict[str, float | bool | None]:
    """Find the first real route/gate intersection and post-gate distance."""
    if len(route) < 2 or len(gate) != 2 or route_km <= 0:
        return {
            "crosses_checkpoint": False,
            "intersection_chainage_km": None,
            "external_km": 0.0,
        }
    segment_lengths = [haversine_km(a, b) for a, b in zip(route, route[1:], strict=False)]
    geometry_km = sum(segment_lengths)
    if geometry_km <= 0:
        return {
            "crosses_checkpoint": False,
            "intersection_chainage_km": None,
            "external_km": 0.0,
        }
    traversed = 0.0
    for index, (a, b) in enumerate(zip(route, route[1:], strict=False)):
        fraction = segment_intersection_fraction(a, b, gate[0], gate[1])
        if fraction is not None:
            chainage = (traversed + segment_lengths[index] * fraction) * route_km / geometry_km
            chainage = min(route_km, max(0.0, chainage))
            return {
                "crosses_checkpoint": True,
                "intersection_chainage_km": chainage,
                "external_km": max(0.0, route_km - chainage),
            }
        traversed += segment_lengths[index]
    return {
        "crosses_checkpoint": False,
        "intersection_chainage_km": None,
        "external_km": 0.0,
    }


def weighted_jenks_breaks(values: list[float], class_count: int) -> list[float]:
    """Exact Jenks breaks using value frequencies without expanding the DP."""
    levels = sorted(Counter(values).items())
    level_count = len(levels)
    if not levels or class_count < 1:
        return []
    if class_count >= level_count:
        return [value for value, _frequency in levels]

    counts = [0]
    sums = [0.0]
    squares = [0.0]
    for value, frequency in levels:
        counts.append(counts[-1] + frequency)
        sums.append(sums[-1] + value * frequency)
        squares.append(squares[-1] + value * value * frequency)

    def variance(first: int, last: int) -> float:
        weight = counts[last] - counts[first - 1]
        total = sums[last] - sums[first - 1]
        total_sq = squares[last] - squares[first - 1]
        return total_sq - total * total / weight

    infinite = float("inf")
    scores = [[infinite] * (level_count + 1) for _ in range(class_count + 1)]
    starts = [[0] * (level_count + 1) for _ in range(class_count + 1)]
    scores[0][0] = 0.0
    for group in range(1, class_count + 1):
        for last in range(group, level_count + 1):
            for first in range(group, last + 1):
                score = scores[group - 1][first - 1] + variance(first, last)
                if score < scores[group][last] - 1e-12:
                    scores[group][last] = score
                    starts[group][last] = first

    breaks: list[float] = []
    last = level_count
    for group in range(class_count, 0, -1):
        first = starts[group][last]
        breaks.append(levels[last - 1][0])
        last = first - 1
    return list(reversed(breaks))


def gvf(values: list[float], breaks: list[float]) -> float:
    mean = sum(values) / len(values)
    total_variance = sum((value - mean) ** 2 for value in values)
    classes: dict[int, list[float]] = {}
    for value in values:
        class_index = 0
        while class_index < len(breaks) - 1 and value > breaks[class_index]:
            class_index += 1
        classes.setdefault(class_index, []).append(value)
    within_variance = sum(
        sum((value - sum(group) / len(group)) ** 2 for value in group)
        for group in classes.values()
    )
    return 1.0 - within_variance / total_variance if total_variance else 1.0
