#!/usr/bin/env python
"""Build the immutable versioned zone release `releases/bender-zones-v1`.

Freezes the owner-approved zones (K=4, Scenario A) into a vendorable, checksummed
release: a compact zone dataset (geometry + colours + address->zone index), the
schemas, a manifest with SHA-256 checksums, and an IMMUTABLE marker. Contains NO
money — verified before writing. Deterministic; safe to re-run.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from bender_zones import jsonutil

RELEASE = "bender-zones-v1"
VERSION = "1.0.0"
ZONE_EDGES = [2.424, 4.076, 5.577, 9.692]
ZONE_COLORS = {"1": "#2a9d3f", "2": "#f2c500", "3": "#f07f14", "4": "#d62828"}
MONEY_TOKENS = ("delivery_fee", "courier_payout", "courier_base_payout",
                "priceCents", "price_cents", "amount_cents", "currency",
                "customer_delivery_fee")

# Copied into the release (small, vendorable).
INCLUDE = [
    "docs/data/final-zone-polygons.geojson",
    "docs/data/final-street-zone-catalog.json",
    "docs/data/final-zone-map-summary.json",
    "docs/data/varnita-village-no-delivery.geojson",
    "docs/data/varnita-admin-reference.geojson",
    "docs/data/severny-service-area.geojson",
]
SCHEMAS = ["zone-dataset", "address-zone-lookup", "zone-tariff-matrix",
           "order-pricing-snapshot"]
# Checksummed but NOT copied (large; canonical copy stays in docs/data).
REFERENCED = [
    "docs/data/final-address-zone-catalog.csv",
    "docs/data/final-address-zone-points.geojson",
]


def _sha256(path: Path) -> tuple[str, int]:
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def _assert_no_money(path: Path) -> None:
    if path.suffix not in (".json", ".geojson", ".csv"):
        return
    text = path.read_text(encoding="utf-8").lower()
    for token in MONEY_TOKENS:
        if token.lower() in text and token != "currency":
            raise SystemExit(f"refusing to release: money token {token!r} in {path}")


def build(repo_root: Path) -> int:
    release_dir = repo_root / "releases" / RELEASE
    if release_dir.exists():
        shutil.rmtree(release_dir)
    (release_dir / "data").mkdir(parents=True)
    (release_dir / "schemas").mkdir(parents=True)

    summary = json.loads((repo_root / "docs/data/final-zone-map-summary.json")
                         .read_text("utf-8"))
    streets = json.loads((repo_root / "docs/data/final-street-zone-catalog.json")
                         .read_text("utf-8"))["streets"]
    polygons = json.loads((repo_root / "docs/data/final-zone-polygons.geojson")
                          .read_text("utf-8"))
    dataset_version = None
    catalog = json.loads((repo_root / "docs/data/final-address-zone-catalog.json")
                         .read_text("utf-8"))
    for a in catalog["addresses"]:
        if a.get("source_dataset_version"):
            dataset_version = a["source_dataset_version"]
            break

    # Compact vendorable dataset (the shape Direct imports).
    zones = [{"zone_id": f["properties"]["zone_id"],
              "zone_name": f["properties"]["zone_name"],
              "color": f["properties"]["color"],
              "component": f["properties"]["component"]}
             for f in polygons["features"]]
    resolution_streets = [{
        "settlement_ru": s["settlement_ru"], "district_ru": s["district_ru"],
        "street_ru": s["street_ru"], "zones": s["zones"],
        "split_street": s["split_street"], "service_status": s["service_status"],
        "houses_by_zone": s["houses_by_zone"]} for s in streets]
    dataset = {
        "release": RELEASE, "version": VERSION, "immutable": True,
        "decided_k": 4, "scenario": "A", "zone_edges_km": ZONE_EDGES,
        "zone_colors": ZONE_COLORS, "source_dataset_version": dataset_version,
        "prices_included": False, "direct_integration": False,
        "zones": zones,
        "resolution_index": {"streets": resolution_streets},
    }
    jsonutil.write_compact(release_dir / "data" / "zone-dataset.json", dataset)

    for rel in INCLUDE:
        src = repo_root / rel
        _assert_no_money(src)
        shutil.copy2(src, release_dir / "data" / Path(rel).name)
    for name in SCHEMAS:
        shutil.copy2(repo_root / "schemas" / f"{name}.schema.json",
                     release_dir / "schemas" / f"{name}.schema.json")

    # checksums over every released file + referenced canonical artifacts
    files = []
    for p in sorted((release_dir / "data").glob("*")) + \
            sorted((release_dir / "schemas").glob("*")):
        sha, n = _sha256(p)
        files.append({"path": str(p.relative_to(release_dir)).replace("\\", "/"),
                      "sha256": sha, "bytes": n})
    referenced = []
    for rel in REFERENCED:
        p = repo_root / rel
        sha, n = _sha256(p)
        referenced.append({"path": rel, "sha256": sha, "bytes": n})

    _assert_no_money(release_dir / "data" / "zone-dataset.json")

    manifest = {
        "release": RELEASE, "version": VERSION, "immutable": True,
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "decided_k": 4, "scenario": "A", "zone_edges_km": ZONE_EDGES,
        "zone_colors": ZONE_COLORS, "source_dataset_version": dataset_version,
        "prices_included": False, "direct_integration": False,
        "counts": {"objects_per_zone": summary["objects_per_zone"],
                   "streets": len(streets), "severny_objects": summary["severny_objects"],
                   "varnita_serviceable_addresses_in_zones":
                       summary["varnita_serviceable_addresses_in_zones"]},
        "readiness": summary["readiness"],
        "files": files, "referenced_artifacts": referenced,
        "notes": ("Zones only. No prices. Immutable: re-releasing bumps the "
                  "version, never edits this release. See "
                  "docs/product/ZONE_PRICING_SEPARATION.md."),
    }
    jsonutil.write(release_dir / "manifest.json", manifest)

    checksum_lines = [f"{f['sha256']}  {f['path']}" for f in files]
    (release_dir / "CHECKSUMS.sha256").write_text(
        "\n".join(checksum_lines) + "\n", encoding="utf-8", newline="\n")
    (release_dir / "IMMUTABLE").write_text(
        f"{RELEASE} {VERSION} — immutable release. Do not edit files in place; "
        "create a new versioned release instead.\n", encoding="utf-8", newline="\n")
    (release_dir / "README.md").write_text(
        f"# {RELEASE} ({VERSION})\n\n"
        "Immutable, versioned Bender delivery zones (K=4, Scenario A). Zones only,\n"
        "no prices. Vendor `data/zone-dataset.json` to resolve addresses to zones.\n"
        "Verify integrity with `sha256sum -c CHECKSUMS.sha256`. See the manifest\n"
        "and `docs/product/ZONE_PRICING_SEPARATION.md`.\n",
        encoding="utf-8", newline="\n")

    print(f"release {RELEASE} {VERSION}: {len(files)} files, "
          f"{len(referenced)} referenced, dataset_version {dataset_version}")
    print(f"  streets {len(streets)} | zones {len(zones)} | no money verified")
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo-root", default=".")
    return build(Path(ap.parse_args(argv).repo_root))


if __name__ == "__main__":
    raise SystemExit(main())
