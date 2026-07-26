"""Кишинёвская: per-house recalculation, scoped zone move, nothing else touched."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
D = REPO / "docs/data"
STREET = "Кишинёвская улица"
EDGES = [2.424, 4.076, 5.577, 9.692]


def calc():
    return list(csv.DictReader((D / "kishinevskaya-recalculation.csv").open(encoding="utf-8")))


def audit():
    return list(csv.DictReader((D / "kishinevskaya-zone-change-audit.csv").open(encoding="utf-8")))


def overlay():
    return json.loads((D / "zone-corrections-pending.json").read_text("utf-8"))


def points():
    return [f["properties"] for f in
            json.loads((D / "final-address-zone-points.geojson").read_text("utf-8"))["features"]]


def street_houses():
    return [p for p in points()
            if (p.get("street_ru") or "") == STREET
            and p.get("address_status") == "verified_osm_address" and p.get("housenumber")]


# --- the anchor question -----------------------------------------------------

def test_our_house_1_exists_and_house_13_does_not():
    nums = {p["housenumber"] for p in street_houses()}
    assert "1" in nums
    assert "13" not in nums, "Yandex's 'Кишинёвская 13' has no counterpart in our base"


def test_the_tested_coordinate_is_our_house_1():
    h1 = next(p for p in street_houses() if p["housenumber"] == "1")
    assert h1["uid"] == "w209267167"


def test_anchor_rows_are_flagged_as_the_same_road_segment():
    flags = {r["address_anchor_status"] for r in calc()}
    assert "SAME_ROAD_SEGMENT_AS_YANDEX_LABEL" in flags


# --- per-house, never a blanket street zone ---------------------------------

def test_every_exact_house_is_recalculated_individually():
    assert len(calc()) == len(street_houses()) == 23


def test_the_street_is_not_given_one_blanket_zone():
    """Per-house handling: the corrections do not cover every house identically."""
    o = overlay()
    corrected = {c["uid"] for c in o["corrections"]}
    all_uids = {p["uid"] for p in street_houses()}
    assert corrected < all_uids, "a split street must not be corrected wholesale"


def test_candidate_zone_follows_the_corrected_distance():
    for r in calc():
        if not r["corrected_weighted_km"]:
            continue
        km = float(r["corrected_weighted_km"])
        expected = next((i + 1 for i, e in enumerate(EDGES) if km <= e), 4)
        assert int(r["candidate_new_zone"]) == expected, r["housenumber"]


def test_corrected_distance_is_shorter_than_the_old_duration_based_value():
    for r in calc():
        if r["corrected_weighted_km"] and r["old_distance_km"]:
            assert float(r["corrected_weighted_km"]) <= float(r["old_distance_km"])


# --- the applied move is exactly what was authorised ------------------------

def test_only_zone_4_to_zone_3_moves_were_recorded():
    for a in audit():
        assert int(a["old_zone"]) == 4
        assert int(a["new_zone"]) == 3


def test_no_house_was_jumped_two_zones_on_our_own_initiative():
    for a in audit():
        if int(a["computed_zone"]) != 3:
            assert a["borderline"].startswith("да")
            assert int(a["new_zone"]) == 3


def test_house_54_zone_2_is_not_in_the_corrections():
    h = next(p for p in street_houses() if p["housenumber"] == "54")
    assert h["zone_id"] == 2
    assert h["uid"] not in {c["uid"] for c in overlay()["corrections"]}


def test_the_correction_is_an_overlay_not_an_in_place_edit():
    """bender-zones-v1 pins the working artifacts by SHA-256, so they must not be
    rewritten; the fix has to travel as an overlay into the NEXT release."""
    o = overlay()
    assert len(o["corrections"]) == len(audit()) == 22
    assert o["authorised_move"] == "Zone 4 -> Zone 3"
    assert o["prices_tariffs_direct_changed"] is False
    assert o["other_districts_changed"] is False
    assert "duration" in o["basis"]
    for c in o["corrections"]:
        assert c["street_ru"] == STREET
        assert c["old_zone_id"] == 4 and c["new_zone_id"] == 3


def test_pinned_working_artifacts_still_match_the_release_reference():
    import hashlib
    man = json.loads((REPO / "releases/bender-zones-v1/manifest.json").read_text("utf-8"))
    for ref in man.get("referenced_artifacts", []):
        p = REPO / ref["path"]
        got = hashlib.sha256(p.read_bytes()).hexdigest()
        assert got == ref["sha256"], ref["path"]


# --- nothing outside Кишинёвская changed ------------------------------------

def test_no_other_street_appears_in_the_corrections():
    for c in overlay()["corrections"]:
        assert c["street_ru"] == STREET


def test_immutable_releases_are_unchanged():
    for rel in ("bender-zones-v1", "bender-zones-v1.1"):
        man = REPO / "releases" / rel / "manifest.json"
        if not man.exists():
            continue
        for f in json.loads(man.read_text("utf-8"))["files"]:
            p = REPO / "releases" / rel / f["path"]
            assert hashlib.sha256(p.read_bytes()).hexdigest() == f["sha256"], f["path"]
