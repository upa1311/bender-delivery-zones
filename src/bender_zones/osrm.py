"""Minimal client for a LOCAL OSRM server (Stage 06).

The routing engine is a locally built OSRM MLD car profile over the same Moldova
PBF, so one-ways, turn restrictions, barriers, access tags, maxspeed and
bridge/tunnel topology are handled by OSRM itself — not by ad-hoc geometry.

Nothing here talks to a public routing service.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class OsrmError(RuntimeError):
    """Raised when the local OSRM server cannot answer."""


class OsrmClient:
    def __init__(self, base_url: str = "http://127.0.0.1:5000", timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str):
        url = f"{self.base_url}/{path}"
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            raise OsrmError(f"OSRM request failed: {exc}") from exc

    def is_up(self) -> bool:
        try:
            self._get("route/v1/driving/29.4828,46.8242;29.4830,46.8244?overview=false")
            return True
        except OsrmError:
            return False

    def route(self, origin, destination):
        """One route. ``origin``/``destination`` are ``(lon, lat)``.

        Returns ``(distance_m, duration_s)`` or ``None`` when unroutable.
        """
        coords = f"{origin[0]:.6f},{origin[1]:.6f};{destination[0]:.6f},{destination[1]:.6f}"
        data = self._get(f"route/v1/driving/{coords}?overview=false")
        if data.get("code") != "Ok" or not data.get("routes"):
            return None
        r = data["routes"][0]
        return (r["distance"], r["duration"])

    def table(self, sources, destinations, chunk_size: int = 300):
        """Distance/duration matrix from every source to every destination.

        Returns ``(distances_m, durations_s)`` as ``len(sources) x
        len(destinations)`` lists, with ``None`` for unreachable pairs.
        """
        n_src = len(sources)
        distances = [[None] * len(destinations) for _ in range(n_src)]
        durations = [[None] * len(destinations) for _ in range(n_src)]

        for start in range(0, len(destinations), chunk_size):
            batch = destinations[start:start + chunk_size]
            coords = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in
                              list(sources) + list(batch))
            src_idx = ";".join(str(i) for i in range(n_src))
            dst_idx = ";".join(str(n_src + i) for i in range(len(batch)))
            data = self._get(
                f"table/v1/driving/{coords}?sources={src_idx}&destinations={dst_idx}"
                "&annotations=distance,duration")
            if data.get("code") != "Ok":
                raise OsrmError(f"table failed: {data.get('code')} {data.get('message')}")
            for i in range(n_src):
                for j in range(len(batch)):
                    d = data["distances"][i][j]
                    t = data["durations"][i][j]
                    distances[i][start + j] = d
                    durations[i][start + j] = t
        return distances, durations


def expected_cost(per_origin_values, origin_weights):
    """Weight per-origin values by origin share; ``None`` if nothing is reachable.

    This is what makes the restaurant-origin model drive the assignment: the
    number a unit is banded on is the ORIGIN-WEIGHTED expectation, not a single
    origin's distance.
    """
    total, acc = 0.0, 0.0
    for value, weight in zip(per_origin_values, origin_weights, strict=False):
        if value is None:
            continue
        acc += value * weight
        total += weight
    if total <= 0:
        return None
    return acc / total


def worst_cost(per_origin_values):
    """Worst reachable origin value, for QA."""
    vals = [v for v in per_origin_values if v is not None]
    return max(vals) if vals else None
