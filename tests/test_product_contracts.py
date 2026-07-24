"""Product contracts for the future Direct integration (docs + JSON Schemas).

Nothing here integrates with Direct and no price is assigned; the tests guard the
contracts' shape and the no-money / K=4 guarantees.
"""

from __future__ import annotations

import json

SCHEMAS = ["address-zone-lookup", "zone-tariff-matrix", "order-pricing-snapshot"]
MATRIX_FIELDS = ["origin_zone_id", "destination_zone_id", "customer_delivery_fee",
                 "courier_base_payout", "courier_distance_adjustment", "currency",
                 "effective_from", "effective_to", "status", "version", "changed_by",
                 "change_reason"]
SNAPSHOT_FIELDS = ["zone_dataset_version", "tariff_version", "origin_zone_id",
                   "destination_zone_id", "route_distance_km", "route_duration_min",
                   "customer_delivery_fee", "courier_payout", "calculation_components"]


def _schema(repo_root, name):
    return json.loads((repo_root / "schemas" / f"{name}.schema.json")
                      .read_text(encoding="utf-8"))


def test_all_schemas_exist_and_are_valid_json(repo_root):
    for name in SCHEMAS:
        s = _schema(repo_root, name)
        assert s["$schema"].startswith("https://json-schema.org/")
        assert s["title"] and s["description"]


def test_lookup_is_keyed_on_the_exact_address_not_the_street(repo_root):
    s = _schema(repo_root, "address-zone-lookup")
    modes = s["properties"]["query"]["properties"]["mode"]["enum"]
    assert "exact_address" in modes and "street_only" in modes
    statuses = s["properties"]["resolution"]["properties"]["status"]["enum"]
    assert "ambiguous_street" in statuses, \
        "a street-only query must be answerable as ambiguous, not one zone_id"
    addr = s["$defs"]["addressZone"]["properties"]
    for field in ("canonical_address_key", "display_address_ru", "full_address_ru",
                  "settlement_ru", "district_ru", "street_ru", "housenumber"):
        assert field in addr, field
    assert "assignment_basis" in addr and "zone_dataset_version" in addr


def test_lookup_exposes_routing_basis_and_service_status(repo_root):
    addr = _schema(repo_root, "address-zone-lookup")["$defs"]["addressZone"]["properties"]
    basis = addr["assignment_basis"]["properties"]
    for field in ("expected_km", "central_origin", "bam_origin", "tier"):
        assert field in basis, field
    assert "no_delivery" in addr["service_status"]["enum"]


def test_tariff_matrix_is_4x4_and_directional(repo_root):
    s = _schema(repo_root, "zone-tariff-matrix")
    assert s["properties"]["zone_set"]["properties"]["k"]["const"] == 4
    rows = s["properties"]["rows"]
    assert rows["minItems"] == 16 and rows["maxItems"] == 16
    props = s["$defs"]["tariffRow"]["properties"]
    for field in MATRIX_FIELDS:
        assert field in props, field


def test_tariff_matrix_assigns_no_money(repo_root):
    s = _schema(repo_root, "zone-tariff-matrix")
    props = s["$defs"]["tariffRow"]["properties"]
    for field in ("customer_delivery_fee", "courier_base_payout",
                  "courier_distance_adjustment", "currency"):
        assert props[field]["default"] is None, field
        assert "null" in props[field]["type"]
    example = s["examples"][0]
    assert example["currency"] is None
    for row in example["rows"]:
        assert row["customer_delivery_fee"] is None
        assert row["courier_base_payout"] is None


def test_customer_fee_and_courier_payout_are_separate(repo_root):
    snap = _schema(repo_root, "order-pricing-snapshot")["properties"]
    assert "customer_delivery_fee" in snap and "courier_payout" in snap
    assert "separately" in snap["courier_payout"]["description"]


def test_order_snapshot_is_immutable_and_complete(repo_root):
    s = _schema(repo_root, "order-pricing-snapshot")
    props = s["properties"]
    for field in SNAPSHOT_FIELDS:
        assert field in props, field
    assert props["immutable"]["const"] is True
    assert "never" in props["immutable"]["description"].lower()
    assert "later" in s["description"].lower()


def test_snapshot_records_the_routing_engine(repo_root):
    engine = _schema(repo_root, "order-pricing-snapshot")["properties"][
        "routing_engine"]["properties"]
    assert engine["name"]["const"] == "OSRM"
    assert engine["algorithm"]["const"] == "MLD"
    for field in ("profile_sha256", "source_pbf_sha256"):
        assert field in engine


def test_product_docs_exist_and_state_the_guardrails(repo_root):
    for name in ("admin-zone-console", "driver-price-explanation"):
        text = (repo_root / "docs/product" / f"{name}.md").read_text(encoding="utf-8")
        assert "K=4" in text
        assert "Direct" in text
        assert "не назначены" in text
        assert "не интегрирован" in text


def test_admin_doc_covers_the_required_screens(repo_root):
    text = (repo_root / "docs/product/admin-zone-console.md").read_text(encoding="utf-8")
    for needle in ("улица Ленина (Гиска)", "улица Ленина (Парканы)",
                   "ambiguous_street", "no_delivery", "Tier C",
                   "zone_dataset_version", "улица Энгельса (Липканы)"):
        assert needle in text, needle


def test_driver_doc_shows_both_amounts_and_the_matrix_row(repo_root):
    text = (repo_root / "docs/product/driver-price-explanation.md").read_text(
        encoding="utf-8")
    for needle in ("Zone 1 → Zone 3", "Выплата водителю", "Стоимость доставки",
                   "tariff_version", "immutable"):
        assert needle in text, needle
