#!/usr/bin/env python
"""Stage 09 routing-truth engine (shared, read-only).

The zone metric follows the owner clarification: a home's zone comes ONLY from
the FASTEST VALID driving route (minimum realistic travel duration) found over
the whole connected graph by OSRM's car profile — which already respects
oneway/access/barriers/turn-restrictions — never straight-line, nearest road,
a random alternative, a fixed district entry, or a street's "primary zone".

For each origin we take OSRM's default route (global min-duration shortest path),
plus alternatives and the shortest-distance variant among them, all with full
GeoJSON geometry, and split the chosen route into in-city / outside-city km
against the real Bender OSM boundary. `equivalent_city_km` is a PROVISIONAL
relative difficulty weight (owner_review), NOT money and NOT a Direct tariff.

Nothing here writes prices, edits an immutable release, or touches Direct.
"""

from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from shapely.geometry import Point, shape

OSRM = "http://127.0.0.1:5000"
REPO = Path(__file__).resolve().parents[1]

# Owner-stated local taxi km rates (words only — NOT a Direct price/tariff).
CITY_KM_RATE = 6.0
OUTSIDE_KM_RATE = 10.0
OUTSIDE_MULTIPLIER = OUTSIDE_KM_RATE / CITY_KM_RATE  # 1.6666667

# Confirmed restaurant origins (lon, lat, weight). Actual split is 85/10/5.
ORIGINS = [
    {"key": "central", "lon": 29.48313, "lat": 46.82388, "weight": 0.85},
    {"key": "bam", "lon": 29.47296, "lat": 46.84167, "weight": 0.10},
    {"key": "outer_other", "lon": 29.48801, "lat": 46.83396, "weight": 0.05},
]

# OSM place=suburb/neighbourhood district markers inside Bender (points only —
# no invented boundaries; used for nearest-place district labelling).
OSM_PLACES = {
    "Борисовка": (46.839237, 29.465056),
    "Хомутяновка": (46.824091, 29.461572),
    "Солнечный": (46.849424, 29.464830),
    "Птичник": (46.844477, 29.456476),
    "Ленинский": (46.802269, 29.468510),
    "Шёлковый": (46.790543, 29.487187),
    "Липканы": (46.846220, 29.480155),
    "Центр": (46.823417, 29.481791),
    "Балка": (46.813598, 29.468583),
    "Кавказ": (46.806550, 29.484333),
    "Нижний Днестр": (46.816315, 29.491366),
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def line_km(coords: list[list[float]]) -> float:
    """Geodesic length of a [lon,lat] polyline in km."""
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(coords, coords[1:], strict=False):
        total += haversine_km(lat1, lon1, lat2, lon2)
    return total


def _get(path: str) -> dict:
    with urllib.request.urlopen(f"{OSRM}/{path}", timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


@dataclass
class RouteResult:
    ok: bool
    distance_km: float | None = None
    duration_s: float | None = None
    geometry: list[list[float]] = field(default_factory=list)  # [lon,lat]
    alternatives: list[dict] = field(default_factory=list)  # {distance_km,duration_s,geometry}


def route_full(origin_lonlat, dest_lonlat) -> RouteResult:
    """OSRM fastest (min-duration) route + up to 3 alternatives, full geometry."""
    a = f"{origin_lonlat[0]:.6f},{origin_lonlat[1]:.6f}"
    b = f"{dest_lonlat[0]:.6f},{dest_lonlat[1]:.6f}"
    q = urllib.parse.urlencode(
        {"overview": "full", "geometries": "geojson", "alternatives": "3", "steps": "false"}
    )
    data = _get(f"route/v1/driving/{a};{b}?{q}")
    if data.get("code") != "Ok" or not data.get("routes"):
        return RouteResult(ok=False)
    routes = data["routes"]
    best = routes[0]  # OSRM orders by duration (fastest first)
    alts = [
        {
            "distance_km": round(r["distance"] / 1000, 4),
            "duration_s": round(r["duration"], 1),
            "geometry": r["geometry"]["coordinates"],
        }
        for r in routes[1:]
    ]
    return RouteResult(
        ok=True,
        distance_km=round(best["distance"] / 1000, 4),
        duration_s=round(best["duration"], 1),
        geometry=best["geometry"]["coordinates"],
        alternatives=alts,
    )


def nearest(lon: float, lat: float) -> dict:
    """OSRM snap diagnostics for a coordinate: snapped point + snap distance."""
    data = _get(f"nearest/v1/driving/{lon:.6f},{lat:.6f}?number=1")
    if data.get("code") != "Ok" or not data.get("waypoints"):
        return {"ok": False}
    wp = data["waypoints"][0]
    slon, slat = wp["location"]
    return {
        "ok": True,
        "snap_lon": round(slon, 6),
        "snap_lat": round(slat, 6),
        "snap_distance_m": round(haversine_km(lat, lon, slat, slon) * 1000, 1),
        "snapped_name": wp.get("name") or "",
    }


def load_bender_boundary():
    gj = json.loads((REPO / "docs/data/source-boundaries.geojson").read_text("utf-8"))
    for f in gj["features"]:
        if f["properties"].get("key") == "bender":
            return shape(f["geometry"])
    raise SystemExit("Bender boundary not found")


def segment_in_out_city(geometry: list[list[float]], boundary) -> dict:
    """Split a [lon,lat] route into in-city / outside-city km against the Bender
    OSM boundary, and report the first exit point and whether it re-enters."""
    if len(geometry) < 2:
        return {
            "in_city_km": 0.0,
            "outside_city_km": 0.0,
            "crosses_boundary": False,
            "first_exit_lonlat": None,
            "reenters_city": False,
        }
    in_km = 0.0
    out_km = 0.0
    first_exit = None
    reenters = False
    was_outside = False
    for (lon1, lat1), (lon2, lat2) in zip(geometry, geometry[1:], strict=False):
        seg_km = haversine_km(lat1, lon1, lat2, lon2)
        mid = Point((lon1 + lon2) / 2, (lat1 + lat2) / 2)
        inside = boundary.contains(mid)
        if inside:
            in_km += seg_km
            if was_outside:
                reenters = True
            was_outside = False
        else:
            out_km += seg_km
            if first_exit is None:
                first_exit = [round((lon1 + lon2) / 2, 6), round((lat1 + lat2) / 2, 6)]
            was_outside = True
    return {
        "in_city_km": round(in_km, 4),
        "outside_city_km": round(out_km, 4),
        "crosses_boundary": out_km > 0.02,
        "first_exit_lonlat": first_exit,
        "reenters_city": reenters,
    }


def equivalent_city_km(in_city_km: float, outside_city_km: float) -> float:
    return round(in_city_km + outside_city_km * OUTSIDE_MULTIPLIER, 4)


def nearest_osm_place(lat: float, lon: float) -> tuple[str, float]:
    best_name, best_km = "", 1e9
    for name, (plat, plon) in OSM_PLACES.items():
        d = haversine_km(lat, lon, plat, plon)
        if d < best_km:
            best_name, best_km = name, d
    return best_name, round(best_km, 3)


def load_address_points() -> list[dict]:
    gj = json.loads((REPO / "docs/data/final-address-zone-points.geojson").read_text("utf-8"))
    out = []
    for f in gj["features"]:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"]
        out.append(
            {
                "uid": p["uid"],
                "settlement_ru": p["settlement_ru"],
                "district_ru": p.get("district_ru"),
                "street_ru": p["street_ru"],
                "housenumber": p["housenumber"],
                "zone_id": p["zone_id"],
                "central_km": p.get("central_km"),
                "bam_km": p.get("bam_km"),
                "expected_km": p.get("expected_km"),
                "service_status": p.get("service_status"),
                "address_status": p.get("address_status"),
                "lat": round(lat, 6),
                "lon": round(lon, 6),
            }
        )
    return out


if __name__ == "__main__":
    # Self-check: route the three owner-named anomalies from the central origin.
    boundary = load_bender_boundary()
    central = (ORIGINS[0]["lon"], ORIGINS[0]["lat"])
    for name, (plat, plon) in [
        ("Борисовка place", OSM_PLACES["Борисовка"]),
        ("Хомутяновка place", OSM_PLACES["Хомутяновка"]),
        ("Паркан entry ~", (46.8372, 29.5174)),
    ]:
        r = route_full(central, (plon, plat))
        seg = segment_in_out_city(r.geometry, boundary) if r.ok else {}
        print(
            name,
            "dist_km", r.distance_km,
            "dur_s", r.duration_s,
            "in", seg.get("in_city_km"),
            "out", seg.get("outside_city_km"),
            "eq_km", equivalent_city_km(seg.get("in_city_km", 0), seg.get("outside_city_km", 0)),
            "alts", len(r.alternatives),
        )
