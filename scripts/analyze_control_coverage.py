#!/usr/bin/env python
"""Analyze full-address anomalies, manual-control coverage and zone-review risk."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.ops import nearest_points

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data/interim"
DOCS = REPO / "docs/data"
REPORTS = REPO / "reports/full-address-routing-audit"
AUDIT = DATA / "all-address-router-audit-v1.csv"
BASELINE = DATA / "router-baseline-v1.csv"
CONTROL_SOURCE = DOCS / "manual-yandex-route-controls.csv"
MEASUREMENTS = DOCS / "manual-yandex-measurements.csv"

COVERAGE_OUTPUT = DATA / "address-control-coverage-v1.csv"
CANDIDATES_OUTPUT = DATA / "additional-manual-route-candidates-v1.csv"
BOUNDARY_OUTPUT = DATA / "provisional-zone-boundary-review-v1.csv"
THRESHOLDS = [2.424, 4.076, 5.577, 9.692]
VALID_COVERAGE = {"STRONG_COVERAGE", "PARTIAL_COVERAGE", "WEAK_COVERAGE", "UNCOVERED"}

COVERAGE_FIELDS = [
    "address_id",
    "best_control_id",
    "coverage_level",
    "coverage_score",
    "shared_corridor",
    "shared_terminal_signature",
    "shared_bridge_or_rail",
    "distance_to_control_m",
    "reason",
    "manual_review_recommended",
]
CANDIDATE_FIELDS = [
    "priority",
    "address_id",
    "territory",
    "street",
    "house_number",
    "destination_lat",
    "destination_lon",
    "router_distance_km",
    "router_duration_min",
    "snap_distance_m",
    "detour_factor",
    "coverage_level",
    "best_control_id",
    "anomaly_reasons",
    "expected_information_gain",
    "recommended_manual_action",
    "owner_review_required",
]
BOUNDARY_FIELDS = [
    "address_id",
    "street",
    "house_number",
    "router_distance_km",
    "nearest_threshold_km",
    "distance_to_threshold_m",
    "provisional_zone",
    "neighbor_zone_discontinuity",
    "snap_risk",
    "manual_review_required",
    "reason",
]


def evaluator_module():
    spec = importlib.util.spec_from_file_location(
        "full_address_evaluator",
        REPO / "scripts/evaluate_all_addresses_against_router.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EVALUATOR = evaluator_module()


def varnita_geometry():
    payload = json.loads(
        (DOCS / "varnita-village-no-delivery.geojson").read_text(encoding="utf-8")
    )
    geometries = [shape(feature["geometry"]) for feature in payload["features"]]
    if len(geometries) != 1:
        from shapely.ops import unary_union

        return unary_union(geometries)
    return geometries[0]


VARNITA_GEOMETRY = varnita_geometry()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def normalized_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")


def split_streets(value: str) -> list[str]:
    return [item.strip() for item in value.split(";") if item.strip()]


def split_nodes(value: str) -> set[str]:
    return set(filter(None, value.split(";")))


def normalize_name(value: str) -> str:
    ignored = {"улица", "ул", "переулок", "пер", "тупик", "проезд"}
    words = [
        "".join(character for character in word.casefold() if character.isalnum())
        for word in value.replace("-", " ").split()
    ]
    return " ".join(word for word in words if word and word not in ignored)


def haversine_m(a_lon: float, a_lat: float, b_lon: float, b_lat: float) -> float:
    return 1000 * EVALUATOR.haversine_km(a_lon, a_lat, b_lon, b_lat)


def control_profiles() -> list[dict]:
    baseline = read_csv(BASELINE)
    coordinates = {row["control_id"]: row for row in read_csv(CONTROL_SOURCE)}
    if len(baseline) != 86 or len(coordinates) != 86:
        raise RuntimeError("coverage requires exactly 86 primary controls")
    result = []
    for row in baseline:
        control = coordinates[row["control_id"]]
        streets = split_streets(row["router_main_streets"])
        crossing = row["bridge_or_rail"]
        result.append(
            {
                "control_id": row["control_id"],
                "district": row["district"],
                "street": control["street"],
                "lat": float(control["destination_lat"]),
                "lon": float(control["destination_lon"]),
                "streets": streets,
                "corridor_signature": EVALUATOR.stable_signature(streets[:5] + [crossing]),
                "terminal_signature": EVALUATOR.stable_signature(streets[-2:]),
                "last_nodes": set(row["route_node_ids"].split(";")[-8:]),
                "bridge": crossing,
            }
        )
    return result


def score_coverage(address: dict[str, str], control: dict) -> tuple[float, dict]:
    distance_m = haversine_m(
        float(address["destination_lon"]),
        float(address["destination_lat"]),
        control["lon"],
        control["lat"],
    )
    streets = split_streets(address["router_main_streets"])
    address_street_names = {normalize_name(item) for item in streets}
    control_street_names = {normalize_name(item) for item in control["streets"]}
    address_tail = split_nodes(address["route_last_nodes"])
    union = address_tail | control["last_nodes"]
    tail_overlap = len(address_tail & control["last_nodes"]) / len(union) if union else 0
    street_union = address_street_names | control_street_names
    street_overlap = (
        len(address_street_names & control_street_names) / len(street_union)
        if street_union
        else 0
    )
    shared_corridor = address["corridor_signature"] == control["corridor_signature"]
    shared_terminal = (
        address["terminal_node_signature"] == control["terminal_signature"]
        or tail_overlap >= 0.4
    )
    shared_bridge = address["bridge_or_rail"] == control["bridge"]
    same_street = normalize_name(address["street"]) == normalize_name(control["street"])
    score = 0.0
    score += 0.35 if shared_corridor else 0
    score += 0.25 if address["terminal_node_signature"] == control["terminal_signature"] else 0
    score += 0.15 if tail_overlap >= 0.4 else 0
    score += 0.10 if shared_bridge else 0
    score += 0.15 if same_street else 0
    score += 0.10 * street_overlap
    proximity_score = (
        0.05
        if distance_m <= 250
        else 0.03
        if distance_m <= 750
        else 0.01
        if distance_m <= 2000
        else 0
    )
    score += proximity_score
    evidence = {
        "distance_m": distance_m,
        "shared_corridor": shared_corridor,
        "shared_terminal": shared_terminal,
        "shared_bridge": shared_bridge,
        "same_street": same_street,
        "tail_overlap": tail_overlap,
        "street_overlap": street_overlap,
    }
    return min(score, 1.0), evidence


def coverage_level(score: float, evidence: dict) -> str:
    if (
        evidence["shared_corridor"]
        and evidence["shared_terminal"]
        and (evidence["same_street"] or evidence["distance_m"] <= 500)
    ):
        return "STRONG_COVERAGE"
    if evidence["shared_corridor"] and (
        evidence["shared_terminal"] or evidence["same_street"]
    ):
        return "PARTIAL_COVERAGE"
    if score >= 0.20 and (
        evidence["street_overlap"] > 0 or evidence["shared_bridge"]
    ):
        return "WEAK_COVERAGE"
    return "UNCOVERED"


def build_coverage(audit: list[dict[str, str]], controls: list[dict]) -> list[dict[str, str]]:
    output = []
    for address in audit:
        if address["router_status"] != "ROUTABLE":
            output.append(
                {
                    "address_id": address["address_id"],
                    "best_control_id": "",
                    "coverage_level": "UNCOVERED",
                    "coverage_score": "0.000",
                    "shared_corridor": "False",
                    "shared_terminal_signature": "False",
                    "shared_bridge_or_rail": "False",
                    "distance_to_control_m": "",
                    "reason": f"router_status={address['router_status']}",
                    "manual_review_recommended": "True",
                }
            )
            continue
        scored = []
        for control in controls:
            score, evidence = score_coverage(address, control)
            scored.append((score, -evidence["distance_m"], control, evidence))
        score, _, control, evidence = max(scored, key=lambda item: (item[0], item[1]))
        level = coverage_level(score, evidence)
        reasons = [
            f"corridor={evidence['shared_corridor']}",
            f"terminal={evidence['shared_terminal']}",
            f"same_street={evidence['same_street']}",
            f"tail_overlap={evidence['tail_overlap']:.2f}",
            f"street_overlap={evidence['street_overlap']:.2f}",
        ]
        output.append(
            {
                "address_id": address["address_id"],
                "best_control_id": control["control_id"],
                "coverage_level": level,
                "coverage_score": f"{score:.3f}",
                "shared_corridor": str(evidence["shared_corridor"]),
                "shared_terminal_signature": str(evidence["shared_terminal"]),
                "shared_bridge_or_rail": str(evidence["shared_bridge"]),
                "distance_to_control_m": f"{evidence['distance_m']:.1f}",
                "reason": "; ".join(reasons),
                "manual_review_recommended": str(level != "STRONG_COVERAGE"),
            }
        )
    return output


def anomaly_set(row: dict[str, str]) -> set[str]:
    return set(filter(None, row["probable_anomaly"].replace("NONE", "").split(";")))


def candidate_priority(
    audit: dict[str, str], coverage: dict[str, str], corridor_count: Counter
) -> tuple[str | None, list[str]]:
    anomalies = anomaly_set(audit)
    reasons = set(anomalies)
    status = audit["router_status"]
    snap = float(audit["destination_snap_distance_m"] or 0)
    critical = status != "ROUTABLE" or snap > 100
    critical |= (
        coverage["coverage_level"] == "UNCOVERED"
        and corridor_count[audit["corridor_signature"]] == 1
    )
    critical |= bool(
        anomalies
        & {
            "SETTLEMENT_DISAGREEMENT",
            "ADDRESS_ANCHOR_DISAGREEMENT",
        }
    )
    point = Point(
        float(audit["destination_lon"]), float(audit["destination_lat"])
    )
    if VARNITA_GEOMETRY.contains(point):
        varnita_distance_m = 0.0
    else:
        nearest = nearest_points(point, VARNITA_GEOMETRY)[1]
        varnita_distance_m = haversine_m(point.x, point.y, nearest.x, nearest.y)
    if varnita_distance_m <= 100:
        critical = True
        reasons.add("ADDRESS_WITHIN_100M_OF_EXCLUDED_VARNITA")
    if status != "ROUTABLE":
        reasons.add(status)
    if coverage["coverage_level"] == "UNCOVERED":
        reasons.add("UNCOVERED")
    if critical:
        return "CRITICAL", sorted(reasons)
    distance = float(audit["router_distance_km"] or 0)
    near_boundary = status == "ROUTABLE" and any(
        abs(distance - threshold) / threshold <= 0.03 for threshold in THRESHOLDS
    )
    if coverage["coverage_level"] == "WEAK_COVERAGE" and near_boundary:
        reasons.add("WEAK_COVERAGE_NEAR_THRESHOLD")
    high = snap > 60 or coverage["coverage_level"] == "UNCOVERED"
    high |= coverage["coverage_level"] == "WEAK_COVERAGE" and near_boundary
    high |= bool(
        anomalies
        & {
            "STREET_DISTANCE_CONTINUITY_OUTLIER",
            "STREET_DURATION_CONTINUITY_OUTLIER",
            "ROBUST_HIGH_DETOUR_FACTOR",
            "UTURN",
            "HOUSE_NUMBER_DISAGREEMENT",
            "STREET_NAME_VARIANT",
            "LOCAL_CORRIDOR_DISCONTINUITY",
        }
    )
    if high:
        return "HIGH", sorted(reasons | {coverage["coverage_level"]})
    if coverage["coverage_level"] == "PARTIAL_COVERAGE" or anomalies:
        return "MEDIUM", sorted(reasons | {coverage["coverage_level"]})
    return None, []


def candidate_cluster(address: dict[str, str], reasons: list[str]) -> tuple:
    anomaly_family = next(
        (
            family
            for family in (
                "ROUTER",
                "SNAP",
                "CONTINUITY",
                "DETOUR",
                "CORRIDOR",
                "ADDRESS",
                "COVERAGE",
            )
            if any(family in reason for reason in reasons)
        ),
        "OTHER",
    )
    if anomaly_family == "CONTINUITY":
        return (
            anomaly_family,
            address["territory"],
            normalize_name(address["street"]),
            address["corridor_signature"],
        )
    if anomaly_family in {"SNAP", "ADDRESS"}:
        return (
            anomaly_family,
            address["territory"],
            normalize_name(address["street"]),
            round(float(address["destination_lat"]) / 0.005),
            round(float(address["destination_lon"]) / 0.005),
        )
    return (
        anomaly_family,
        address["corridor_signature"],
        address["terminal_node_signature"],
    )


def build_candidates(
    audit: list[dict[str, str]], coverage_rows: list[dict[str, str]]
) -> tuple[list[dict[str, str]], set[str], set[str]]:
    coverage = {row["address_id"]: row for row in coverage_rows}
    corridor_count = Counter(row["corridor_signature"] for row in audit)
    pool: dict[tuple, list[tuple[dict[str, str], str, list[str]]]] = defaultdict(list)
    critical_ids = set()
    for address in audit:
        priority, reasons = candidate_priority(
            address, coverage[address["address_id"]], corridor_count
        )
        if priority is None:
            continue
        pool[candidate_cluster(address, reasons)].append((address, priority, reasons))
        if priority == "CRITICAL":
            critical_ids.add(address["address_id"])

    priority_rank = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1}
    minimal_ids = set(critical_ids)
    extended_ids = set(critical_ids)
    selected: dict[str, tuple[dict[str, str], str, list[str]]] = {}
    for cluster in pool.values():
        ordered = sorted(
            cluster,
            key=lambda item: (
                -priority_rank[item[1]],
                -float(item[0]["destination_snap_distance_m"] or 0),
                -len(item[2]),
                item[0]["address_id"],
            ),
        )
        representative = ordered[0]
        minimal_ids.add(representative[0]["address_id"])
        selected[representative[0]["address_id"]] = representative
        spatial = sorted(
            cluster,
            key=lambda item: (
                float(item[0]["destination_lat"]),
                float(item[0]["destination_lon"]),
                item[0]["address_id"],
            ),
        )
        indices = {0, len(spatial) // 2, len(spatial) - 1}
        for index in indices:
            item = spatial[index]
            extended_ids.add(item[0]["address_id"])
            selected[item[0]["address_id"]] = item
        extended_ids.add(representative[0]["address_id"])

    rows = []
    for address_id in sorted(extended_ids | minimal_ids):
        address, priority, reasons = selected.get(address_id) or next(
            item
            for cluster in pool.values()
            for item in cluster
            if item[0]["address_id"] == address_id
        )
        cov = coverage[address_id]
        minimal = address_id in minimal_ids
        rows.append(
            {
                "priority": priority,
                "address_id": address_id,
                "territory": address["territory"],
                "street": address["street"],
                "house_number": address["house_number"],
                "destination_lat": address["destination_lat"],
                "destination_lon": address["destination_lon"],
                "router_distance_km": address["router_distance_km"],
                "router_duration_min": address["router_duration_min"],
                "snap_distance_m": address["destination_snap_distance_m"],
                "detour_factor": address["detour_factor"],
                "coverage_level": cov["coverage_level"],
                "best_control_id": cov["best_control_id"],
                "anomaly_reasons": ";".join(reasons),
                "expected_information_gain": (
                    "tests an unresolved failure or unique network branch"
                    if priority == "CRITICAL"
                    else "tests a high-risk anomaly cluster"
                    if priority == "HIGH"
                    else "extends a partially covered local branch"
                ),
                "recommended_manual_action": (
                    "MINIMAL_SET: inspect one route visually and record exact corridor/snap"
                    if minimal
                    else "EXTENDED_SET: inspect for higher confidence across the cluster"
                ),
                "owner_review_required": "True",
            }
        )
    return rows, minimal_ids, extended_ids | minimal_ids


def provisional_zone(distance: float) -> str:
    for index, threshold in enumerate(THRESHOLDS, start=1):
        if distance <= threshold:
            return f"Zone {index}"
    return "ABOVE_ZONE_4"


def nearest_same_street(
    row: dict[str, str], group: list[dict[str, str]], count: int = 4
) -> list[dict[str, str]]:
    candidates = []
    for other in group:
        if other["address_id"] == row["address_id"]:
            continue
        distance = haversine_m(
            float(row["destination_lon"]),
            float(row["destination_lat"]),
            float(other["destination_lon"]),
            float(other["destination_lat"]),
        )
        candidates.append((distance, other))
    return [item for _, item in sorted(candidates, key=lambda item: item[0])[:count]]


def build_boundary_review(audit: list[dict[str, str]]) -> list[dict[str, str]]:
    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in audit:
        if row["router_status"] == "ROUTABLE":
            groups[(row["territory"], row["district"], row["street"])].append(row)
    rows = []
    for group in groups.values():
        for address in group:
            distance = float(address["router_distance_km"])
            threshold = min(THRESHOLDS, key=lambda value: abs(distance - value))
            difference_m = abs(distance - threshold) * 1000
            neighbors = nearest_same_street(address, group)
            zone = provisional_zone(distance)
            neighbor_discontinuity = any(
                provisional_zone(float(item["router_distance_km"])) != zone
                for item in neighbors
            )
            snap = float(address["destination_snap_distance_m"] or 0)
            snap_risk = snap > 30 and snap >= difference_m
            near = difference_m <= 100 or difference_m / (threshold * 1000) <= 0.03
            if not (near or neighbor_discontinuity or snap_risk):
                continue
            reasons = []
            if difference_m <= 50:
                reasons.append("WITHIN_50M_OF_THRESHOLD")
            elif difference_m <= 100:
                reasons.append("WITHIN_100M_OF_THRESHOLD")
            if difference_m / (threshold * 1000) <= 0.03:
                reasons.append("WITHIN_3_PERCENT_OF_THRESHOLD")
            if neighbor_discontinuity:
                reasons.append("NEIGHBOR_ZONE_DISCONTINUITY")
            if snap_risk:
                reasons.append("SNAP_CAN_CROSS_THRESHOLD")
            rows.append(
                {
                    "address_id": address["address_id"],
                    "street": address["street"],
                    "house_number": address["house_number"],
                    "router_distance_km": address["router_distance_km"],
                    "nearest_threshold_km": f"{threshold:.3f}",
                    "distance_to_threshold_m": f"{difference_m:.1f}",
                    "provisional_zone": zone,
                    "neighbor_zone_discontinuity": str(neighbor_discontinuity),
                    "snap_risk": str(snap_risk),
                    "manual_review_required": "True",
                    "reason": ";".join(reasons),
                }
            )
    return sorted(rows, key=lambda row: row["address_id"])


def numeric_summary(values: list[float]) -> tuple[float, float, float]:
    return (
        statistics.median(values),
        statistics.fmean(values),
        EVALUATOR.percentile(values, 0.9),
    )


def report_tables(
    audit: list[dict[str, str]],
    coverage: list[dict[str, str]],
    candidates: list[dict[str, str]],
    minimal_ids: set[str],
    extended_ids: set[str],
    boundary: list[dict[str, str]],
) -> dict[str, str]:
    statuses = Counter(row["router_status"] for row in audit)
    levels = Counter(row["coverage_level"] for row in coverage)
    anomalies = Counter(
        anomaly for row in audit for anomaly in anomaly_set(row)
    )
    severity = Counter(row["anomaly_severity"] for row in audit)
    routable = [row for row in audit if row["router_status"] == "ROUTABLE"]
    distances = [float(row["router_distance_km"]) for row in routable]
    snaps = [float(row["destination_snap_distance_m"]) for row in routable]
    median_distance, mean_distance, p90_distance = numeric_summary(distances)
    median_snap, _, p90_snap = numeric_summary(snaps)
    continuity = sum(
        any("CONTINUITY" in anomaly for anomaly in anomaly_set(row)) for row in audit
    )
    high_detour = sum(
        "ROBUST_HIGH_DETOUR_FACTOR" in anomaly_set(row) for row in audit
    )
    known_discrepancy_flags = {
        "STREET_NAME_VARIANT",
        "HOUSE_NUMBER_DISAGREEMENT",
        "ADDRESS_ANCHOR_DISAGREEMENT",
        "SETTLEMENT_DISAGREEMENT",
    }
    discrepancy_addresses = sum(
        bool(anomaly_set(row) & known_discrepancy_flags) for row in audit
    )
    discrepancy_source_rows = len(read_csv(DOCS / "manual-yandex-address-discrepancies.csv"))
    corridor_count = len({row["corridor_signature"] for row in routable})
    terminal_count = len({row["terminal_node_signature"] for row in routable})
    critical_open = statuses["UNREACHABLE"] + statuses["ROUTER_ERROR"] + statuses[
        "INVALID_COORDINATES"
    ]
    critical_open += sum(float(row["destination_snap_distance_m"] or 0) > 100 for row in routable)
    decision = (
        "NO_GO"
        if statuses["UNREACHABLE"]
        or statuses["ROUTER_ERROR"]
        or statuses["INVALID_COORDINATES"]
        else "GO_WITH_REVIEW"
        if critical_open or levels["UNCOVERED"] or continuity
        else "GO"
    )
    territory_anomalies = Counter(
        row["territory"] for row in audit if anomaly_set(row)
    )
    street_anomalies = Counter(
        f"{row['territory']} / {row['street']}" for row in audit if anomaly_set(row)
    )
    distance_summary = f"{median_distance:.3f} / {mean_distance:.3f} / {p90_distance:.3f} km"
    snap_threshold_summary = (
        f"{sum(v > 30 for v in snaps)} / {sum(v > 60 for v in snaps)} / "
        f"{sum(v > 100 for v in snaps)}"
    )
    coverage_summary = (
        f"{levels['STRONG_COVERAGE']} | {levels['PARTIAL_COVERAGE']} | "
        f"{levels['WEAK_COVERAGE']} | {levels['UNCOVERED']}"
    )
    discrepancy_summary = f"{discrepancy_source_rows} / {discrepancy_addresses}"
    source = (
        f"Canonical registry: `releases/bender-zones-v1.1/address-registry.json` "
        f"(normalized SHA-256 `{EVALUATOR.REGISTRY_SHA256}`); coordinate join: "
        f"`docs/data/delivery-units.csv` (normalized SHA-256 "
        f"`{EVALUATOR.COORDINATES_SHA256}`)."
    )

    summary = f"""# Full address routing audit v1

{source}

Grain: one immutable v1.1 delivery address (`address_id = uid`). The audit uses
fresh local OSRM routes from `{EVALUATOR.DEFAULT_BASE_URL}` and never calls Yandex.

## Source reconciliation

| stage | objects |
|---|---:|
| full catalog before eligibility/exclusions | 23,229 |
| eligible verified rows before canonical dedupe | 9,777 |
| canonical duplicate rows removed | 561 |
| immutable working registry after dedupe | 9,216 |
| admin QA objects outside the working registry | 14,013 |

## Routing summary

| metric | value |
|---|---:|
| addresses | {len(audit)} |
| routable | {statuses['ROUTABLE']} |
| unreachable | {statuses['UNREACHABLE']} |
| router errors | {statuses['ROUTER_ERROR']} |
| invalid coordinates | {statuses['INVALID_COORDINATES']} |
| median / mean / p90 distance | {distance_summary} |
| median / p90 destination snap | {median_snap:.1f} / {p90_snap:.1f} m |
| snap >30 / >60 / >100 m | {snap_threshold_summary} |
| continuity outliers | {continuity} |
| robust high detour factors | {high_detour} |
| known discrepancy rows / matched canonical addresses | {discrepancy_summary} |
| unique corridor signatures | {corridor_count} |
| unique terminal branch signatures | {terminal_count} |
| provisional-boundary review addresses | {len(boundary)} |

## Manual-control coverage

| STRONG | PARTIAL | WEAK | UNCOVERED |
|---:|---:|---:|---:|
| {coverage_summary} |

The 86 controls are not treated as sufficient merely because they share a
district. Strong coverage requires a matching corridor plus terminal evidence
and street/branch proximity.

## Additional manual review

- minimum representative set: **{len(minimal_ids)}** routes;
- expanded confidence set: **{len(extended_ids)}** routes;
- candidate CSV rows: **{len(candidates)}**.

## Decision

**{decision}** for zone recalculation analysis. This does not authorize a zone
release. Zones, thresholds and assignments were not changed.
"""

    anomaly_lines = [
        "# Full address routing anomalies v1",
        "",
        source,
        "",
        "## Severity",
        "",
        "| severity | addresses |",
        "|---|---:|",
    ]
    anomaly_lines.extend(f"| {key} | {value} |" for key, value in sorted(severity.items()))
    anomaly_lines += ["", "## Anomaly classes", "", "| anomaly | addresses |", "|---|---:|"]
    anomaly_lines.extend(
        f"| {key} | {value} |" for key, value in anomalies.most_common()
    )
    anomaly_lines += ["", "## Territories", "", "| territory | anomaly addresses |", "|---|---:|"]
    anomaly_lines.extend(
        f"| {key} | {value} |" for key, value in territory_anomalies.most_common()
    )
    anomaly_lines += [
        "",
        "## Top streets",
        "",
        "| territory / street | anomaly addresses |",
        "|---|---:|",
    ]
    anomaly_lines.extend(
        f"| {key} | {value} |" for key, value in street_anomalies.most_common(30)
    )
    anomaly_lines += [
        "",
        "High detour and corridor changes are triage signals, not automatic graph",
        "errors: rivers, railways, bridges and legal network separation can explain them.",
    ]

    coverage_lines = [
        "# Manual-control coverage v1",
        "",
        source,
        "",
        "## Coverage levels",
        "",
        "| level | addresses | share |",
        "|---|---:|---:|",
    ]
    for level in ("STRONG_COVERAGE", "PARTIAL_COVERAGE", "WEAK_COVERAGE", "UNCOVERED"):
        coverage_lines.append(
            f"| {level} | {levels[level]} | {100 * levels[level] / len(coverage):.1f}% |"
        )
    territory_levels: dict[str, Counter] = defaultdict(Counter)
    street_levels: dict[str, Counter] = defaultdict(Counter)
    corridor_levels: dict[str, Counter] = defaultdict(Counter)
    audit_by_id = {row["address_id"]: row for row in audit}
    for row in coverage:
        address = audit_by_id[row["address_id"]]
        territory_levels[address["territory"]][row["coverage_level"]] += 1
        street_levels[f"{address['territory']} / {address['street']}"][row["coverage_level"]] += 1
        corridor_levels[address["corridor_signature"]][row["coverage_level"]] += 1
    coverage_lines += [
        "",
        "## By territory",
        "",
        "| territory | strong | partial | weak | uncovered |",
        "|---|---:|---:|---:|---:|",
    ]
    for territory, counts in sorted(territory_levels.items()):
        coverage_lines.append(
            f"| {territory} | {counts['STRONG_COVERAGE']} | "
            f"{counts['PARTIAL_COVERAGE']} | {counts['WEAK_COVERAGE']} | "
            f"{counts['UNCOVERED']} |"
        )
    coverage_lines += [
        "",
        "## Highest-risk streets",
        "",
        "| territory / street | strong | partial | weak | uncovered |",
        "|---|---:|---:|---:|---:|",
    ]
    risky_streets = sorted(
        street_levels.items(),
        key=lambda item: (
            -item[1]["UNCOVERED"],
            -item[1]["WEAK_COVERAGE"],
            item[0],
        ),
    )[:30]
    for street, counts in risky_streets:
        coverage_lines.append(
            f"| {street} | {counts['STRONG_COVERAGE']} | "
            f"{counts['PARTIAL_COVERAGE']} | {counts['WEAK_COVERAGE']} | "
            f"{counts['UNCOVERED']} |"
        )
    coverage_lines += [
        "",
        "## Highest-risk corridor signatures",
        "",
        "| corridor signature | strong | partial | weak | uncovered |",
        "|---|---:|---:|---:|---:|",
    ]
    risky_corridors = sorted(
        corridor_levels.items(),
        key=lambda item: (
            -item[1]["UNCOVERED"],
            -item[1]["WEAK_COVERAGE"],
            item[0],
        ),
    )[:30]
    for corridor, counts in risky_corridors:
        coverage_lines.append(
            f"| `{corridor}` | {counts['STRONG_COVERAGE']} | "
            f"{counts['PARTIAL_COVERAGE']} | {counts['WEAK_COVERAGE']} | "
            f"{counts['UNCOVERED']} |"
        )
    uncovered_corridors = Counter(
        audit_by_id[row["address_id"]]["corridor_signature"]
        for row in coverage
        if row["coverage_level"] == "UNCOVERED"
    )
    uncovered_terminals = Counter(
        audit_by_id[row["address_id"]]["terminal_node_signature"]
        for row in coverage
        if row["coverage_level"] == "UNCOVERED"
    )
    coverage_lines += [
        "",
        f"Unique uncovered corridor signatures: **{len(uncovered_corridors)}**.",
        f"Unique uncovered terminal branches: **{len(uncovered_terminals)}**.",
        "",
        "Top uncovered terminal signatures: "
        + ", ".join(
            f"`{signature}` ({count})"
            for signature, count in uncovered_terminals.most_common(20)
        )
        + ".",
        "",
        "District equality contributes no score. The exact scoring evidence is retained",
        "per address in `data/interim/address-control-coverage-v1.csv`.",
    ]

    candidate_counts = Counter(row["priority"] for row in candidates)
    varnita_near = sum(
        "ADDRESS_WITHIN_100M_OF_EXCLUDED_VARNITA" in row["anomaly_reasons"]
        for row in candidates
    )
    manual = f"""# Additional manual route plan v1

{source}

Candidates are clustered by territory, normalized street, corridor, anomaly
family and geographic cell. Every CRITICAL row survives deduplication; other
clusters retain beginning, midpoint, endpoint and worst representative where
distinct.

| priority | selected addresses |
|---|---:|
| CRITICAL | {candidate_counts['CRITICAL']} |
| HIGH | {candidate_counts['HIGH']} |
| MEDIUM | {candidate_counts['MEDIUM']} |

Canonical addresses within 100 m of excluded Varnița: **{varnita_near}**.

- minimum necessary representative set: **{len(minimal_ids)}**;
- expanded higher-confidence set: **{len(extended_ids)}**.

Each selected address and its reason are recorded in
`data/interim/additional-manual-route-candidates-v1.csv`. These are proposals;
no new Yandex measurement was made.
"""

    boundary_reasons = Counter(
        reason for row in boundary for reason in row["reason"].split(";") if reason
    )
    boundary_report = [
        "# Provisional zone boundary review v1",
        "",
        "The existing thresholds are used only for review. No zone assignment,",
        "polygon, release or threshold was changed.",
        "",
        f"Addresses requiring boundary review: **{len(boundary)}**.",
        "",
        "| reason | addresses |",
        "|---|---:|",
    ]
    boundary_report.extend(
        f"| {key} | {value} |" for key, value in boundary_reasons.most_common()
    )

    return {
        "all-address-summary-v1.md": summary,
        "anomalies-v1.md": "\n".join(anomaly_lines),
        "control-coverage-v1.md": "\n".join(coverage_lines),
        "manual-review-plan-v1.md": manual,
        "provisional-zone-boundary-review-v1.md": "\n".join(boundary_report),
    }


def ensure_outputs_absent(overwrite: bool) -> None:
    outputs = [
        COVERAGE_OUTPUT,
        CANDIDATES_OUTPUT,
        BOUNDARY_OUTPUT,
        *(REPORTS / name for name in (
            "all-address-summary-v1.md",
            "anomalies-v1.md",
            "control-coverage-v1.md",
            "manual-review-plan-v1.md",
            "provisional-zone-boundary-review-v1.md",
        )),
    ]
    existing = [path for path in outputs if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(f"analysis outputs exist; use --overwrite: {existing}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    ensure_outputs_absent(args.overwrite)
    audit = read_csv(AUDIT)
    if len(audit) != EVALUATOR.EXPECTED_ADDRESSES:
        raise RuntimeError("full audit is incomplete")
    if len({row["address_id"] for row in audit}) != len(audit):
        raise RuntimeError("duplicate address_id in full audit")
    coverage = build_coverage(audit, control_profiles())
    candidates, minimal_ids, extended_ids = build_candidates(audit, coverage)
    boundary = build_boundary_review(audit)
    reports = report_tables(
        audit, coverage, candidates, minimal_ids, extended_ids, boundary
    )
    write_csv(COVERAGE_OUTPUT, COVERAGE_FIELDS, coverage)
    write_csv(CANDIDATES_OUTPUT, CANDIDATE_FIELDS, candidates)
    write_csv(BOUNDARY_OUTPUT, BOUNDARY_FIELDS, boundary)
    for name, text in reports.items():
        write_text(REPORTS / name, text)
    print(
        json.dumps(
            {
                "coverage": Counter(row["coverage_level"] for row in coverage),
                "minimal_manual_set": len(minimal_ids),
                "expanded_manual_set": len(extended_ids),
                "boundary_review": len(boundary),
            },
            ensure_ascii=True,
            indent=2,
            default=dict,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
