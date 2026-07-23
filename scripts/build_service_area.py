#!/usr/bin/env python
"""Build the Stage-02 service-area QA data from the local OSM extract.

Local-only pipeline (needs the Moldova PBF + osmium-tool). It produces the small
committed artifacts that drive the public Leaflet map:

* docs/data/settlements.geojson      real boundaries (or boundary_missing markers)
* docs/data/roads.geojson            named streets with resolved RU names
* docs/data/summary.json             per-territory statistics
* docs/data/street-names-review.csv  street table + needs_ru_review list
* reports/stage-02/service-area-discovery.{json,md}

It never creates delivery zones, tariffs, routing graphs, or a production polygon,
and never invents a boundary or a Russian street name. Data comes from the local
extract, not Overpass/Nominatim.

Usage::

    uv run python scripts/build_service_area.py --pbf data/raw/moldova-latest.osm.pbf
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import osmium

from bender_zones import jsonutil
from bender_zones.config import load_audit, load_sources
from bender_zones.errors import SpatialAuditUnavailableError
from bender_zones.extract import extract_boundary, osmium_tool_path
from bender_zones.manifest import find_latest_manifest
from bender_zones.relations import find_relations
from bender_zones.service_area import (
    STREET_FIELDS,
    build_settlement_feature,
    load_local_ru_table,
    load_service_area,
    resolve_ru_name,
    round_coords,
    street_record,
)
from bender_zones.versions import tool_versions

NOTICE_RU = "Это карта проверки данных. Финальные зоны доставки ещё не созданы."
ROAD_PROP_KEYS = ["osm_id", "osm_type", "settlement", "highway",
                  "road_class", "is_address_street", "needs_name_classification_review",
                  "ru_display", "ru_source", "ru_status", *STREET_FIELDS]
_CLASS_PRIORITY = ["bridge", "intercity", "service", "informal", "track", "path", "other"]


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_boundary_geometry(geojson_path: Path) -> dict | None:
    data = jsonutil_load(geojson_path)
    feats = data.get("features") or []
    for feat in feats:
        geom = feat.get("geometry") or {}
        if geom.get("type") in ("Polygon", "MultiPolygon"):
            return round_coords(geom, 5)
    return None


def jsonutil_load(path: Path) -> dict:
    import json
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _node_lonlat(pbf: Path, workdir: Path, node_id: int) -> tuple[float, float] | None:
    """Fetch a single node's (lon, lat) via osmium getid. Used only for markers."""
    exe = osmium_tool_path()
    if exe is None:
        return None
    out = workdir / f"node-{node_id}.osm.pbf"
    proc = subprocess.run([exe, "getid", str(pbf), f"n{node_id}", "-o", str(out), "--overwrite"],
                          capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return None
    for obj in osmium.FileProcessor(str(out), osmium.osm.NODE):
        if obj.id == node_id:
            return (round(obj.lon, 5), round(obj.lat, 5))
    return None


def _process_city(city_pbf: Path, settlement_key: str, local_table: dict[str, str]):
    """Single pass over a city extract: road features, per-name segments, counts."""
    road_features: list[dict] = []
    segments_by_name: dict[str, list] = {}
    buildings = 0
    address_objects = 0

    fp = osmium.FileProcessor(str(city_pbf)).with_locations()
    for obj in fp:
        tags = {k: v for k, v in obj.tags}
        if tags.get("building") is not None:
            buildings += 1
        if tags.get("addr:housenumber") is not None:
            address_objects += 1

        if obj.type_str() != "w" or tags.get("highway") is None or not tags.get("name"):
            continue

        coords = []
        valid = True
        for nd in obj.nodes:
            if not nd.location.valid():
                valid = False
                break
            coords.append([round(nd.lon, 5), round(nd.lat, 5)])
        if not valid or len(coords) < 2:
            continue

        rec = street_record("way", obj.id, tags, settlement_key, local_table)
        road_features.append({
            "type": "Feature",
            "properties": {k: rec.get(k, tags.get(k)) for k in ROAD_PROP_KEYS},
            "geometry": {"type": "LineString", "coordinates": coords},
        })
        segments_by_name.setdefault(tags["name"], []).append(
            (obj.id, tags, rec["road_class"], rec["is_address_street"],
             rec["needs_name_classification_review"]))

    return road_features, segments_by_name, buildings, address_objects


def _merge_field(segments: list, field: str):
    """Value from the lowest-osm-id segment that carries *field* (deterministic)."""
    best, best_id = None, None
    for osm_id, tags, *_ in segments:
        value = tags.get(field)
        if value and (best_id is None or osm_id < best_id):
            best, best_id = value, osm_id
    return best


def _dominant_class(classes: list[str], is_address: bool) -> str:
    if is_address:
        return "address_street"
    for candidate in _CLASS_PRIORITY:
        if candidate in classes:
            return candidate
    return "other"


def _build_street_rows(segments_by_name: dict[str, list], settlement: str,
                       local_table: dict[str, str]) -> list[dict]:
    """Aggregate segments into one deterministic row per distinct street name."""
    rows: list[dict] = []
    for name in sorted(segments_by_name):
        segs = segments_by_name[name]
        merged = {f: _merge_field(segs, f) for f in STREET_FIELDS}
        merged["name"] = name
        display, source, status = resolve_ru_name(merged, local_table)
        is_address = any(s[3] for s in segs)
        needs_class = any(s[4] for s in segs)
        road_class = _dominant_class([s[2] for s in segs], is_address)
        rows.append({
            "settlement": settlement,
            "osm_type": "way",
            "osm_id": min(s[0] for s in segs),
            "ru_display": display,
            "ru_source": source,
            "ru_status": status,
            "road_class": road_class,
            "is_address_street": is_address,
            "needs_name_classification_review": needs_class,
            **{f: merged.get(f) for f in STREET_FIELDS},
        })
    return rows


def _street_stats(rows: list[dict]) -> dict:
    address = [r for r in rows if r["is_address_street"]]
    return {
        "named_ways_total": len(rows),
        "unique_streets": len(address),  # counts ONLY real address streets
        "streets_with_name_ru": sum(1 for r in address if r.get("name:ru")),
        "streets_needs_ru_review": sum(
            1 for r in address if r["ru_status"] == "needs_ru_review"),
        "streets_needs_name_classification_review": sum(
            1 for r in rows if r["needs_name_classification_review"]),
    }


def build(pbf: Path, repo_root: Path) -> int:
    sa = load_service_area(repo_root / "config" / "service-area.yml")
    local_table = load_local_ru_table(repo_root / "config" / "street-names-ru.yml")
    audit_cfg = load_audit(repo_root / "config" / "audit.yml")
    workdir = repo_root / audit_cfg.workdir
    workdir.mkdir(parents=True, exist_ok=True)

    infos = find_relations(pbf, [s.osm_id for s in sa.allowed])

    settlement_features: list[dict] = []
    all_roads: list[dict] = []
    all_streets: list[dict] = []
    per_settlement: dict[str, dict] = {}
    discovery: list[dict] = []
    warnings: list[str] = []
    boundaries_found = 0
    boundaries_missing = 0

    for entry in sa.allowed:
        info = infos[entry.osm_id]
        tags = info.tags
        geometry = None
        marker = None
        try:
            result = extract_boundary(pbf, entry.osm_id, workdir,
                                      strategy=audit_cfg.osmium_strategy)
            geometry = _read_boundary_geometry(result.boundary_geojson)
            if geometry is None:
                raise SpatialAuditUnavailableError("export produced no usable polygon")
            city_pbf = result.city_pbf
        except SpatialAuditUnavailableError as exc:
            warnings.append(f"{entry.key}: boundary unavailable ({exc}); shown as marker")
            city_pbf = None

        if geometry is None:
            boundaries_missing += 1
            if entry.place_node:
                marker = _node_lonlat(pbf, workdir, entry.place_node)
            feature = build_settlement_feature(entry, tags, geometry=None, marker_lonlat=marker)
            stats = {"named_ways_total": 0, "unique_streets": 0, "streets_with_name_ru": 0,
                     "streets_needs_ru_review": 0,
                     "streets_needs_name_classification_review": 0,
                     "buildings": 0, "address_objects": 0}
        else:
            boundaries_found += 1
            feature = build_settlement_feature(entry, tags, geometry=geometry)
            roads, segments_by_name, buildings, addr = _process_city(
                city_pbf, entry.key, local_table)
            all_roads.extend(roads)
            rows = _build_street_rows(segments_by_name, entry.key, local_table)
            all_streets.extend(rows)
            stats = {**_street_stats(rows),
                     "buildings": buildings, "address_objects": addr}

        settlement_features.append(feature)
        per_settlement[entry.key] = {
            "display_ru": entry.display_ru,
            "osm_type": entry.osm_type,
            "osm_id": entry.osm_id,
            "boundary_status": feature["properties"]["status"],
            **stats,
        }
        discovery.append({
            "key": entry.key,
            "display_ru": entry.display_ru,
            "osm_type": entry.osm_type,
            "osm_id": entry.osm_id,
            "found": info.found,
            "boundary_status": feature["properties"]["status"],
            "tags": tags,
            "member_count": info.member_count,
            "member_type_counts": info.member_type_counts,
            **stats,
        })

    # Deterministic ordering.
    settlement_features.sort(key=lambda f: f["properties"]["osm_id"])
    all_roads.sort(key=lambda f: (f["properties"]["settlement"], f["properties"]["osm_id"]))
    all_streets.sort(key=lambda r: (r["settlement"], r["name"] or "", r["osm_id"]))

    def _sum(field):
        return sum(p[field] for p in per_settlement.values())

    totals = {
        "settlements": len(sa.allowed),
        "boundaries_found": boundaries_found,
        "boundaries_missing": boundaries_missing,
        "named_ways_total": _sum("named_ways_total"),
        "unique_streets": _sum("unique_streets"),
        "streets_with_name_ru": _sum("streets_with_name_ru"),
        "streets_needs_ru_review": _sum("streets_needs_ru_review"),
        "streets_needs_name_classification_review": _sum(
            "streets_needs_name_classification_review"),
    }

    # --- write map data ---
    data_dir = repo_root / "docs" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    jsonutil.write(data_dir / "settlements.geojson",
                   {"type": "FeatureCollection", "features": settlement_features})
    jsonutil.write(data_dir / "roads.geojson",
                   {"type": "FeatureCollection", "features": all_roads})

    manifest = find_latest_manifest(repo_root / "data" / "manifests",
                                    str(pbf.relative_to(repo_root)).replace("\\", "/"))
    summary = {
        "schema": "bender-service-area/2",
        "generated_at": _utc_now_iso(),
        "notice": NOTICE_RU,
        "boundary_selected": False,
        "zones_created": False,
        "excluded_settlements": [{"key": k, "reason": r} for k, r in sa.excluded],
        "totals": totals,
        "per_settlement": per_settlement,
        "source_pbf_sha256": (manifest or {}).get("sha256"),
        "tool_versions": tool_versions(),
    }
    jsonutil.write(data_dir / "summary.json", summary)

    _write_street_csv(data_dir / "street-names-review.csv", all_streets)

    # --- write reports ---
    reports_dir = repo_root / "reports" / "stage-02"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "bender-service-area-discovery/2",
        "generated_at": summary["generated_at"],
        "zones_created": False,
        "boundary_selected": False,
        "allowed_settlements": discovery,
        "excluded_settlements": [{"key": k, "reason": r} for k, r in sa.excluded],
        "boundaries_found": [d["key"] for d in discovery
                             if d["boundary_status"] == "boundary_found"],
        "boundaries_needing_manual_decision": [
            d["key"] for d in discovery if d["boundary_status"] == "boundary_missing"],
        "totals": totals,
        "source_pbf_sha256": summary["source_pbf_sha256"],
        "tool_versions": summary["tool_versions"],
        "warnings": warnings,
        "limitations": [
            "This is a data-QA map. No delivery zones, tariffs, routing graph, or "
            "production polygon are created.",
            "Territories are shown as separate real OSM boundaries; they are NOT "
            "merged into a final service polygon at this stage.",
            "Varnița is intentionally excluded from the service area.",
            "The unique_streets statistic counts only real address streets "
            "(is_address_street=true). Intercity roads, named bridge structures, "
            "service/track ways and informal placeholder names are classified via "
            "road_class and excluded from the count; ambiguous ones set "
            "needs_name_classification_review for a human to confirm.",
            "Street Russian names are resolved by priority (verified local override "
            "first, then name:ru/official_name:ru/alt_name:ru); unconfirmed ones "
            "are flagged needs_ru_review and never transliterated.",
            "Address coverage in OpenStreetMap is community-contributed and NOT complete.",
        ],
    }
    jsonutil.write(reports_dir / "service-area-discovery.json", report)
    (reports_dir / "service-area-discovery.md").write_text(
        _render_report_md(report, summary), encoding="utf-8", newline="\n")

    print("wrote docs/data/settlements.geojson, roads.geojson, summary.json, "
          "street-names-review.csv")
    print("wrote reports/stage-02/service-area-discovery.{json,md}")
    print(f"boundaries found: {boundaries_found} | missing: {boundaries_missing}")
    print(f"unique streets: {totals['unique_streets']} | with name:ru: "
          f"{totals['streets_with_name_ru']} | needs_ru_review: "
          f"{totals['streets_needs_ru_review']}")
    return 0


def _write_street_csv(path: Path, streets: list[dict]) -> None:
    header = ["settlement", "osm_type", "osm_id", "name", "name_ru", "name_ro",
              "official_name", "alt_name", "old_name", "ru_display", "ru_source",
              "ru_status", "road_class", "is_address_street",
              "needs_name_classification_review"]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(header)
        for r in streets:
            writer.writerow([
                r["settlement"], r["osm_type"], r["osm_id"], r.get("name"),
                r.get("name:ru"), r.get("name:ro"), r.get("official_name"),
                r.get("alt_name"), r.get("old_name"), r["ru_display"],
                r["ru_source"], r["ru_status"], r["road_class"],
                r["is_address_street"], r["needs_name_classification_review"],
            ])


def _render_report_md(report: dict, summary: dict) -> str:
    lines = ["# Stage 02 — service-area discovery (data QA)", "",
             f"- Generated (UTC): `{report['generated_at']}`",
             f"- Zones created: **{report['zones_created']}** · "
             f"boundary_selected: **{report['boundary_selected']}**",
             f"- Source PBF SHA-256: `{report['source_pbf_sha256']}`", "",
             "> " + summary["notice"], "",
             "## Allowed territories & discovered OSM objects", ""]
    for d in report["allowed_settlements"]:
        lines += [f"### {d['display_ru']} (`{d['key']}`)",
                  f"- OSM object: **{d['osm_type']} {d['osm_id']}** · found: {d['found']}",
                  f"- Boundary status: **{d['boundary_status']}**",
                  f"- Members: {d['member_count']} `{d['member_type_counts']}`",
                  f"- Address streets: {d['unique_streets']} "
                  f"(of {d['named_ways_total']} named ways) · "
                  f"{d['streets_with_name_ru']} with name:ru · "
                  f"{d['streets_needs_ru_review']} need RU review · "
                  f"{d['streets_needs_name_classification_review']} need class review",
                  f"- Buildings: {d['buildings']} · address objects: {d['address_objects']}",
                  "- Key tags: " + ", ".join(
                      f"`{k}={d['tags'].get(k)}`" for k in
                      ("name", "name:ru", "name:ro", "admin_level", "boundary")
                      if d["tags"].get(k)),
                  ""]
    lines += ["## Boundary status summary", "",
              f"- Found: {report['boundaries_found'] or '—'}",
              f"- Need manual decision (boundary_missing): "
              f"{report['boundaries_needing_manual_decision'] or '— none'}", "",
              "## Excluded", ""]
    for e in report["excluded_settlements"]:
        lines += [f"- **{e['key']}** — {e['reason']}"]
    lines += ["", "## Warnings", ""]
    lines += [f"- {w}" for w in report["warnings"]] or ["- none"]
    lines += ["", "## Limitations", ""]
    lines += [f"- {lim}" for lim in report["limitations"]]
    lines += [""]
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pbf", default=None)
    parser.add_argument("--source", default="osm_moldova")
    parser.add_argument("--repo-root", default=".")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root)
    sources = load_sources(repo_root / "config" / "sources.yml")
    pbf_rel = args.pbf or sources[args.source].destination
    pbf = repo_root / pbf_rel
    if not pbf.is_file():
        print(f"error: PBF not found: {pbf}", file=sys.stderr)
        print("hint: run scripts/download_osm.py first (local only).", file=sys.stderr)
        return 2
    if osmium_tool_path() is None:
        print("error: osmium-tool not found; exact boundary extraction is required.",
              file=sys.stderr)
        return 2
    return build(pbf, repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
