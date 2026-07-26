"""Липканы is an ordinary microdistrict of Бендеры (owner decision)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import yaml  # noqa: E402

from bender_zones.address import (  # noqa: E402
    EXTERNAL_SETTLEMENTS,
    TERRITORY_ADDRESS,
    canonical_address_key,
    is_external_settlement,
    is_lipcani,
    normalize_admin_classification,
)

REPO = Path(__file__).resolve().parents[1]
CATALOG = REPO / "docs/data/final-address-zone-catalog.json"


def lipcani_rows():
    cat = json.loads(CATALOG.read_text("utf-8"))["addresses"]
    return [a for a in cat if is_lipcani(a.get("district_ru")) or is_lipcani(a.get("settlement_ru"))]  # noqa: E501


# --- always Бендеры / Липканы ------------------------------------------------

def test_every_lipcani_address_is_settlement_bender():
    rows = lipcani_rows()
    assert rows
    assert all(a["settlement_ru"] == "Бендеры" for a in rows)


def test_every_lipcani_address_is_district_lipcani():
    assert all(a["district_ru"] == "Липканы" for a in lipcani_rows())


def test_no_address_uses_lipcani_as_a_settlement():
    cat = json.loads(CATALOG.read_text("utf-8"))["addresses"]
    assert [a for a in cat if is_lipcani(a.get("settlement_ru"))] == []


def test_territory_map_says_bender_district():
    assert TERRITORY_ADDRESS["bender_lipcani"] == ("Бендеры", "Липканы")


def test_normalizer_rewrites_lipcani_given_as_a_settlement():
    assert normalize_admin_classification("Липканы", None) == ("Бендеры", "Липканы")
    assert normalize_admin_classification("Lipcani", None) == ("Бендеры", "Липканы")
    assert normalize_admin_classification("Бендеры", "Липкань") == ("Бендеры", "Липканы")


def test_all_known_spellings_are_recognised():
    for name in ("Липканы", "Липкань", "Липкани", "Lipcani", "Lipkani", "ЛИПКАНЫ"):
        assert is_lipcani(name), name


def test_other_districts_are_untouched_by_the_normalizer():
    assert normalize_admin_classification("Бендеры", "Северный") == ("Бендеры", "Северный")
    assert normalize_admin_classification("Парканы", None) == ("Парканы", None)


# --- not an external settlement / no city-exit multiplier -------------------

def test_lipcani_is_not_an_external_settlement():
    assert is_external_settlement("Липканы") is False
    assert "Липканы" not in EXTERNAL_SETTLEMENTS


def test_only_real_outside_settlements_are_external():
    assert set(EXTERNAL_SETTLEMENTS) == {"Гиска", "Парканы", "Протягайловка"}
    for s in EXTERNAL_SETTLEMENTS:
        assert is_external_settlement(s)


def test_territory_config_no_longer_calls_lipcani_a_suburb():
    cfg = yaml.safe_load((REPO / "config/service-trim.yml").read_text("utf-8"))
    terr = {t["key"]: t for t in cfg["territories"]}["bender_lipcani"]
    assert terr["role"] == "bender_district"
    assert terr["role"] != "bender_suburb"
    assert terr.get("settlement_ru") == "Бендеры"
    assert terr.get("district_ru") == "Липканы"
    assert "must_connect_to" not in terr           # suburb-connectivity rule removed


# --- no special pricing / status just because of the name -------------------

def test_lipcani_has_no_name_based_service_status():
    statuses = {a["service_status"] for a in lipcani_rows()}
    # only ordinary per-address outcomes; nothing invented for the district
    assert statuses <= {"standard", "low_density", "disputed", "no_delivery", "excluded"}
    assert "standard" in statuses


def test_lipcani_gets_no_separate_tariff_or_zone_edges():
    """The district entry itself must carry no money/zone knobs of its own."""
    cfg = yaml.safe_load((REPO / "config/service-trim.yml").read_text("utf-8"))
    terr = {t["key"]: t for t in cfg["territories"]}["bender_lipcani"]
    blob = " ".join(f"{k}={v}" for k, v in terr.items()).lower()
    for forbidden in ("surcharge", "multiplier", "zone_edge", "tariff", "price", "fee"):
        assert forbidden not in blob, forbidden
    # and it must not declare a delivery area / routing direction of its own
    for forbidden_key in ("owner_limits", "service_area", "zone_edges",
                          "tariff_direction", "must_connect_to"):
        assert forbidden_key not in terr, forbidden_key


# --- canonical keys stay unique and unchanged -------------------------------

def test_correction_changes_no_canonical_key():
    audit = json.loads((REPO / "docs/data/lipcani-classification-audit.json").read_text("utf-8"))
    assert audit["canonical_keys_changed"] == 0
    assert audit["duplicate_canonical_keys_after"] == audit["duplicate_canonical_keys_before"]


def test_canonical_key_ignores_district_unless_required():
    a = canonical_address_key("Бендеры", "улица Гайдара", "1", "Липканы")
    b = canonical_address_key("Бендеры", "улица Гайдара", "1", None)
    assert a == b, "a district label alone must never change an address key"


def test_canonical_key_uses_district_when_required():
    a = canonical_address_key("Бендеры", "улица Гайдара", "1", "Липканы",
                              district_required=True)
    assert "липканы" in a


# --- immutable releases untouched -------------------------------------------

def test_immutable_releases_still_carry_their_own_checksums():
    import hashlib
    for rel in ("bender-zones-v1", "bender-zones-v1.1"):
        man = REPO / "releases" / rel / "manifest.json"
        if not man.exists():
            continue
        for f in json.loads(man.read_text("utf-8"))["files"]:
            p = REPO / "releases" / rel / f["path"]
            got = hashlib.sha256(p.read_bytes()).hexdigest()
            assert got == f["sha256"], f"{rel}/{f['path']} was modified"
