"""Build the immutable-base classification and deterministic Yandex audit sample.

This script does not call Yandex.  It only prepares a review population and a
reproducible sample.  Browser observations are recorded separately and must
never be inferred from OSM or routing data.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "releases/bender-zones-v1.1/address-registry.json"
DELIVERY_UNITS = ROOT / "docs/data/delivery-units.csv"
DISCREPANCIES = ROOT / "docs/data/manual-yandex-address-discrepancies.csv"
ROUTE_CONTROLS = ROOT / "docs/data/manual-yandex-route-controls.csv"
ROUTING_AUDIT = ROOT / "docs/data/stage-09a-routing-audit.csv"
VARNITA = ROOT / "docs/data/varnita-village-no-delivery.geojson"
CLASSIFICATION = ROOT / "data/interim/canonical-deliverable-address-classification-v1.csv"
SAMPLE = ROOT / "data/interim/yandex-address-validation-sample-v1.csv"

CLASSIFICATION_FIELDS = [
    "address_id",
    "territory",
    "street",
    "house_number",
    "lat",
    "lon",
    "source_object_type",
    "normalized_object_type",
    "deliverable_address_status",
    "exclusion_reason",
    "manual_review_required",
]
SAMPLE_FIELDS = [
    "sample_id",
    "address_id",
    "territory",
    "street",
    "house_number",
    "lat",
    "lon",
    "deliverable_address_status",
    "selection_stratum",
    "selection_reason",
    "sampling_weight",
    "mandatory_check",
]
SEED = 20260726
MINIMUM_SAMPLE_SIZE = 1000
NON_DELIVERABLE_TYPES = {
    "garage",
    "garages",
    "garage_box",
    "shed",
    "barn",
    "outbuilding",
    "farm_auxiliary",
    "greenhouse",
    "carport",
    "collapsed",
    "ruins",
    "demolished",
    "construction",
    "technical_building",
    "transformer_house",
}


def normalized_sha256(path: Path) -> str:
    """Return the repository-style SHA-256 after normalizing line endings."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def street_bucket(count: int) -> str:
    if count <= 5:
        return "SHORT_1_5"
    if count <= 20:
        return "MEDIUM_6_20"
    return "LONG_21_PLUS"


def address_grain_key(territory: str, street: str, house_number: str) -> tuple[str, str, str]:
    """Return the audit grain; apartment, POI and organization are intentionally absent."""
    return territory.casefold().strip(), street.casefold().strip(), house_number.casefold().strip()


def classify_source_object_type(source_type: str) -> tuple[str, str, str, str]:
    """Map retained or future detailed types without treating uncertainty as deliverable."""
    normalized = source_type.casefold().strip().replace(" ", "_")
    if normalized == "addressed_residential_building":
        return "RESIDENTIAL_BUILDING", "DELIVERABLE", "", "False"
    if normalized in NON_DELIVERABLE_TYPES:
        return (
            normalized.upper(),
            "NON_DELIVERABLE_STRUCTURE",
            f"non_deliverable_structure:{normalized}",
            "False",
        )
    if normalized == "standalone_address_node":
        return (
            "ADDRESS_NODE_WITHOUT_BUILDING_TYPE",
            "UNKNOWN_REQUIRES_REVIEW",
            "source_does_not_identify_a_building",
            "True",
        )
    return (
        "UNMAPPED_SOURCE_OBJECT_TYPE",
        "UNKNOWN_REQUIRES_REVIEW",
        "unmapped_source_object_type",
        "True",
    )


def _dominant_axis_sort(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    lat_span = max(float(row["lat"]) for row in rows) - min(float(row["lat"]) for row in rows)
    lon_span = max(float(row["lon"]) for row in rows) - min(float(row["lon"]) for row in rows)
    primary, secondary = ("lat", "lon") if lat_span >= lon_span else ("lon", "lat")
    return sorted(
        rows,
        key=lambda row: (float(row[primary]), float(row[secondary]), row["address_id"]),
    )


def _position_indices(length: int) -> list[tuple[int, str]]:
    candidates = [
        (0, "STREET_START"),
        (round((length - 1) * 0.25), "STREET_25_PERCENT"),
        (round((length - 1) * 0.50), "STREET_MIDDLE"),
        (round((length - 1) * 0.75), "STREET_75_PERCENT"),
        (length - 1, "STREET_END"),
    ]
    seen: set[int] = set()
    return [(index, label) for index, label in candidates if not (index in seen or seen.add(index))]


def _varnita_geometry():
    payload = json.loads(VARNITA.read_text(encoding="utf-8"))
    features = payload.get("features", [])
    return unary_union([shape(feature["geometry"]) for feature in features])


def build_classification() -> tuple[list[dict[str, str]], dict[str, dict[str, object]]]:
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    addresses = payload["addresses"]
    units = {row["uid"]: row for row in read_csv(DELIVERY_UNITS)}
    if len(addresses) != 9216:
        raise ValueError(f"Expected 9216 canonical addresses, found {len(addresses)}")
    if len({row["uid"] for row in addresses}) != len(addresses):
        raise ValueError("Canonical address IDs are not unique")

    rows: list[dict[str, str]] = []
    metadata: dict[str, dict[str, object]] = {}
    for address in addresses:
        uid = address["uid"]
        unit = units.get(uid)
        if unit is None or not unit["lat"] or not unit["lon"]:
            raise ValueError(f"Missing protected coordinates for {uid}")
        source_type = unit["unit_type"]
        normalized_type, status, exclusion_reason, review = classify_source_object_type(source_type)
        row = {
            "address_id": uid,
            "territory": address["settlement_ru"],
            "street": address["street_ru"],
            "house_number": address["housenumber"],
            "lat": unit["lat"],
            "lon": unit["lon"],
            "source_object_type": source_type,
            "normalized_object_type": normalized_type,
            "deliverable_address_status": status,
            "exclusion_reason": exclusion_reason,
            "manual_review_required": review,
        }
        rows.append(row)
        metadata[uid] = {
            "district": address.get("district_ru") or "",
            "requires_varnita_transit": bool(address["route_flags"]["requires_varnita_transit"]),
        }
    rows.sort(key=lambda row: row["address_id"])
    return rows, metadata


def _anomaly_scores() -> dict[str, float]:
    scores: dict[str, float] = {}
    for row in read_csv(ROUTING_AUDIT):
        snap = float(row["snap_distance_m"] or 0)
        detour = float(row["detour_ratio"] or 0)
        flag_bonus = 100.0 if row["flags"] else 0.0
        scores[row["uid"]] = snap + 20.0 * max(detour - 1.0, 0.0) + flag_bonus
    return scores


def _snap_distances() -> dict[str, float]:
    return {
        row["uid"]: float(row["snap_distance_m"] or 0)
        for row in read_csv(ROUTING_AUDIT)
    }


def _mandatory_discrepancy_mapping(
    population: list[dict[str, str]],
) -> dict[str, list[str]]:
    controls = {row["control_id"]: row for row in read_csv(ROUTE_CONTROLS)}
    by_id = {row["address_id"]: row for row in population}
    reasons: dict[str, list[str]] = defaultdict(list)
    for discrepancy in read_csv(DISCREPANCIES):
        control_id = discrepancy["control_id"]
        uid = controls.get(control_id, {}).get("uid", "")
        if uid not in by_id:
            target_lat = float(discrepancy["destination_lat"])
            target_lon = float(discrepancy["destination_lon"])
            uid = min(
                population,
                key=lambda row: (float(row["lat"]) - target_lat) ** 2
                + (float(row["lon"]) - target_lon) ** 2,
            )["address_id"]
            reason = f"KNOWN_DISCREPANCY_PROXY:{control_id}"
        else:
            reason = f"KNOWN_DISCREPANCY:{control_id}"
        reasons[uid].append(reason)
    return reasons


def build_sample(
    population: list[dict[str, str]], metadata: dict[str, dict[str, object]]
) -> list[dict[str, object]]:
    by_id = {row["address_id"]: row for row in population}
    street_groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in population:
        district = str(metadata[row["address_id"]]["district"])
        street_groups[(row["territory"], district, row["street"])].append(row)

    reasons: dict[str, set[str]] = defaultdict(set)
    anomaly_scores = _anomaly_scores()
    snap_distances = _snap_distances()
    for street_rows in street_groups.values():
        ordered = _dominant_axis_sort(street_rows)
        if len(ordered) <= 5:
            for row in ordered:
                reasons[row["address_id"]].add("SHORT_STREET_FULL")
        else:
            for index, label in _position_indices(len(ordered)):
                reasons[ordered[index]["address_id"]].add(label)
            anomalous = max(
                ordered,
                key=lambda row: (anomaly_scores.get(row["address_id"], -1.0), row["address_id"]),
            )
            reasons[anomalous["address_id"]].add("MOST_ANOMALOUS_ON_STREET")

    for row in population:
        uid = row["address_id"]
        if row["deliverable_address_status"] == "UNKNOWN_REQUIRES_REVIEW":
            reasons[uid].add("UNKNOWN_REQUIRES_REVIEW")
        house = row["house_number"]
        if re.search(r"[A-Za-zА-Яа-я]", house):
            reasons[uid].add("LETTERED_HOUSE_NUMBER")
        if "/" in house or "-" in house:
            reasons[uid].add("FRACTIONAL_HOUSE_NUMBER")
        if snap_distances.get(uid, 0.0) >= 40.0:
            reasons[uid].add("BAD_SNAP_40M_PLUS")
        if metadata[uid]["requires_varnita_transit"]:
            reasons[uid].add("VARNITA_TRANSIT_FLAG")

    by_territory: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in population:
        by_territory[row["territory"]].append(row)
    for territory_rows in by_territory.values():
        extrema = [
            (
                min(territory_rows, key=lambda row: (float(row["lat"]), row["address_id"])),
                "LAT_MIN",
            ),
            (
                max(territory_rows, key=lambda row: (float(row["lat"]), row["address_id"])),
                "LAT_MAX",
            ),
            (
                min(territory_rows, key=lambda row: (float(row["lon"]), row["address_id"])),
                "LON_MIN",
            ),
            (
                max(territory_rows, key=lambda row: (float(row["lon"]), row["address_id"])),
                "LON_MAX",
            ),
        ]
        numeric = [
            row
            for row in territory_rows
            if re.fullmatch(r"\d+", row["house_number"].strip())
        ]
        if numeric:
            rare_cutoff = sorted(int(row["house_number"]) for row in numeric)[
                math.floor(0.95 * (len(numeric) - 1))
            ]
            for row in numeric:
                if int(row["house_number"]) >= rare_cutoff:
                    reasons[row["address_id"]].add("RARE_HIGH_HOUSE_NUMBER")
        for row, label in extrema:
            reasons[row["address_id"]].add(f"GEOGRAPHIC_EXTREME_{label}")

    varnita = _varnita_geometry()
    for row in population:
        point = Point(float(row["lon"]), float(row["lat"]))
        if point.distance(varnita) <= 0.003:
            reasons[row["address_id"]].add("NEAR_VARNITA_BOUNDARY")

    for uid, discrepancy_reasons in _mandatory_discrepancy_mapping(population).items():
        reasons[uid].update(discrepancy_reasons)

    street_sizes = {
        key: len(rows)
        for key, rows in street_groups.items()
    }
    strata: dict[str, list[str]] = defaultdict(list)
    for row in population:
        district = str(metadata[row["address_id"]]["district"])
        key = (row["territory"], district, row["street"])
        district_label = district or "NO_DISTRICT_METADATA"
        stratum = "|".join(
            [
                row["territory"],
                district_label,
                row["deliverable_address_status"],
                street_bucket(street_sizes[key]),
            ]
        )
        strata[stratum].append(row["address_id"])

    selected = set(reasons)
    rng = random.Random(SEED)
    while len(selected) < MINIMUM_SAMPLE_SIZE:
        progress = False
        for stratum in sorted(strata):
            candidates = sorted(set(strata[stratum]) - selected)
            if candidates:
                uid = candidates[rng.randrange(len(candidates))]
                selected.add(uid)
                reasons[uid].add("SEEDED_STRATIFIED_FILL")
                progress = True
                if len(selected) >= MINIMUM_SAMPLE_SIZE:
                    break
        if not progress:
            break

    selected_counts = Counter()
    population_counts = Counter()
    uid_to_stratum: dict[str, str] = {}
    for stratum, uids in strata.items():
        population_counts[stratum] = len(uids)
        for uid in uids:
            uid_to_stratum[uid] = stratum
            if uid in selected:
                selected_counts[stratum] += 1

    output: list[dict[str, object]] = []
    for number, uid in enumerate(sorted(selected), start=1):
        source = by_id[uid]
        stratum = uid_to_stratum[uid]
        output.append(
            {
                "sample_id": f"YAV-{number:04d}",
                "address_id": uid,
                "territory": source["territory"],
                "street": source["street"],
                "house_number": source["house_number"],
                "lat": source["lat"],
                "lon": source["lon"],
                "deliverable_address_status": source["deliverable_address_status"],
                "selection_stratum": stratum,
                "selection_reason": ";".join(sorted(reasons[uid])),
                "sampling_weight": f"{population_counts[stratum] / selected_counts[stratum]:.8f}",
                "mandatory_check": "False"
                if reasons[uid] == {"SEEDED_STRATIFIED_FILL"}
                else "True",
            }
        )
    return output


def main() -> None:
    population, metadata = build_classification()
    sample = build_sample(population, metadata)
    write_csv(CLASSIFICATION, CLASSIFICATION_FIELDS, population)
    write_csv(SAMPLE, SAMPLE_FIELDS, sample)
    counts = Counter(row["deliverable_address_status"] for row in population)
    print(f"registry_sha256={normalized_sha256(REGISTRY)}")
    print(f"population={len(population)}")
    print(f"deliverable={counts['DELIVERABLE']}")
    print(f"non_deliverable={counts['NON_DELIVERABLE_STRUCTURE']}")
    print(f"unknown={counts['UNKNOWN_REQUIRES_REVIEW']}")
    print(f"sample={len(sample)}")


if __name__ == "__main__":
    main()
