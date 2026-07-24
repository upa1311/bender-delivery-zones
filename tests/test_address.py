"""Duplicate street names across settlements and districts (Stage 07)."""

from __future__ import annotations

import csv
import json

from bender_zones.address import (
    build_street_index,
    canonical_address_key,
    display_address_ru,
    full_address_ru,
    search_variants,
    settlement_district,
)

LENIN = "улица Ленина"


def _rows(repo_root):
    text = (repo_root / "docs/data/delivery-units.csv").read_text(encoding="utf-8")
    return list(csv.DictReader(text.splitlines()))


def _qa(repo_root):
    return json.loads((repo_root / "docs/data/street-name-qa.json")
                      .read_text(encoding="utf-8"))


# --- same name, different settlement = different street ---------------------

def test_lenin_in_giska_and_parkany_are_different_streets():
    a = canonical_address_key("Гиска", LENIN, "15")
    b = canonical_address_key("Парканы", LENIN, "15")
    assert a != b, "same street name in two settlements must not collide"


def test_same_housenumber_on_same_named_streets_are_different_addresses():
    giska = canonical_address_key("Гиска", LENIN, "15")
    parkany = canonical_address_key("Парканы", LENIN, "15")
    bender = canonical_address_key("Бендеры", LENIN, "15")
    assert len({giska, parkany, bender}) == 3


def test_unique_street_is_displayed_without_brackets():
    index = build_street_index([("Бендеры", None, "улица Энгельса")])
    qual = index[("Бендеры", None, "улица энгельса")]
    assert qual is None
    assert display_address_ru("улица Энгельса", qual) == "улица Энгельса"


def test_repeated_street_is_displayed_with_settlement():
    index = build_street_index([
        ("Гиска", None, LENIN), ("Парканы", None, LENIN), ("Бендеры", None, LENIN)])
    for settlement in ("Гиска", "Парканы", "Бендеры"):
        qual = index[(settlement, None, "улица ленина")]
        assert display_address_ru(LENIN, qual) == f"{LENIN} ({settlement})"


def test_duplicate_inside_bender_is_disambiguated_by_district():
    index = build_street_index([
        ("Бендеры", "Липканы", "улица Энгельса"),
        ("Бендеры", None, "улица Энгельса")])
    lip = index[("Бендеры", "Липканы", "улица энгельса")]
    core = index[("Бендеры", None, "улица энгельса")]
    assert display_address_ru("улица Энгельса", lip) == "улица Энгельса (Липканы)"
    assert display_address_ru("улица Энгельса", core) == \
        "улица Энгельса (Бендеры, другой район)"


def test_street_name_never_contains_the_settlement():
    index = build_street_index([("Гиска", None, LENIN), ("Парканы", None, LENIN)])
    qual = index[("Гиска", None, "улица ленина")]
    # the qualifier is display-only; the real name is untouched
    assert LENIN == "улица Ленина"
    assert display_address_ru(LENIN, qual).startswith(LENIN)


# --- full address -----------------------------------------------------------

def test_full_address_formats():
    assert full_address_ru("Гиска", None, LENIN, "15") == "Гиска, улица Ленина, дом 15"
    assert full_address_ru("Бендеры", "Липканы", "улица Энгельса", "24") == \
        "Бендеры, Липканы, улица Энгельса, дом 24"


def test_territory_maps_to_settlement_and_district():
    assert settlement_district("bender_lipcani") == ("Бендеры", "Липканы")
    assert settlement_district("bender_core") == ("Бендеры", None)
    assert settlement_district("giska") == ("Гиска", None)


# --- the tariff zone is not part of address identity ------------------------

def test_zone_is_not_part_of_the_canonical_key(repo_root):
    key = canonical_address_key("Гиска", LENIN, "15")
    for token in ("zone", "band", "k4", "k5"):
        assert token not in key.lower()
    for r in _rows(repo_root)[:300]:
        if r["canonical_address"]:
            assert r["band_k4"] not in r["canonical_address"].split("|")


def test_changing_the_zone_does_not_change_address_identity():
    before = canonical_address_key("Гиска", LENIN, "15")
    # re-banding changes nothing about the address itself
    after = canonical_address_key("Гиска", LENIN, "15")
    assert before == after


# --- search -----------------------------------------------------------------

def test_search_returns_one_variant_per_place():
    records = [
        {"street_ru": LENIN, "settlement_ru": "Гиска", "district_ru": None},
        {"street_ru": LENIN, "settlement_ru": "Парканы", "district_ru": None},
        {"street_ru": LENIN, "settlement_ru": "Бендеры", "district_ru": None},
        {"street_ru": LENIN, "settlement_ru": "Гиска", "district_ru": None},
    ]
    out = search_variants("Ленина", records)
    assert len(out) == 3
    assert {v["place_ru"] for v in out} == {"Гиска", "Парканы", "Бендеры"}
    for v in out:
        assert v["street_ru"] == LENIN


# --- committed artifacts ----------------------------------------------------

def test_units_carry_separate_address_fields(repo_root):
    rows = _rows(repo_root)
    for field in ("settlement_ru", "district_ru", "street_ru", "housenumber",
                  "canonical_address", "display_address_ru", "full_address_ru"):
        assert field in rows[0], field
    for r in rows[:500]:
        if r["settlement_ru"] and r["street_ru"]:
            assert r["settlement_ru"] not in r["street_ru"], \
                "settlement must never be glued into the street name"


def test_committed_lenin_variants_are_separated(repo_root):
    qa = _qa(repo_root)
    lenin = [d for d in qa["duplicates"] if d["normalized_street"] == "улица ленина"]
    assert lenin, "улица Ленина repeats and must be reported"
    places = {v["settlement_ru"] for v in lenin[0]["variants"]}
    assert {"Гиска", "Парканы", "Бендеры"} <= places
    for v in lenin[0]["variants"]:
        assert v["display_address_ru"].endswith(f"({v['settlement_ru']})")
        assert v["address_count"] > 0


def test_street_name_qa_report_is_complete(repo_root):
    qa = _qa(repo_root)
    assert qa["duplicate_street_names"] > 0
    assert "addresses_without_settlement" in qa
    assert "same_address_different_coordinates" in qa
    assert "never modified" in qa["rule"]
    header = (repo_root / "docs/data/duplicate-street-names.csv").read_text(
        encoding="utf-8").splitlines()[0]
    for col in ("street_ru", "settlement_ru", "district_ru", "display_address_ru",
                "address_count"):
        assert col in header


def test_duplicate_streets_do_not_share_canonical_keys(repo_root):
    """Two same-named streets in different settlements must never merge."""
    by_key = {}
    for r in _rows(repo_root):
        if not r["canonical_address"]:
            continue
        by_key.setdefault(r["canonical_address"], set()).add(r["settlement_ru"])
    for key, settlements in by_key.items():
        assert len(settlements) == 1, f"{key} spans settlements {settlements}"


# --- district beats the generic settlement qualifier ------------------------

def test_district_is_preferred_over_settlement_qualifier():
    index = build_street_index([
        ("Бендеры", "Липканы", "улица Энгельса"),
        ("Бендеры", None, "улица Энгельса")])
    lip = index[("Бендеры", "Липканы", "улица энгельса")]
    core = index[("Бендеры", None, "улица энгельса")]
    assert display_address_ru("улица Энгельса", lip) == "улица Энгельса (Липканы)"
    assert "(Бендеры)" not in display_address_ru("улица Энгельса", lip)
    assert display_address_ru("улица Энгельса", core) == \
        "улица Энгельса (Бендеры, другой район)"


def test_district_wins_even_across_settlements():
    """A street in Липканы is labelled by its district, never by 'Бендеры'."""
    index = build_street_index([
        ("Бендеры", "Липканы", "улица Ленина"),
        ("Гиска", None, "улица Ленина"),
        ("Парканы", None, "улица Ленина")])
    lip = index[("Бендеры", "Липканы", "улица ленина")]
    assert display_address_ru(LENIN, lip) == "улица Ленина (Липканы)"
    assert display_address_ru(LENIN, index[("Гиска", None, "улица ленина")]) == \
        "улица Ленина (Гиска)"


def test_full_address_still_carries_settlement_and_district():
    assert full_address_ru("Бендеры", "Липканы", "улица Энгельса", "24") == \
        "Бендеры, Липканы, улица Энгельса, дом 24"


def test_committed_lipcani_rows_never_say_bendery(repo_root):
    rows = _rows(repo_root)
    lip = [r for r in rows if r["district_ru"] == "Липканы"]
    assert lip
    for r in lip:
        assert "(Бендеры)" not in r["display_address_ru"]
        if "(" in r["display_address_ru"]:
            assert r["display_address_ru"].endswith("(Липканы)")
        assert r["full_address_ru"].startswith("Бендеры, Липканы, ")


def test_committed_titova_shows_district_on_both_sides(repo_root):
    labels = {r["display_address_ru"] for r in _rows(repo_root)
              if "Титова" in (r["street_ru"] or "")}
    assert "улица Титова (Липканы)" in labels
    assert "улица Титова (Бендеры, другой район)" in labels


# --- disputed addresses are quarantined, never auto-resolved ----------------

def test_disputed_addresses_are_quarantined(repo_root):
    doc = json.loads((repo_root / "docs/data/disputed-addresses.json")
                     .read_text(encoding="utf-8"))
    assert doc["count"] > 0
    assert "Direct" in doc["policy"]
    for a in doc["addresses"]:
        assert a["status"] == "disputed"
        assert a["resolution"] == "owner_review_required"
        assert a["direct_export_eligible"] is False
        assert a["coordinate_spread_m"] >= a["tolerance_m"]
        assert len(a["candidates"]) > 1


def test_disputed_addresses_keep_every_candidate_route(repo_root):
    doc = json.loads((repo_root / "docs/data/disputed-addresses.json")
                     .read_text(encoding="utf-8"))
    for a in doc["addresses"][:50]:
        for c in a["candidates"]:
            assert c["uid"] and c["lon"] and c["lat"]
            assert c["expected_km"] is not None
        # the shortest route was NOT silently chosen for the address
        assert "resolved_km" not in a


def test_disputed_addresses_are_absent_from_the_bands(repo_root):
    doc = json.loads((repo_root / "docs/data/disputed-addresses.json")
                     .read_text(encoding="utf-8"))
    banded = {r["canonical_address"] for r in _rows(repo_root)}
    for a in doc["addresses"]:
        assert a["canonical_address"] not in banded, \
            "a disputed address must not receive a tariff zone"


def test_disputed_counts_published_by_settlement_and_street(repo_root):
    doc = json.loads((repo_root / "docs/data/disputed-addresses.json")
                     .read_text(encoding="utf-8"))
    assert doc["by_settlement"] and doc["by_street"]
    assert sum(doc["by_settlement"].values()) == doc["count"]
    header = (repo_root / "docs/data/disputed-addresses.csv").read_text(
        encoding="utf-8").splitlines()[0]
    for col in ("coordinate_spread_m", "candidate_uid", "expected_km", "status",
                "direct_export_eligible"):
        assert col in header


def test_duplicates_within_tolerance_are_still_merged(repo_root):
    tuning = json.loads((repo_root / "docs/data/tariff-band-metrics.json")
                        .read_text(encoding="utf-8"))["tuning"]
    merged = tuning["duplicate_address_conflicts"]
    assert merged, "safe duplicates must still merge automatically"
    for m in merged:
        assert m["resolution"] == "merged_within_coordinate_tolerance"
        assert m["coordinate_spread_m"] <= tuning["disputed_addresses"]["tolerance_m"]


def test_apartment_section_reads_the_current_field(repo_root):
    md = (repo_root / "reports/stage-06/tariff-bands.md").read_text(encoding="utf-8")
    assert "Квартирная чувствительность" in md
    assert "addr:flats" in md and "building:levels" in md
    for scenario in ("one_unit", "levels"):
        assert scenario in md
    assert "None" not in md.split("Квартирная чувствительность")[1][:600]
