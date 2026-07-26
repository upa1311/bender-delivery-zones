#!/usr/bin/env python
"""Audit every immutable v1.1 delivery address against the live local OSRM.

The release registry is the canonical address list. Coordinates are joined by
the same stable uid from the protected delivery-units source because the
immutable resolver registry intentionally does not duplicate coordinates.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "releases/bender-zones-v1.1/address-registry.json"
COORDINATES = REPO / "docs/data/delivery-units.csv"
DISCREPANCIES = REPO / "docs/data/manual-yandex-address-discrepancies.csv"
CROSSINGS = REPO / "docs/data/stage-09b-road-rail-crossings.csv"
OUTPUT = REPO / "data/interim/all-address-router-audit-v1.csv"
CHECKPOINT = REPO / "data/interim/all-address-router-audit-checkpoint-v1.json"
PARTIAL = REPO / "data/interim/all-address-router-audit-v1.partial.csv"

REGISTRY_SHA256 = "bc66ad113a6ba5706bb6d2797ddc543e5b576482051d0d981551f014561c1817"
COORDINATES_SHA256 = "7f52e5119db0bfeb8a68464ad79ed1288a070c3563d887c088f72283c85c4250"
EXPECTED_ADDRESSES = 9_216
ORIGIN = (29.48313, 46.82388)  # lon, lat
DEFAULT_BASE_URL = "http://127.0.0.1:5000"
VALID_STATUSES = {"ROUTABLE", "UNREACHABLE", "ROUTER_ERROR", "INVALID_COORDINATES"}
CHECKPOINT_INTERVAL = 50

FIELDS = [
    "address_id",
    "address_release_version",
    "territory",
    "district",
    "street",
    "house_number",
    "destination_lat",
    "destination_lon",
    "router_status",
    "router_distance_km",
    "router_duration_min",
    "straight_line_km",
    "detour_factor",
    "snapped_origin_lat",
    "snapped_origin_lon",
    "origin_snap_distance_m",
    "snapped_destination_lat",
    "snapped_destination_lon",
    "destination_snap_distance_m",
    "router_main_streets",
    "route_node_count",
    "route_first_nodes",
    "route_last_nodes",
    "terminal_node_signature",
    "corridor_signature",
    "bridge_or_rail",
    "uturn",
    "route_geometry_hash",
    "probable_anomaly",
    "anomaly_severity",
    "owner_review_required",
]


def normalized_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def load_addresses() -> tuple[list[dict[str, str]], dict]:
    actual_registry = normalized_sha256(REGISTRY)
    actual_coordinates = normalized_sha256(COORDINATES)
    if actual_registry != REGISTRY_SHA256:
        raise RuntimeError(
            f"canonical registry hash mismatch: {actual_registry} != {REGISTRY_SHA256}"
        )
    if actual_coordinates != COORDINATES_SHA256:
        raise RuntimeError(
            f"coordinate source hash mismatch: {actual_coordinates} != {COORDINATES_SHA256}"
        )

    release = json.loads(REGISTRY.read_text(encoding="utf-8"))
    registry = release["addresses"]
    coordinate_rows = read_csv(COORDINATES)
    coordinates = {row["uid"]: row for row in coordinate_rows}
    ids = [row["uid"] for row in registry]
    canonical_keys = [row["canonical_address_key"] for row in registry]
    if len(ids) != EXPECTED_ADDRESSES or len(set(ids)) != len(ids):
        raise RuntimeError("registry must contain 9,216 unique uid values")
    if len(set(canonical_keys)) != len(canonical_keys):
        raise RuntimeError("registry canonical addresses are not unique")

    missing = [address_id for address_id in ids if address_id not in coordinates]
    if missing:
        raise RuntimeError(f"registry addresses missing coordinate rows: {missing[:10]}")

    addresses = []
    for item in registry:
        coordinate = coordinates[item["uid"]]
        if (
            item["street_ru"] != coordinate["street_ru"]
            or item["housenumber"] != coordinate["housenumber"]
        ):
            raise RuntimeError(f"registry/coordinate identity mismatch: {item['uid']}")
        addresses.append(
            {
                "address_id": item["uid"],
                "address_release_version": release["version"],
                "territory": item["settlement_ru"] or "",
                "district": item["district_ru"] or "",
                "street": item["street_ru"] or "",
                "house_number": item["housenumber"] or "",
                "destination_lat": coordinate["lat"],
                "destination_lon": coordinate["lon"],
            }
        )
    addresses.sort(key=lambda row: row["address_id"])
    return addresses, release


def haversine_km(a_lon: float, a_lat: float, b_lon: float, b_lat: float) -> float:
    radius = 6_371.0088
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    term = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(term))


def ordered_streets(steps: list[dict]) -> list[str]:
    result: list[str] = []
    for step in steps:
        name = (step.get("name") or "").strip()
        if name and (not result or result[-1] != name):
            result.append(name)
    return result


def name_tokens(value: str) -> set[str]:
    ignored = {"улица", "ул", "переулок", "пер", "тупик", "проезд"}
    return {
        token
        for word in value.casefold().replace("-", " ").split()
        if (token := "".join(character for character in word if character.isalnum()))
        and token not in ignored
    }


def stable_signature(values: list[str]) -> str:
    text = "\x1f".join(values)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]


def geometry_hash(coordinates: list[list[float]]) -> str:
    rounded = [[round(lon, 6), round(lat, 6)] for lon, lat in coordinates]
    payload = json.dumps(rounded, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def crossing_points() -> list[tuple[float, float, str]]:
    result = []
    for row in read_csv(CROSSINGS):
        if row["classification"] in {"BRIDGE", "TUNNEL", "LEVEL_CROSSING"}:
            result.append((float(row["lon"]), float(row["lat"]), row["classification"]))
    return result


def route_crossings(
    geometry: list[list[float]], points: list[tuple[float, float, str]]
) -> str:
    found = {
        classification
        for route_lon, route_lat in geometry
        for crossing_lon, crossing_lat, classification in points
        if haversine_km(route_lon, route_lat, crossing_lon, crossing_lat) <= 0.025
    }
    return ";".join(sorted(found)) if found else "NONE_OBSERVED"


def empty_result(address: dict[str, str], status: str, anomaly: str) -> dict[str, str]:
    row = {field: "" for field in FIELDS}
    row.update(address)
    row.update(
        {
            "router_status": status,
            "uturn": "UNKNOWN",
            "probable_anomaly": anomaly,
            "anomaly_severity": "CRITICAL",
            "owner_review_required": "True",
        }
    )
    return row


def request_route(
    base_url: str, destination: tuple[float, float], retries: int = 3
) -> tuple[str, dict | None, str]:
    coordinates = (
        f"{ORIGIN[0]:.7f},{ORIGIN[1]:.7f};"
        f"{destination[0]:.7f},{destination[1]:.7f}"
    )
    query = urllib.parse.urlencode(
        {
            "alternatives": "false",
            "overview": "full",
            "geometries": "geojson",
            "steps": "true",
            "annotations": "nodes",
        }
    )
    url = f"{base_url.rstrip('/')}/route/v1/driving/{coordinates}?{query}"
    last_error = ""
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            code = payload.get("code")
            if code == "Ok" and payload.get("routes"):
                return "ROUTABLE", payload, ""
            if code in {"NoRoute", "NoSegment"}:
                return "UNREACHABLE", payload, str(code)
            last_error = f"OSRM code {code!r}"
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < retries:
            time.sleep(0.1 * attempt)
    return "ROUTER_ERROR", None, last_error


def evaluate_address(
    address: dict[str, str],
    base_url: str,
    crossings: list[tuple[float, float, str]],
) -> dict[str, str]:
    try:
        lat = float(address["destination_lat"])
        lon = float(address["destination_lon"])
    except (TypeError, ValueError):
        return empty_result(address, "INVALID_COORDINATES", "INVALID_COORDINATES")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return empty_result(address, "INVALID_COORDINATES", "INVALID_COORDINATES")

    status, response, error = request_route(base_url, (lon, lat))
    if status != "ROUTABLE" or response is None:
        return empty_result(address, status, error or status)

    route = response["routes"][0]
    leg = route["legs"][0]
    waypoints = response["waypoints"]
    geometry = route["geometry"]["coordinates"]
    steps = leg.get("steps", [])
    streets = ordered_streets(steps)
    nodes = [str(node) for node in (leg.get("annotation", {}).get("nodes") or [])]
    straight = haversine_km(ORIGIN[0], ORIGIN[1], lon, lat)
    distance = float(route["distance"]) / 1000
    duration = float(route["duration"]) / 60
    origin_location = waypoints[0]["location"]
    destination_location = waypoints[1]["location"]
    crossing = route_crossings(geometry, crossings)
    uturn = any(
        step.get("maneuver", {}).get("modifier") == "uturn" for step in steps
    )
    loop = len(streets) != len(set(streets))
    anomalies = []
    snap = float(waypoints[1]["distance"])
    if snap > 100:
        anomalies.append("DESTINATION_SNAP_GT100M")
    elif snap > 60:
        anomalies.append("DESTINATION_SNAP_GT60M")
    elif snap > 30:
        anomalies.append("DESTINATION_SNAP_GT30M")
    if straight <= 0:
        anomalies.append("IMPOSSIBLE_STRAIGHT_LINE")
    if uturn:
        anomalies.append("UTURN")
    if loop:
        anomalies.append("ROUTE_STREET_LOOP")
    snapped_name = waypoints[1].get("name", "")
    if snapped_name and not (name_tokens(address["street"]) & name_tokens(snapped_name)):
        anomalies.append("SNAPPED_STREET_NAME_MISMATCH")

    terminal_values = streets[-2:] if streets else [waypoints[1].get("name", "")]
    corridor_values = streets[:5] + [crossing]
    row = {field: "" for field in FIELDS}
    row.update(address)
    row.update(
        {
            "router_status": status,
            "router_distance_km": f"{distance:.4f}",
            "router_duration_min": f"{duration:.3f}",
            "straight_line_km": f"{straight:.4f}",
            "detour_factor": f"{distance / straight:.3f}" if straight > 0 else "",
            "snapped_origin_lat": f"{origin_location[1]:.7f}",
            "snapped_origin_lon": f"{origin_location[0]:.7f}",
            "origin_snap_distance_m": f"{float(waypoints[0]['distance']):.2f}",
            "snapped_destination_lat": f"{destination_location[1]:.7f}",
            "snapped_destination_lon": f"{destination_location[0]:.7f}",
            "destination_snap_distance_m": f"{snap:.2f}",
            "router_main_streets": "; ".join(streets),
            "route_node_count": str(len(nodes)),
            "route_first_nodes": ";".join(nodes[:8]),
            "route_last_nodes": ";".join(nodes[-8:]),
            "terminal_node_signature": stable_signature(terminal_values),
            "corridor_signature": stable_signature(corridor_values),
            "bridge_or_rail": crossing,
            "uturn": "YES" if uturn else "NO",
            "route_geometry_hash": geometry_hash(geometry),
            "probable_anomaly": ";".join(anomalies) if anomalies else "NONE",
            "anomaly_severity": "CRITICAL"
            if snap > 100
            else "HIGH"
            if snap > 60 or uturn
            else "MEDIUM"
            if anomalies
            else "NONE",
            "owner_review_required": str(bool(anomalies)),
        }
    )
    return row


def percentile(values: list[float], proportion: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    position = (len(ordered) - 1) * proportion
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def robust_limit(values: list[float], upper_percentile: float = 0.95) -> float:
    median = statistics.median(values)
    mad = statistics.median(abs(value - median) for value in values)
    return max(percentile(values, upper_percentile), median + 6 * mad)


def nearest_neighbors(row: dict[str, str], group: list[dict[str, str]], count: int = 4):
    lon, lat = float(row["destination_lon"]), float(row["destination_lat"])
    candidates = [
        (
            haversine_km(
                lon,
                lat,
                float(other["destination_lon"]),
                float(other["destination_lat"]),
            ),
            other,
        )
        for other in group
        if other["address_id"] != row["address_id"]
    ]
    return [other for _, other in sorted(candidates, key=lambda item: item[0])[:count]]


def discrepancy_flags(rows: list[dict[str, str]]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    routable = [row for row in rows if row["router_status"] == "ROUTABLE"]
    for discrepancy in read_csv(DISCREPANCIES):
        lat, lon = float(discrepancy["destination_lat"]), float(
            discrepancy["destination_lon"]
        )
        nearest = min(
            routable,
            key=lambda row: haversine_km(
                lon,
                lat,
                float(row["destination_lon"]),
                float(row["destination_lat"]),
            ),
        )
        distance_m = 1000 * haversine_km(
            lon,
            lat,
            float(nearest["destination_lon"]),
            float(nearest["destination_lat"]),
        )
        if distance_m <= 50:
            result[nearest["address_id"]].add(discrepancy["flag"])
    return result


def annotate_anomalies(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    routable = [row for row in rows if row["router_status"] == "ROUTABLE"]
    for row in routable:
        groups[(row["territory"], row["district"], row["street"])].append(row)

    all_detours = [float(row["detour_factor"]) for row in routable if row["detour_factor"]]
    detours_by_territory: dict[str, list[float]] = defaultdict(list)
    for row in routable:
        if row["detour_factor"]:
            detours_by_territory[row["territory"]].append(float(row["detour_factor"]))
    discrepancy_by_id = discrepancy_flags(rows)

    origin_signatures = {
        (
            row["snapped_origin_lat"],
            row["snapped_origin_lon"],
            row["origin_snap_distance_m"],
        )
        for row in routable
    }
    if len(origin_signatures) > 1:
        for row in routable:
            add_anomalies(row, ["ORIGIN_SNAP_INCONSISTENCY"], "CRITICAL")

    snap_groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in routable:
        if float(row["destination_snap_distance_m"] or 0) > 30:
            snap_groups[
                (row["snapped_destination_lat"], row["snapped_destination_lon"])
            ].append(row)
    for group in snap_groups.values():
        if len(group) < 2:
            continue
        first = group[0]
        spread_m = max(
            1000
            * haversine_km(
                float(first["destination_lon"]),
                float(first["destination_lat"]),
                float(other["destination_lon"]),
                float(other["destination_lat"]),
            )
            for other in group[1:]
        )
        if spread_m > 100:
            for row in group:
                add_anomalies(row, ["SHARED_DISTANT_SNAP_NODE"], "HIGH")

    for group in groups.values():
        if len(group) < 5:
            continue
        distance_deltas = []
        duration_deltas = []
        for row in group:
            neighbors = nearest_neighbors(row, group)
            if neighbors:
                distance_deltas.append(
                    abs(
                        float(row["router_distance_km"])
                        - statistics.median(
                            float(item["router_distance_km"]) for item in neighbors
                        )
                    )
                )
                duration_deltas.append(
                    abs(
                        float(row["router_duration_min"])
                        - statistics.median(
                            float(item["router_duration_min"]) for item in neighbors
                        )
                    )
                )
        distance_limit = robust_limit(distance_deltas)
        duration_limit = robust_limit(duration_deltas)
        corridor_counts = Counter(row["corridor_signature"] for row in group)
        terminal_counts = Counter(row["terminal_node_signature"] for row in group)
        for row in group:
            neighbors = nearest_neighbors(row, group)
            if not neighbors:
                continue
            distance_delta = abs(
                float(row["router_distance_km"])
                - statistics.median(float(item["router_distance_km"]) for item in neighbors)
            )
            duration_delta = abs(
                float(row["router_duration_min"])
                - statistics.median(float(item["router_duration_min"]) for item in neighbors)
            )
            additions = []
            if distance_delta > distance_limit:
                additions.append("STREET_DISTANCE_CONTINUITY_OUTLIER")
            if duration_delta > duration_limit:
                additions.append("STREET_DURATION_CONTINUITY_OUTLIER")
            neighbor_corridors = Counter(item["corridor_signature"] for item in neighbors)
            if (
                corridor_counts[row["corridor_signature"]] == 1
                and row["corridor_signature"] not in neighbor_corridors
            ):
                additions.append("LOCAL_CORRIDOR_DISCONTINUITY")
            if terminal_counts[row["terminal_node_signature"]] == 1:
                additions.append("UNIQUE_TERMINAL_BRANCH")
            add_anomalies(row, additions, "HIGH")

    global_detour_limit = robust_limit(all_detours, 0.99)
    for row in rows:
        additions = []
        if row["router_status"] == "ROUTABLE" and row["detour_factor"]:
            territory_values = detours_by_territory[row["territory"]]
            territory_limit = (
                robust_limit(territory_values, 0.99)
                if len(territory_values) >= 20
                else global_detour_limit
            )
            if float(row["detour_factor"]) > territory_limit:
                additions.append("ROBUST_HIGH_DETOUR_FACTOR")
        additions.extend(sorted(discrepancy_by_id.get(row["address_id"], set())))
        add_anomalies(row, additions, "HIGH")
    return rows


def add_anomalies(row: dict[str, str], additions: list[str], severity: str) -> None:
    if not additions:
        return
    current = set(filter(None, row["probable_anomaly"].replace("NONE", "").split(";")))
    current.update(additions)
    row["probable_anomaly"] = ";".join(sorted(current))
    rank = {"NONE": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    if rank[severity] > rank[row["anomaly_severity"]]:
        row["anomaly_severity"] = severity
    row["owner_review_required"] = "True"


def checkpoint_payload(
    rows: list[dict[str, str]],
    total: int,
    started_at: str,
    base_url: str,
    complete: bool,
) -> dict:
    counts = Counter(row["router_status"] for row in rows)
    return {
        "total_addresses": total,
        "processed_addresses": len(rows),
        "routable": counts["ROUTABLE"],
        "unreachable": counts["UNREACHABLE"],
        "router_errors": counts["ROUTER_ERROR"],
        "invalid_coordinates": counts["INVALID_COORDINATES"],
        "started_at": started_at,
        "updated_at": utc_now(),
        "input_sha256": REGISTRY_SHA256,
        "osrm_base_url": base_url,
        "complete": complete,
    }


def validate_resume(checkpoint: dict, total: int, base_url: str) -> None:
    expected = {
        "total_addresses": total,
        "input_sha256": REGISTRY_SHA256,
        "osrm_base_url": base_url,
    }
    mismatches = {
        key: (checkpoint.get(key), value)
        for key, value in expected.items()
        if checkpoint.get(key) != value
    }
    if mismatches:
        raise RuntimeError(f"unsafe checkpoint mismatch: {mismatches}")


def run(args: argparse.Namespace) -> list[dict[str, str]]:
    addresses, _ = load_addresses()
    if OUTPUT.exists() and not args.overwrite:
        raise FileExistsError(f"completed audit exists; use --overwrite: {OUTPUT}")
    if args.overwrite:
        for path in (OUTPUT, CHECKPOINT, PARTIAL):
            if path.exists():
                path.unlink()

    started_at = utc_now()
    completed: dict[str, dict[str, str]] = {}
    if CHECKPOINT.exists() or PARTIAL.exists():
        if not CHECKPOINT.exists() or not PARTIAL.exists():
            raise RuntimeError("checkpoint and partial CSV must exist together")
        checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
        validate_resume(checkpoint, len(addresses), args.base_url)
        started_at = checkpoint["started_at"]
        partial_rows = read_csv(PARTIAL)
        completed = {row["address_id"]: row for row in partial_rows}
        if len(completed) != len(partial_rows):
            raise RuntimeError("duplicate address_id in resume partial CSV")
        if len(completed) != checkpoint["processed_addresses"]:
            raise RuntimeError("checkpoint count does not match partial CSV")

    pending = [row for row in addresses if row["address_id"] not in completed]
    crossings = crossing_points()
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(evaluate_address, address, args.base_url, crossings): address
            for address in pending
        }
        since_checkpoint = 0
        for future in as_completed(futures):
            result = future.result()
            completed[result["address_id"]] = result
            since_checkpoint += 1
            if since_checkpoint >= CHECKPOINT_INTERVAL:
                ordered = [completed[key] for key in sorted(completed)]
                write_csv(PARTIAL, ordered)
                atomic_json(
                    CHECKPOINT,
                    checkpoint_payload(
                        ordered, len(addresses), started_at, args.base_url, False
                    ),
                )
                since_checkpoint = 0

    ordered = [completed[key] for key in sorted(completed)]
    if len(ordered) != len(addresses):
        raise RuntimeError("audit finished with missing addresses")
    annotate_anomalies(ordered)
    write_csv(OUTPUT, ordered)
    atomic_json(
        CHECKPOINT,
        checkpoint_payload(ordered, len(addresses), started_at, args.base_url, True),
    )
    if PARTIAL.exists():
        PARTIAL.unlink()
    return ordered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 16:
        parser.error("--workers must be between 1 and 16")
    rows = run(args)
    counts = Counter(row["router_status"] for row in rows)
    print(
        json.dumps(
            {"addresses": len(rows), "statuses": counts},
            ensure_ascii=True,
            indent=2,
            default=dict,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
