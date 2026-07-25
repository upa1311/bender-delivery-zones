#!/usr/bin/env python
"""Build the immutable zone release `releases/bender-zones-v1.1`.

v1.1 splits the catalog into an EXACT working address registry (verified,
export-eligible, zoned houses only) and an admin-only QA-objects file (disputed,
no_delivery, unaddressed, owner-review, Tier C, excluded, all Северный). The
release ships zone geometry + Varnița/Северный layers + a street index +
schemas/zone-release.schema.json, with a manifest, checksums and IMMUTABLE
marker. NO pricing schema. NO money. v1.0 is left untouched.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from bender_zones import jsonutil

RELEASE_ID = "bender-zones-v1.1"
VERSION = "1.1.0"
ZONE_EDGES = [2.424, 4.076, 5.577, 9.692]
ZONE_COLORS = {"1": "#2a9d3f", "2": "#f2c500", "3": "#f07f14", "4": "#d62828"}
MONEY_TOKENS = ("delivery_fee", "courier_payout", "courier_base_payout",
                "price_cents", "pricecents", "amount_cents", "customer_delivery_fee",
                "tariff")
REGISTRY_FIELDS = ["uid", "settlement_ru", "district_ru", "street_ru", "housenumber",
                   "canonical_address_key", "zone_id", "service_status",
                   "source_dataset_version", "route_flags"]
REQUIRED_FILES = [
    "manifest.json", "CHECKSUMS.sha256", "IMMUTABLE", "address-registry.json",
    "street-index.json", "admin-qa-objects.json", "zone-polygons.geojson",
    "varnita-village-no-delivery.geojson", "varnita-admin-reference.geojson",
    "severny-route-qa.geojson", "schemas/zone-release.schema.json",
]
COPY_GEOJSON = {
    "zone-polygons.geojson": "docs/data/final-zone-polygons.geojson",
    "varnita-village-no-delivery.geojson": "docs/data/varnita-village-no-delivery.geojson",
    "varnita-admin-reference.geojson": "docs/data/varnita-admin-reference.geojson",
    "severny-route-qa.geojson": "docs/data/severny-route-qa.geojson",
}


def _sha(path: Path):
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def _assert_no_money(path: Path):
    text = path.read_text(encoding="utf-8").lower()
    for token in MONEY_TOKENS:
        if token in text:
            raise SystemExit(f"refusing to release: money token {token!r} in {path}")


def _is_registry(a: dict) -> bool:
    return bool(
        a["direct_export_eligible"]
        and a["address_status"] == "verified_osm_address"
        and a["zone_id"] in (1, 2, 3, 4)
        and a["service_status"] in ("standard", "low_density")
        and not a["owner_review_required"]
        and a["canonical_address_key"]
        and a["housenumber"]
    )


def build(repo_root: Path) -> int:
    catalog = json.loads((repo_root / "docs/data/final-address-zone-catalog.json")
                         .read_text("utf-8"))["addresses"]
    version = next((a["source_dataset_version"] for a in catalog
                    if a.get("source_dataset_version")), "moldova-pbf:unknown")

    # --- exact working registry: dedup by canonical address ---
    by_canon: dict[str, dict] = {}
    for a in catalog:
        if not _is_registry(a):
            continue
        key = a["canonical_address_key"]
        prev = by_canon.get(key)
        if prev is None or a["uid"] < prev["uid"]:
            by_canon[key] = a
    registry = []
    for a in sorted(by_canon.values(),
                    key=lambda x: (x["settlement_ru"] or "", x["district_ru"] or "",
                                   x["street_ru"] or "", x["canonical_address_key"])):
        registry.append({
            "uid": a["uid"], "settlement_ru": a["settlement_ru"],
            "district_ru": a["district_ru"], "street_ru": a["street_ru"],
            "housenumber": a["housenumber"],
            "canonical_address_key": a["canonical_address_key"],
            "zone_id": a["zone_id"], "service_status": a["service_status"],
            "source_dataset_version": a["source_dataset_version"] or version,
            "route_flags": {"requires_varnita_transit": False},
        })

    # --- admin QA objects: everything NOT in the working registry ---
    registry_uids = {a["uid"] for a in by_canon.values()}
    qa_objects = []
    for a in catalog:
        if a["uid"] in registry_uids:
            continue
        qa_objects.append({
            "uid": a["uid"], "osm_type": a["osm_type"], "osm_id": a["osm_id"],
            "settlement_ru": a["settlement_ru"], "district_ru": a["district_ru"],
            "street_ru": a["street_ru"], "housenumber": a["housenumber"],
            "canonical_address_key": a["canonical_address_key"],
            "zone_id": a["zone_id"], "service_status": a["service_status"],
            "address_status": a["address_status"],
            "owner_review_required": a["owner_review_required"],
            "severny": bool(a.get("severny")),
        })

    release = repo_root / "releases" / RELEASE_ID
    if release.exists():
        shutil.rmtree(release)
    (release / "schemas").mkdir(parents=True)

    jsonutil.write_compact(release / "address-registry.json", {
        "schema": "bender-address-registry/1.1", "release_id": RELEASE_ID,
        "version": VERSION, "source_dataset_version": version, "decided_k": 4,
        "prices_included": False,
        "note": ("Exact working registry: verified OSM addresses with a confirmed "
                 "house and a Zone 1-4 only. The resolver uses ONLY this file. No "
                 "money."),
        "verified_address_count": len(registry), "addresses": registry})
    jsonutil.write_compact(release / "admin-qa-objects.json", {
        "schema": "bender-admin-qa-objects/1.1", "release_id": RELEASE_ID,
        "note": ("Admin-only QA objects: disputed, no_delivery, unaddressed, "
                 "owner-review, Tier C, excluded and all Северный. Never a working "
                 "delivery zone."),
        "qa_object_count": len(qa_objects), "objects": qa_objects})

    streets = json.loads((repo_root / "docs/data/final-street-zone-catalog.json")
                         .read_text("utf-8"))["streets"]
    jsonutil.write_compact(release / "street-index.json", {
        "schema": "bender-street-index/1.1", "release_id": RELEASE_ID,
        "note": "Street catalog for admin display; the house is the source of truth.",
        "streets": streets})

    for name, rel in COPY_GEOJSON.items():
        src = repo_root / rel
        _assert_no_money(src)
        shutil.copy2(src, release / name)
    shutil.copy2(repo_root / "schemas/zone-release.schema.json",
                 release / "schemas/zone-release.schema.json")

    for p in (release / "address-registry.json", release / "admin-qa-objects.json",
              release / "street-index.json"):
        _assert_no_money(p)

    files = []
    for p in sorted(release.rglob("*")):
        if p.is_file() and p.name not in ("manifest.json", "CHECKSUMS.sha256"):
            sha, n = _sha(p)
            files.append({"path": str(p.relative_to(release)).replace("\\", "/"),
                          "sha256": sha, "bytes": n})

    manifest = {
        "release_id": RELEASE_ID, "version": VERSION, "immutable": True,
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "decided_k": 4, "scenario": "A", "prices_included": False,
        "source_dataset_version": version,
        "approved_for_internal_integration": True,
        "approved_for_customer_address_catalog": True,
        "severny_address_catalog_complete": False,
        "verified_address_count": len(registry),
        "qa_object_count": len(qa_objects),
        "zone_edges_km": ZONE_EDGES, "zone_colors": ZONE_COLORS,
        "required_files": REQUIRED_FILES, "files": files,
        "notes": ("Zones only. No pricing schema, no money. Immutable — a new "
                  "version is a new release folder. See "
                  "docs/product/ZONE_PRICING_SEPARATION.md."),
    }
    jsonutil.write(release / "manifest.json", manifest)
    (release / "CHECKSUMS.sha256").write_text(
        "".join(f"{f['sha256']}  {f['path']}\n" for f in files),
        encoding="utf-8", newline="\n")
    (release / "IMMUTABLE").write_text(
        f"{RELEASE_ID} {VERSION} — immutable. Do not edit in place.\n",
        encoding="utf-8", newline="\n")
    (release / "README.md").write_text(
        f"# {RELEASE_ID} ({VERSION})\n\nExact-address Bender zone release (K=4, "
        "Scenario A). Zones only, no prices, no pricing schema. Working resolver "
        "uses `address-registry.json`; admin QA uses `admin-qa-objects.json`. "
        "Validate `CHECKSUMS.sha256` fail-closed before use.\n",
        encoding="utf-8", newline="\n")

    print(f"release {RELEASE_ID} {VERSION}: verified_address_count={len(registry)} "
          f"qa_object_count={len(qa_objects)} files={len(files)}")
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo-root", default=".")
    return build(Path(ap.parse_args(argv).repo_root))


if __name__ == "__main__":
    raise SystemExit(main())
