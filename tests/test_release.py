"""Immutable versioned zone release: integrity, checksums, no money."""

from __future__ import annotations

import hashlib
import json

REL = "releases/bender-zones-v1"
MONEY = ("delivery_fee", "courier_payout", "courier_base_payout", "pricecents",
         "price_cents", "amount_cents", "customer_delivery_fee")


def _json(repo_root, rel):
    return json.loads((repo_root / rel).read_text(encoding="utf-8"))


def _manifest(repo_root):
    return _json(repo_root, f"{REL}/manifest.json")


def test_release_manifest_is_immutable_and_priceless(repo_root):
    m = _manifest(repo_root)
    assert m["release"] == "bender-zones-v1"
    assert m["immutable"] is True
    assert m["prices_included"] is False
    assert m["direct_integration"] is False
    assert m["decided_k"] == 4
    assert m["zone_edges_km"] == [2.424, 4.076, 5.577, 9.692]


def test_release_checksums_match(repo_root):
    lines = (repo_root / f"{REL}/CHECKSUMS.sha256").read_text("utf-8").splitlines()
    assert lines
    for line in lines:
        want, _, rel = line.partition("  ")
        got = hashlib.sha256((repo_root / REL / rel).read_bytes()).hexdigest()
        assert got == want, f"checksum mismatch: {rel}"


def test_manifest_file_hashes_match_disk(repo_root):
    for f in _manifest(repo_root)["files"]:
        got = hashlib.sha256((repo_root / REL / f["path"]).read_bytes()).hexdigest()
        assert got == f["sha256"], f["path"]


def test_referenced_artifacts_are_checksummed(repo_root):
    for ref in _manifest(repo_root)["referenced_artifacts"]:
        got = hashlib.sha256((repo_root / ref["path"]).read_bytes()).hexdigest()
        assert got == ref["sha256"], ref["path"]


def test_vendorable_dataset_shape(repo_root):
    d = _json(repo_root, f"{REL}/data/zone-dataset.json")
    assert d["immutable"] is True and d["prices_included"] is False
    assert d["decided_k"] == 4 and d["scenario"] == "A"
    zone_ids = {z["zone_id"] for z in d["zones"]}
    assert zone_ids == {1, 2, 3, 4}
    assert any(z["component"] == "severny_enclave" for z in d["zones"])
    streets = d["resolution_index"]["streets"]
    assert streets
    for s in streets[:50]:
        assert s["settlement_ru"] and s["street_ru"]
        assert isinstance(s["split_street"], bool)


def test_release_data_contains_no_money(repo_root):
    """The zone DATA carries no money. Schemas may NAME money fields (the tariff
    contract), but only with null values — checked separately below."""
    for p in (repo_root / REL / "data").rglob("*"):
        if p.suffix not in (".json", ".geojson", ".csv"):
            continue
        blob = p.read_text(encoding="utf-8").lower()
        for token in MONEY:
            assert token not in blob, f"money token {token!r} in {p.name}"


def test_tariff_schema_money_fields_default_to_null(repo_root):
    schema = _json(repo_root, f"{REL}/schemas/zone-tariff-matrix.schema.json")
    props = schema["$defs"]["tariffRow"]["properties"]
    for field in ("customer_delivery_fee", "courier_base_payout",
                  "courier_distance_adjustment"):
        assert props[field]["default"] is None, field
    example = schema["examples"][0]
    assert example["currency"] is None
    for row in example["rows"]:
        assert row["customer_delivery_fee"] is None


def test_immutable_marker_and_schemas_present(repo_root):
    assert (repo_root / f"{REL}/IMMUTABLE").exists()
    for name in ("zone-dataset", "address-zone-lookup", "zone-tariff-matrix",
                 "order-pricing-snapshot"):
        assert (repo_root / f"{REL}/schemas/{name}.schema.json").exists(), name


def test_separation_doc_states_the_rule(repo_root):
    text = (repo_root / "docs/product/ZONE_PRICING_SEPARATION.md").read_text("utf-8").lower()
    assert "zones" in text and "no money" in text
    assert "immutable" in text
    assert "null" in text
    assert "tariff" in text
