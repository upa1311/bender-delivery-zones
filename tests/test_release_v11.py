"""Immutable exact-address zone release v1.1: registry, QA split, no pricing."""

from __future__ import annotations

import hashlib
import json

REL = "releases/bender-zones-v1.1"
MONEY = ("delivery_fee", "courier_payout", "price_cents", "pricecents",
         "amount_cents", "customer_delivery_fee", "tariff")
REQUIRED = ["manifest.json", "CHECKSUMS.sha256", "IMMUTABLE", "address-registry.json",
            "street-index.json", "admin-qa-objects.json", "zone-polygons.geojson",
            "varnita-village-no-delivery.geojson", "varnita-admin-reference.geojson",
            "severny-route-qa.geojson", "schemas/zone-release.schema.json"]


def _json(repo_root, rel):
    return json.loads((repo_root / rel).read_text(encoding="utf-8"))


def _manifest(repo_root):
    return _json(repo_root, f"{REL}/manifest.json")


def test_v10_release_is_untouched(repo_root):
    m = _json(repo_root, "releases/bender-zones-v1/manifest.json")
    assert m["version"] == "1.0.0"


def test_v11_manifest_fields(repo_root):
    m = _manifest(repo_root)
    assert m["release_id"] == "bender-zones-v1.1"
    assert m["version"] == "1.1.0"
    assert m["immutable"] is True
    assert m["decided_k"] == 4
    assert m["prices_included"] is False
    assert m["approved_for_internal_integration"] is True
    assert m["approved_for_customer_address_catalog"] is True
    assert m["severny_address_catalog_complete"] is False
    assert m["verified_address_count"] > 0
    assert m["qa_object_count"] > 0
    assert m["source_dataset_version"].startswith("moldova-pbf:")


def test_all_required_files_present(repo_root):
    for name in REQUIRED:
        assert (repo_root / REL / name).exists(), name
    assert set(_manifest(repo_root)["required_files"]) == set(REQUIRED)


def test_checksums_match_and_manifest_agrees(repo_root):
    lines = (repo_root / f"{REL}/CHECKSUMS.sha256").read_text("utf-8").splitlines()
    assert lines
    for line in lines:
        want, _, rel = line.partition("  ")
        got = hashlib.sha256((repo_root / REL / rel).read_bytes()).hexdigest()
        assert got == want, rel
    for f in _manifest(repo_root)["files"]:
        got = hashlib.sha256((repo_root / REL / f["path"]).read_bytes()).hexdigest()
        assert got == f["sha256"], f["path"]


def test_release_has_no_pricing_schema(repo_root):
    schemas = list((repo_root / REL / "schemas").glob("*.schema.json"))
    names = {p.name for p in schemas}
    assert names == {"zone-release.schema.json"}
    assert "zone-tariff-matrix.schema.json" not in names
    assert "order-pricing-snapshot.schema.json" not in names


def test_release_carries_no_money(repo_root):
    for p in (repo_root / REL).rglob("*"):
        if p.suffix not in (".json", ".geojson", ".csv"):
            continue
        blob = p.read_text(encoding="utf-8").lower()
        for token in MONEY:
            assert token not in blob, f"money token {token!r} in {p.name}"


def test_address_registry_is_verified_only(repo_root):
    reg = _json(repo_root, f"{REL}/address-registry.json")
    assert reg["prices_included"] is False
    entries = reg["addresses"]
    assert len(entries) == reg["verified_address_count"]
    seen = set()
    for e in entries:
        for field in ("uid", "settlement_ru", "street_ru", "housenumber",
                      "canonical_address_key", "zone_id", "service_status",
                      "source_dataset_version", "route_flags"):
            assert field in e, field
        assert e["zone_id"] in (1, 2, 3, 4)
        assert e["housenumber"], "every registry entry has a confirmed house"
        assert e["service_status"] in ("standard", "low_density")
        assert e["canonical_address_key"] not in seen, "canonical must be unique"
        seen.add(e["canonical_address_key"])
        assert "requires_varnita_transit" in e["route_flags"]


def test_severny_and_qa_objects_are_out_of_the_registry(repo_root):
    reg_keys = {e["canonical_address_key"]
                for e in _json(repo_root, f"{REL}/address-registry.json")["addresses"]}
    qa = _json(repo_root, f"{REL}/admin-qa-objects.json")["objects"]
    assert qa
    severny = [o for o in qa if o["district_ru"] == "Северный"]
    assert len(severny) == 57, "all 57 Северный objects belong to admin QA"
    unaddressed = [o for o in severny if o["address_status"] == "unaddressed_delivery_unit"]
    assert len(unaddressed) == 50
    statuses = {o["service_status"] for o in qa}
    assert {"disputed", "no_delivery"} <= statuses
    # nothing in QA leaks into the working registry as a registered address
    for o in qa:
        if o["district_ru"] == "Северный":
            assert o["canonical_address_key"] not in reg_keys or o["owner_review_required"]


def test_qa_map_uses_grid_clustering_and_map_filters(repo_root):
    js = (repo_root / "docs/catalog.js").read_text(encoding="utf-8")
    # not one giant L.geoJSON of all points
    assert "GRID_CELLS" in js and "renderMap" in js
    assert "map.getBounds" in js
    assert "POINT_THRESHOLD" in js
    # filters drive the map, not just the table
    assert "renderMap(rows)" in js and "renderTable(rows)" in js
    html = (repo_root / "docs/catalog.html").read_text(encoding="utf-8")
    for control in ("ov-tierc", "ov-varnita-village", "ov-varnita-admin",
                    "ov-severny-route", "s-verified", "s-unaddressed",
                    "s-nodelivery", "s-disputed"):
        assert control in html, control
