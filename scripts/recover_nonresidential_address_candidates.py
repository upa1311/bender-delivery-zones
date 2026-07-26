"""Recover the 36 legacy non-residential exclusions from the pinned OSM PBF.

This is an audit-only extractor.  It reads the exact checksummed source used by
release v1.1, writes a separate candidate layer, and never mutates the canonical
registry or routing graph.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections.abc import Iterable
from pathlib import Path

import osmium
from shapely.geometry import Point, Polygon

from bender_zones.normalize import normalize_text

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PBF = ROOT / "data/raw/moldova-260722.osm.pbf"
EXCEPTIONS = ROOT / "docs/data/delivery-exceptions.csv"
REGISTRY = ROOT / "releases/bender-zones-v1.1/address-registry.json"
OUTPUT = ROOT / "data/interim/recovered-nonresidential-address-candidates-v1.csv"

SOURCE_DATASET = "moldova-pbf:09ba0c058e89"
SOURCE_SHA256 = "09ba0c058e89faacac7e1b1e7c8d0fbb14b4df66061b43abdce590b65ce8813c"
EXCLUSION_REASON = "address_inside_nonresidential_building"

FIELDS = [
    "candidate_id",
    "exception_row_id",
    "osm_type",
    "osm_id",
    "source_dataset",
    "source_sha256",
    "source_recovery_status",
    "lat",
    "lon",
    "settlement",
    "street",
    "house_number",
    "name",
    "building",
    "building_part",
    "amenity",
    "healthcare",
    "shop",
    "office",
    "industrial",
    "craft",
    "tourism",
    "leisure",
    "government",
    "public_transport",
    "railway",
    "entrance",
    "access",
    "lifecycle_status",
    "parent_object_id",
    "facility_category",
    "has_separate_address",
    "independent_delivery_entrance",
    "candidate_delivery_status",
    "exclusion_reason_original",
    "recovery_evidence",
    "manual_yandex_review_required",
    "owner_review_required",
    "notes",
]

FACILITY_TAGS = {
    "building",
    "building:part",
    "amenity",
    "healthcare",
    "shop",
    "office",
    "industrial",
    "craft",
    "tourism",
    "leisure",
    "government",
    "public_transport",
    "railway",
    "entrance",
    "access",
    "name",
}
PARENT_SELECTOR_TAGS = FACILITY_TAGS - {"access", "entrance", "name"}
LIFECYCLE_VALUES = {"abandoned", "collapsed", "demolished", "ruin", "ruins"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def legacy_exclusions() -> list[dict[str, str]]:
    return [row for row in read_csv(EXCEPTIONS) if row["reason"] == EXCLUSION_REASON]


class TargetNodeHandler(osmium.SimpleHandler):
    def __init__(self, target_ids: set[int]) -> None:
        super().__init__()
        self.target_ids = target_ids
        self.nodes: dict[int, dict[str, object]] = {}

    def node(self, node: osmium.osm.Node) -> None:
        if node.id in self.target_ids:
            self.nodes[node.id] = {
                "lat": node.location.lat,
                "lon": node.location.lon,
                "tags": dict(node.tags),
            }


class ParentWayHandler(osmium.SimpleHandler):
    def __init__(self, target_nodes: dict[int, dict[str, object]]) -> None:
        super().__init__()
        self.targets = {
            node_id: Point(float(record["lon"]), float(record["lat"]))
            for node_id, record in target_nodes.items()
        }
        self.target_bounds = (
            min(point.x for point in self.targets.values()),
            min(point.y for point in self.targets.values()),
            max(point.x for point in self.targets.values()),
            max(point.y for point in self.targets.values()),
        )
        self.parents: dict[int, tuple[float, int, dict[str, str]]] = {}

    def way(self, way: osmium.osm.Way) -> None:
        tags = dict(way.tags)
        if not PARENT_SELECTOR_TAGS.intersection(tags) or len(way.nodes) < 4:
            return
        try:
            coordinates = [(node.lon, node.lat) for node in way.nodes]
        except osmium.InvalidLocationError:
            return
        if coordinates[0] != coordinates[-1]:
            return
        way_lons = [coordinate[0] for coordinate in coordinates]
        way_lats = [coordinate[1] for coordinate in coordinates]
        min_lon, min_lat = min(way_lons), min(way_lats)
        max_lon, max_lat = max(way_lons), max(way_lats)
        target_min_lon, target_min_lat, target_max_lon, target_max_lat = self.target_bounds
        if (
            max_lon < target_min_lon
            or min_lon > target_max_lon
            or max_lat < target_min_lat
            or min_lat > target_max_lat
        ):
            return
        possible_targets = {
            node_id: point
            for node_id, point in self.targets.items()
            if min_lon <= point.x <= max_lon and min_lat <= point.y <= max_lat
        }
        if not possible_targets:
            return
        polygon = Polygon(coordinates)
        if polygon.is_empty or not polygon.is_valid:
            polygon = polygon.buffer(0)
        if polygon.is_empty:
            return
        for node_id, point in possible_targets.items():
            if not polygon.covers(point):
                continue
            previous = self.parents.get(node_id)
            area = polygon.area
            if previous is None or area < previous[0]:
                self.parents[node_id] = (area, way.id, tags)


def merged_tag(node_tags: dict[str, str], parent_tags: dict[str, str], key: str) -> str:
    return node_tags.get(key, parent_tags.get(key, ""))


def lifecycle_status(node_tags: dict[str, str], parent_tags: dict[str, str]) -> str:
    combined = {**parent_tags, **node_tags}
    for key in ("building", "building:part"):
        if combined.get(key, "").casefold() in LIFECYCLE_VALUES:
            return combined[key].casefold()
    for prefix in ("abandoned", "demolished", "disused", "ruins"):
        if prefix in combined or any(key.startswith(f"{prefix}:") for key in combined):
            return prefix
    return ""


def facility_category(tags: dict[str, str]) -> str:
    amenity = tags.get("amenity", "").casefold()
    healthcare = tags.get("healthcare", "").casefold()
    building = tags.get("building", "").casefold()
    office = tags.get("office", "").casefold()
    industrial = tags.get("industrial", "").casefold()
    tourism = tags.get("tourism", "").casefold()
    public_transport = tags.get("public_transport", "").casefold()
    railway = tags.get("railway", "").casefold()
    if healthcare or amenity in {"clinic", "doctors", "hospital", "pharmacy", "veterinary"}:
        return "MEDICAL"
    if amenity in {"college", "kindergarten", "school", "university"}:
        return "EDUCATION"
    if building == "warehouse" or industrial == "warehouse":
        return "WAREHOUSE"
    if industrial or tags.get("craft") or building in {"enterprise", "factory", "industrial"}:
        return "INDUSTRIAL"
    if amenity in {"cafe", "fast_food", "restaurant"}:
        return "FOOD_SERVICE"
    if tourism:
        return "HOSPITALITY"
    if office == "government" or tags.get("government") or amenity == "townhall":
        return "GOVERNMENT"
    if office:
        return "OFFICE"
    if amenity in {"bank", "community_centre", "courthouse", "fire_station", "police"}:
        return "PUBLIC_SERVICE"
    if public_transport or railway:
        return "TRANSPORT"
    if tags.get("shop") or amenity == "fuel" or building in {"commercial", "retail"}:
        return "RETAIL"
    if amenity or tags.get("leisure") or tags.get("name"):
        return "OTHER_DELIVERABLE"
    return "UNKNOWN"


def canonical_street_house_keys() -> set[tuple[str, str]]:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))["addresses"]
    return {
        (normalize_text(row.get("street_ru") or ""), normalize_text(row.get("housenumber") or ""))
        for row in registry
        if row.get("street_ru") and row.get("housenumber")
    }


def classify_candidate(
    *,
    unit_type: str,
    category: str,
    has_address: bool,
    has_entrance: bool,
    lifecycle: str,
    is_duplicate: bool,
) -> str:
    if lifecycle:
        return "NON_DELIVERABLE_LIFECYCLE"
    if is_duplicate:
        return "DUPLICATE_EXISTING_ADDRESS"
    if unit_type == "address_in_outbuilding" and not (has_address or has_entrance):
        return "NON_DELIVERABLE_AUXILIARY"
    if category != "UNKNOWN" and (has_address or has_entrance):
        return "DELIVERABLE_CANDIDATE"
    return "UNKNOWN_REQUIRES_REVIEW"


def _bool(value: bool) -> str:
    return "True" if value else "False"


def build_rows(pbf: Path) -> list[dict[str, str]]:
    exclusions = legacy_exclusions()
    target_ids = {int(row["osm_id"]) for row in exclusions}
    node_handler = TargetNodeHandler(target_ids)
    node_handler.apply_file(str(pbf))
    if set(node_handler.nodes) != target_ids:
        missing = sorted(target_ids - set(node_handler.nodes))
        raise ValueError(f"Pinned source is missing target nodes: {missing}")

    parent_handler = ParentWayHandler(node_handler.nodes)
    parent_handler.apply_file(str(pbf), locations=True)
    canonical_keys = canonical_street_house_keys()
    rows: list[dict[str, str]] = []
    for index, exclusion in enumerate(exclusions, start=1):
        node_id = int(exclusion["osm_id"])
        node = node_handler.nodes[node_id]
        node_tags = dict(node["tags"])
        parent = parent_handler.parents.get(node_id)
        parent_id = parent[1] if parent else None
        parent_tags = parent[2] if parent else {}
        combined = {**parent_tags, **node_tags}
        street = merged_tag(node_tags, parent_tags, "addr:street")
        house_number = merged_tag(node_tags, parent_tags, "addr:housenumber")
        settlement = merged_tag(node_tags, parent_tags, "addr:city") or merged_tag(
            node_tags, parent_tags, "addr:place"
        )
        lifecycle = lifecycle_status(node_tags, parent_tags)
        category = facility_category(combined)
        has_address = bool(street and house_number)
        entrance = merged_tag(node_tags, parent_tags, "entrance")
        has_entrance = entrance.casefold() in {"designated", "main", "yes"}
        address_key = (normalize_text(street), normalize_text(house_number))
        is_duplicate = has_address and address_key in canonical_keys
        status = classify_candidate(
            unit_type=exclusion["unit_type"],
            category=category,
            has_address=has_address,
            has_entrance=has_entrance,
            lifecycle=lifecycle,
            is_duplicate=is_duplicate,
        )
        evidence_parts = [
            f"node n{node_id} recovered from SHA-256 verified pinned PBF",
            "source node address tags present" if has_address else "source node address incomplete",
        ]
        if parent_id:
            evidence_parts.append(f"containing way w{parent_id} recovered from the same PBF")
        else:
            evidence_parts.append("no containing tagged way found")
        rows.append(
            {
                "candidate_id": f"REC-{index:03d}",
                "exception_row_id": exclusion["uid"],
                "osm_type": exclusion["osm_type"],
                "osm_id": exclusion["osm_id"],
                "source_dataset": SOURCE_DATASET,
                "source_sha256": SOURCE_SHA256,
                "source_recovery_status": "RECOVERED_FROM_PINNED_SOURCE",
                "lat": f"{float(node['lat']):.7f}",
                "lon": f"{float(node['lon']):.7f}",
                "settlement": settlement,
                "street": street,
                "house_number": house_number,
                "name": node_tags.get("name")
                or node_tags.get("name:ru")
                or parent_tags.get("name")
                or parent_tags.get("name:ru", ""),
                "building": merged_tag(node_tags, parent_tags, "building"),
                "building_part": merged_tag(node_tags, parent_tags, "building:part"),
                "amenity": merged_tag(node_tags, parent_tags, "amenity"),
                "healthcare": merged_tag(node_tags, parent_tags, "healthcare"),
                "shop": merged_tag(node_tags, parent_tags, "shop"),
                "office": merged_tag(node_tags, parent_tags, "office"),
                "industrial": merged_tag(node_tags, parent_tags, "industrial"),
                "craft": merged_tag(node_tags, parent_tags, "craft"),
                "tourism": merged_tag(node_tags, parent_tags, "tourism"),
                "leisure": merged_tag(node_tags, parent_tags, "leisure"),
                "government": merged_tag(node_tags, parent_tags, "government"),
                "public_transport": merged_tag(node_tags, parent_tags, "public_transport"),
                "railway": merged_tag(node_tags, parent_tags, "railway"),
                "entrance": entrance,
                "access": merged_tag(node_tags, parent_tags, "access"),
                "lifecycle_status": lifecycle,
                "parent_object_id": f"w{parent_id}" if parent_id else "",
                "facility_category": category,
                "has_separate_address": _bool(has_address),
                "independent_delivery_entrance": _bool(has_entrance),
                "candidate_delivery_status": status,
                "exclusion_reason_original": exclusion["reason"],
                "recovery_evidence": "; ".join(evidence_parts),
                "manual_yandex_review_required": "True",
                "owner_review_required": _bool(
                    status in {"DELIVERABLE_CANDIDATE", "UNKNOWN_REQUIRES_REVIEW"}
                ),
                "notes": f"legacy unit_type={exclusion['unit_type']}",
            }
        )
    first_candidate_by_address: dict[tuple[str, str], str] = {}
    for row in rows:
        if row["candidate_delivery_status"] != "DELIVERABLE_CANDIDATE":
            continue
        address_identity = (
            row["parent_object_id"] or normalize_text(row["street"]),
            normalize_text(row["house_number"]),
        )
        first_candidate = first_candidate_by_address.get(address_identity)
        if first_candidate:
            row["candidate_delivery_status"] = "DUPLICATE_EXISTING_ADDRESS"
            row["owner_review_required"] = "False"
            row["notes"] += f"; same recovered address as {first_candidate}"
        else:
            first_candidate_by_address[address_identity] = row["candidate_id"]
    return rows


def write_rows(path: Path, rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pbf", type=Path, default=DEFAULT_PBF)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.pbf.is_file():
        raise SystemExit(f"Pinned source not found: {args.pbf}")
    actual_sha = sha256(args.pbf)
    if actual_sha != SOURCE_SHA256:
        raise SystemExit(
            f"Pinned source SHA-256 mismatch: expected {SOURCE_SHA256}, got {actual_sha}"
        )
    rows = build_rows(args.pbf)
    write_rows(args.output, rows)
    counts: dict[str, int] = {}
    for row in rows:
        status = row["candidate_delivery_status"]
        counts[status] = counts.get(status, 0) + 1
    print(f"recovered={len(rows)}")
    for status, count in sorted(counts.items()):
        print(f"{status}={count}")


if __name__ == "__main__":
    main()
