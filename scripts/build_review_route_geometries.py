"""Build compact shortest-distance route geometry for the static review tool.

This is an explicit data-preparation step.  It first uses an operator-supplied
OSRM instance built from the pinned Moldova PBF.  Only missing published
alternatives are recovered from the same public OSRM provider that produced the
committed distance inventory.  Every geometry must match its published length
within two metres, and the polyline6 payload is committed so GitHub Pages never
needs a routing service at run time.
"""

from __future__ import annotations

import argparse
import json
import time
import unicodedata
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POINTS = ROOT / "docs/data/final-address-zone-points.geojson"
REGISTRY = ROOT / "releases/bender-zones-v1.1/address-registry.json"
ROUTING = ROOT / "docs/review/data/route-mindist-results.json"
OUTPUT = ROOT / "docs/review/data/review-route-geometries.json"
ORIGIN = (29.48313, 46.82388)
PINNED_PBF_SHA256 = "09ba0c058e89faacac7e1b1e7c8d0fbb14b4df66061b43abdce590b65ce8813c"


def normalize(value: str | None) -> str:
    return unicodedata.normalize("NFKC", (value or "").strip().casefold())


def unique_address_uids() -> set[str]:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))["addresses"]
    seen: set[tuple[str, str, str]] = set()
    included: set[str] = set()
    for row in sorted(registry, key=lambda item: item["uid"]):
        key = (
            normalize(row.get("settlement_ru")),
            normalize(row.get("street_ru")),
            normalize(row.get("housenumber")),
        )
        if key in seen:
            continue
        seen.add(key)
        included.add(row["uid"])
    return included


def fetch_route(
    uid: str,
    coordinate: tuple[float, float],
    expected_km: float,
    osrm_url: str,
    *,
    timeout: int = 30,
) -> tuple[str, list[object]]:
    lon, lat = coordinate
    url = (
        f"{osrm_url.rstrip('/')}/route/v1/driving/"
        f"{ORIGIN[0]},{ORIGIN[1]};{lon},{lat}"
        "?overview=full&geometries=polyline6&steps=false&alternatives=true"
    )
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "bender-delivery-zones-review-geometry/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        payload = json.load(response)
    if payload.get("code") != "Ok" or not payload.get("routes"):
        raise RuntimeError(f"{uid}: OSRM returned {payload.get('code')!r}")
    route = min(
        payload["routes"],
        key=lambda item: abs(item["distance"] / 1000 - expected_km),
    )
    actual_km = route["distance"] / 1000
    if abs(actual_km - expected_km) > 0.002:
        raise ValueError(
            f"{uid}: no geometry matches published route {expected_km:.4f} km; "
            f"closest is {actual_km:.4f} km"
        )
    return uid, [round(actual_km, 4), route["geometry"]]


def fetch_public_fallback(
    uid: str,
    coordinate: tuple[float, float],
    expected_km: float,
    public_osrm_url: str,
) -> tuple[str, list[object]]:
    """Fetch only a route the pinned local graph cannot reproduce.

    The published distance input itself identifies the intended alternative.
    Slow retries keep this operator step courteous and reproducible without
    turning the public demo into a bulk-routing dependency.
    """
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            if attempt:
                time.sleep(2**attempt)
            result = fetch_route(
                uid,
                coordinate,
                expected_km,
                public_osrm_url,
                timeout=60,
            )
            time.sleep(0.15)
            return result
        except (OSError, ValueError, urllib.error.URLError) as error:
            last_error = error
    raise RuntimeError(f"{uid}: public OSRM fallback failed: {last_error}")


def build(osrm_url: str, public_osrm_url: str, workers: int) -> dict:
    point_data = json.loads(POINTS.read_text(encoding="utf-8"))
    coordinates = {
        feature["properties"]["uid"]: tuple(feature["geometry"]["coordinates"])
        for feature in point_data["features"]
    }
    expected = json.loads(ROUTING.read_text(encoding="utf-8"))["results"]
    included = unique_address_uids()
    routes: dict[str, list[object]] = {}
    fallbacks: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(fetch_route, uid, coordinates[uid], values[0], osrm_url): uid
            for uid, values in expected.items()
            if uid in included
        }
        for index, future in enumerate(as_completed(futures), start=1):
            uid = futures[future]
            try:
                _, route = future.result()
                routes[uid] = route
            except (OSError, ValueError, RuntimeError, urllib.error.URLError):
                fallbacks.append(uid)
            if index % 500 == 0:
                print(f"routes={index}/{len(futures)}")
    print(f"local_matches={len(routes)} public_fallbacks={len(fallbacks)}")
    for index, uid in enumerate(sorted(fallbacks), start=1):
        _, route = fetch_public_fallback(
            uid,
            coordinates[uid],
            expected[uid][0],
            public_osrm_url,
        )
        routes[uid] = route
        if index % 25 == 0:
            print(f"public_routes={index}/{len(fallbacks)}")
    return {
        "schema_version": 1,
        "format": "polyline6",
        "origin_lonlat": list(ORIGIN),
        "route_count": len(routes),
        "distance_source": "OSRM alternative matching the published per-address route distance",
        "geometry_build": {
            "local_pinned_graph_matches": len(routes) - len(fallbacks),
            "published_provider_fallbacks": len(fallbacks),
            "published_provider": public_osrm_url,
            "acceptance_tolerance_km": 0.002,
        },
        "pbf_sha256": PINNED_PBF_SHA256,
        "routes": {uid: routes[uid] for uid in sorted(routes)},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--osrm-url", default="http://127.0.0.1:5001")
    parser.add_argument("--public-osrm-url", default="https://router.project-osrm.org")
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    payload = build(args.osrm_url, args.public_osrm_url, args.workers)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote={OUTPUT} routes={payload['route_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
