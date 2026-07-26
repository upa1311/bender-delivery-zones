#!/usr/bin/env python
"""Evaluate the live local OSRM router against completed manual Yandex controls.

The evaluator is intentionally read-only: it does not rebuild the graph, edit
OSM, alter address data, or touch delivery zones.  Output files are write-once
by default so a pre-repair baseline cannot be silently replaced later.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "docs/data"
ORIGIN = (29.48313, 46.82388)  # lon, lat
DEFAULT_BASE_URL = "http://127.0.0.1:5000"
SNAP_WARNING_M = 60.0
MEASUREMENTS_SHA256 = "58a71e47ac546f2788af0fc977709db169baea792bb866184e8ca926e177571c"
CONTROLS_SHA256 = "5ff6617f3a51145febcd77dfe0ffeedc7f14bdcda268552b6b01f76c4c07a4ca"

FIELDS = [
    "control_id", "district", "destination_lat", "destination_lon",
    "yandex_fastest_km", "current_router_km", "signed_delta_km",
    "absolute_divergence_pct", "router_status", "snapped_origin",
    "snapped_destination", "origin_snap_distance_m", "snap_distance_m",
    "router_main_streets", "bridge_or_rail", "uturn", "route_node_ids",
    "probable_root_cause", "owner_review_required",
]


def sha256_file(path: Path) -> str:
    # Git's canonical LF content is the invariant. This keeps the guard stable
    # on both Windows CRLF checkouts and clean LF verification clones.
    content = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(content).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def assert_golden_inputs() -> None:
    actual_measurements = sha256_file(DATA / "manual-yandex-measurements.csv")
    actual_controls = sha256_file(DATA / "manual-yandex-route-controls.csv")
    if actual_measurements != MEASUREMENTS_SHA256:
        raise RuntimeError(
            "manual Yandex measurements changed: "
            f"expected {MEASUREMENTS_SHA256}, got {actual_measurements}"
        )
    if actual_controls != CONTROLS_SHA256:
        raise RuntimeError(
            f"route controls changed: expected {CONTROLS_SHA256}, got {actual_controls}"
        )


def load_controls() -> list[tuple[dict[str, str], dict[str, str]]]:
    assert_golden_inputs()
    controls = read_csv(DATA / "manual-yandex-route-controls.csv")
    measurements = read_csv(DATA / "manual-yandex-measurements.csv")
    by_id = {row["control_id"]: row for row in measurements}
    ids = [row["control_id"] for row in controls]
    if len(ids) != 86 or len(set(ids)) != 86:
        raise RuntimeError("expected exactly 86 unique route controls")
    missing = [control_id for control_id in ids if control_id not in by_id]
    if missing:
        raise RuntimeError(f"controls without manual measurements: {missing}")
    return [(row, by_id[row["control_id"]]) for row in controls]


def load_discrepancy_flags() -> dict[str, set[str]]:
    flags: dict[str, set[str]] = {}
    for row in read_csv(DATA / "manual-yandex-address-discrepancies.csv"):
        flags[row["control_id"]] = set(filter(None, row["flag"].split(";")))
    return flags


def load_crossings() -> list[tuple[float, float, str]]:
    crossings = []
    path = DATA / "stage-09b-road-rail-crossings.csv"
    for row in read_csv(path):
        if row["classification"] in {"BRIDGE", "TUNNEL", "LEVEL_CROSSING"}:
            crossings.append((float(row["lon"]), float(row["lat"]), row["classification"]))
    return crossings


def haversine_m(a_lon: float, a_lat: float, b_lon: float, b_lat: float) -> float:
    radius = 6_371_008.8
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    term = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(term))


def ordered_unique(values: list[str]) -> list[str]:
    result = []
    for value in values:
        value = value.strip()
        if value and (not result or result[-1] != value):
            result.append(value)
    return result


def request_route(base_url: str, destination: tuple[float, float]) -> dict:
    coords = f"{ORIGIN[0]:.7f},{ORIGIN[1]:.7f};{destination[0]:.7f},{destination[1]:.7f}"
    query = urllib.parse.urlencode({
        "overview": "full",
        "geometries": "geojson",
        "steps": "true",
        "annotations": "nodes,distance,duration",
    })
    url = f"{base_url.rstrip('/')}/route/v1/driving/{coords}?{query}"
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"local OSRM request failed: {exc}") from exc


def route_crossings(route_coordinates, crossings) -> str:
    found = set()
    for route_lon, route_lat in route_coordinates:
        for crossing_lon, crossing_lat, classification in crossings:
            if haversine_m(route_lon, route_lat, crossing_lon, crossing_lat) <= 25:
                found.add(classification)
    return ";".join(sorted(found)) if found else "NONE_OBSERVED"


def classify_status(
    distance_km: float | None,
    divergence: float | None,
    snap_m: float | None,
) -> str:
    if distance_km is None:
        return "UNREACHABLE"
    if snap_m is not None and snap_m > SNAP_WARNING_M:
        return "SUSPICIOUS_SNAP"
    if divergence is not None and divergence > 20:
        return "DIVERGENCE_GT20"
    if divergence is not None and divergence > 10:
        return "DIVERGENCE_GT10"
    if divergence is not None and divergence > 5:
        return "DIVERGENCE_GT5"
    return "WITHIN_5_PERCENT"


def probable_root_cause(flags: set[str], status: str) -> str:
    if "SETTLEMENT_DISAGREEMENT" in flags:
        return "TERRITORY_OR_BOUNDARY_AMBIGUOUS"
    if flags & {
        "STREET_NAME_VARIANT",
        "HOUSE_NUMBER_DISAGREEMENT",
        "ADDRESS_ANCHOR_DISAGREEMENT",
    }:
        return "ADDRESS_ANCHOR_AMBIGUOUS"
    if status == "UNREACHABLE":
        return "GRAPH_DISCONNECTED"
    if status == "SUSPICIOUS_SNAP":
        return "WRONG_DESTINATION_SNAP"
    if status in {"DIVERGENCE_GT10", "DIVERGENCE_GT20"}:
        return "ROUTER_CHOOSES_DIFFERENT_VALID_ROUTE"
    return "YANDEX_VENDOR_DIFFERENCE"


def evaluate_one(control, measurement, base_url, flags, crossings) -> dict[str, str]:
    destination = (float(control["destination_lon"]), float(control["destination_lat"]))
    yandex_km = float(measurement["yandex_fastest_distance_km"])
    response = request_route(base_url, destination)
    if response.get("code") != "Ok" or not response.get("routes"):
        status = "UNREACHABLE"
        cause = probable_root_cause(flags, status)
        return {
            "control_id": control["control_id"],
            "district": control["district"],
            "destination_lat": control["destination_lat"],
            "destination_lon": control["destination_lon"],
            "yandex_fastest_km": f"{yandex_km:.4f}",
            "current_router_km": "",
            "signed_delta_km": "",
            "absolute_divergence_pct": "",
            "router_status": status,
            "snapped_origin": "",
            "snapped_destination": "",
            "origin_snap_distance_m": "",
            "snap_distance_m": "",
            "router_main_streets": "",
            "bridge_or_rail": "",
            "uturn": "UNKNOWN",
            "route_node_ids": "",
            "probable_root_cause": cause,
            "owner_review_required": "True",
        }

    route = response["routes"][0]
    waypoints = response["waypoints"]
    leg = route["legs"][0]
    router_km = route["distance"] / 1000
    delta = router_km - yandex_km
    divergence = abs(delta) / yandex_km * 100
    destination_snap = float(waypoints[1]["distance"])
    status = classify_status(router_km, divergence, destination_snap)
    streets = ordered_unique([step.get("name", "") for step in leg.get("steps", [])])
    maneuvers = [step.get("maneuver", {}) for step in leg.get("steps", [])]
    uturn = any(maneuver.get("modifier") == "uturn" for maneuver in maneuvers)
    annotation = leg.get("annotation", {})
    nodes = annotation.get("nodes") or []
    geometry = route.get("geometry", {}).get("coordinates", [])
    origin_location = waypoints[0]["location"]
    destination_location = waypoints[1]["location"]
    cause = probable_root_cause(flags, status)
    return {
        "control_id": control["control_id"],
        "district": control["district"],
        "destination_lat": control["destination_lat"],
        "destination_lon": control["destination_lon"],
        "yandex_fastest_km": f"{yandex_km:.4f}",
        "current_router_km": f"{router_km:.4f}",
        "signed_delta_km": f"{delta:.4f}",
        "absolute_divergence_pct": f"{divergence:.1f}",
        "router_status": status,
        "snapped_origin": f"{origin_location[1]:.7f},{origin_location[0]:.7f}",
        "snapped_destination": f"{destination_location[1]:.7f},{destination_location[0]:.7f}",
        "origin_snap_distance_m": f"{float(waypoints[0]['distance']):.2f}",
        "snap_distance_m": f"{destination_snap:.2f}",
        "router_main_streets": "; ".join(streets),
        "bridge_or_rail": route_crossings(geometry, crossings),
        "uturn": "YES" if uturn else "NO",
        "route_node_ids": ";".join(map(str, nodes)),
        "probable_root_cause": cause,
        "owner_review_required": str(status != "WITHIN_5_PERCENT"),
    }


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    position = (len(ordered) - 1) * pct
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def metrics(rows: list[dict[str, str]]) -> dict:
    routed = [row for row in rows if row["current_router_km"]]
    divergences = [float(row["absolute_divergence_pct"]) for row in routed]
    per_district = defaultdict(list)
    for row in routed:
        per_district[row["district"]].append(float(row["absolute_divergence_pct"]))
    return {
        "routes": len(rows),
        "routable": len(routed),
        "unreachable": len(rows) - len(routed),
        "median": statistics.median(divergences),
        "mean": statistics.fmean(divergences),
        "p90": percentile(divergences, 0.9),
        "gt5": sum(value > 5 for value in divergences),
        "gt10": sum(value > 10 for value in divergences),
        "gt20": sum(value > 20 for value in divergences),
        "suspicious_snap": sum(float(row["snap_distance_m"] or 0) > SNAP_WARNING_M for row in rows),
        "status_counts": dict(Counter(row["router_status"] for row in rows)),
        "districts": {
            district: {
                "routes": len(values),
                "median": statistics.median(values),
                "mean": statistics.fmean(values),
                "gt10": sum(value > 10 for value in values),
            }
            for district, values in sorted(per_district.items())
        },
    }


def write_csv_once(path: Path, rows: list[dict[str, str]]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite evaluator output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_report_once(
    path: Path,
    rows: list[dict[str, str]],
    summary: dict,
    label: str,
    base_url: str,
) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite evaluator report: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Router evaluation — {label}",
        "",
        "Fresh routes from the local OSRM MLD server were compared with the completed",
        "manual Yandex fastest-route measurements. No Yandex request is made here.",
        "",
        "## Execution evidence",
        "",
        f"- OSRM endpoint: `{base_url}`;",
        f"- fixed origin (lon, lat): `{ORIGIN[0]}, {ORIGIN[1]}`;",
        "- request mode: driving, full GeoJSON overview, steps, and OSM node annotations;",
        "- destinations: the exact coordinates in the 86 immutable route controls;",
        "- limitation: the OSRM HTTP response exposes no build identifier, so the checked-in",
        "  profile/build manifests and captured route node sequences are the reproducibility",
        "  evidence. A graph change still requires an independently identified OSM defect.",
        "",
        "## Summary",
        "",
        "| metric | value |",
        "|---|---:|",
        f"| controls | {summary['routes']} |",
        f"| routable | {summary['routable']} |",
        f"| unreachable | {summary['unreachable']} |",
        f"| median divergence | {summary['median']:.1f}% |",
        f"| mean divergence | {summary['mean']:.1f}% |",
        f"| p90 divergence | {summary['p90']:.1f}% |",
        f"| divergence >5% | {summary['gt5']} |",
        f"| divergence >10% | {summary['gt10']} |",
        f"| divergence >20% | {summary['gt20']} |",
        f"| suspicious destination snap >{SNAP_WARNING_M:.0f} m | {summary['suspicious_snap']} |",
        "",
        "## By district",
        "",
        "| district | routes | median | mean | >10% |",
        "|---|---:|---:|---:|---:|",
    ]
    for district, values in summary["districts"].items():
        lines.append(
            f"| {district} | {values['routes']} | {values['median']:.1f}% | "
            f"{values['mean']:.1f}% | {values['gt10']} |"
        )
    lines += [
        "",
        "## Controls requiring attention",
        "",
        "| control | district | Yandex km | router km | divergence | status | probable cause |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    for row in rows:
        if row["owner_review_required"] == "True":
            divergence = row["absolute_divergence_pct"]
            divergence_text = f"{divergence}%" if divergence else "—"
            lines.append(
                f"| {row['control_id']} | {row['district']} | {row['yandex_fastest_km']} | "
                f"{row['current_router_km'] or '—'} | "
                f"{divergence_text} | "
                f"{row['router_status']} | {row['probable_root_cause']} |"
            )
    lines += [
        "",
        "The probable-cause field is triage, not proof of a graph defect. Graph changes",
        "require concrete OSM node/edge evidence and a regression-safe before/after test.",
        "",
        f"Golden measurements SHA-256: `{MEASUREMENTS_SHA256}`.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--output", type=Path, default=REPO / "data/interim/router-baseline-v1.csv")
    parser.add_argument(
        "--report",
        type=Path,
        default=REPO / "reports/router-repair/router-baseline-v1.md",
    )
    parser.add_argument("--label", default="baseline v1")
    args = parser.parse_args()

    discrepancies = load_discrepancy_flags()
    crossings = load_crossings()
    rows = [
        evaluate_one(
            control,
            measurement,
            args.base_url,
            discrepancies.get(control["control_id"], set()),
            crossings,
        )
        for control, measurement in load_controls()
    ]
    summary = metrics(rows)
    write_csv_once(args.output, rows)
    write_report_once(args.report, rows, summary, args.label, args.base_url)
    print(json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
