"""Duplicate-key normalization: only NFKC/trim/collapse/casefold."""

from __future__ import annotations

from bender_zones.normalize import address_key, normalize_text


def test_trim_and_collapse_whitespace():
    assert normalize_text("  Strada   Mare  ") == "strada mare"


def test_casefold_unifies_case():
    assert normalize_text("ЛЕНИНА") == normalize_text("ленина")


def test_nfkc_normalizes_compatibility_forms():
    # Fullwidth digits (NFKC) collapse to ASCII digits.
    assert normalize_text("１０") == "10"


def test_no_transliteration():
    # Cyrillic must NOT be transliterated to Latin.
    assert normalize_text("Ленина") == "ленина"
    assert normalize_text("Ленина") != "lenina"


def test_address_key_collapses_trailing_space_duplicate():
    assert address_key("Ленина", "10") == address_key("ленина  ", "10")


def test_address_key_distinct_when_number_differs():
    assert address_key("Ленина", "10") != address_key("Ленина", "7")
