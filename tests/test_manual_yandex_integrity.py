"""Integrity of the manual-Yandex control set, ids and measurements."""

from __future__ import annotations

import csv
import importlib.util
import json
import math
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
D = REPO / "docs/data"
TOL_M = 60.0
FOURTH_BATCH_IDS = [
    "MY-052", "MY-053", "MY-054", "MY-057", "MY-058",
    "MY-059", "MY-060", "MY-062", "MY-063", "MY-064",
    "MY-065", "MY-066", "MY-067", "MY-068", "MY-069",
]

REBUILD_SPEC = importlib.util.spec_from_file_location(
    "rebuild_manual_yandex_outputs",
    REPO / "scripts/rebuild_manual_yandex_outputs.py",
)
assert REBUILD_SPEC and REBUILD_SPEC.loader
REBUILD = importlib.util.module_from_spec(REBUILD_SPEC)
REBUILD_SPEC.loader.exec_module(REBUILD)


def controls():
    return list(csv.DictReader((D / "manual-yandex-route-controls.csv").open(encoding="utf-8")))


def measurements():
    return list(csv.DictReader((D / "manual-yandex-measurements.csv").open(encoding="utf-8")))


def migration():
    return list(csv.DictReader(
        (D / "manual-yandex-control-id-migration.csv").open(encoding="utf-8")))


def checkpoint():
    return json.loads((REPO / "data/interim/manual-yandex-checkpoint.json").read_text("utf-8"))


def hav_m(a, b, c, d):
    R = 6371008.8
    p1, p2 = math.radians(a), math.radians(c)
    dp, dl = math.radians(c - a), math.radians(d - b)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


# --- exactly 86 unique control points ---------------------------------------

def test_there_are_exactly_86_control_points():
    assert len(controls()) == 86


def test_every_control_id_is_unique():
    ids = [c["control_id"] for c in controls()]
    assert len(set(ids)) == len(ids) == 86


def test_control_coordinates_are_distinct():
    coords = [(c["destination_lat"], c["destination_lon"]) for c in controls()]
    assert len(set(coords)) == len(coords)


# --- no duplicate ids among measurements ------------------------------------

def test_no_duplicate_control_id_in_measurements():
    dups = [k for k, v in Counter(m["control_id"] for m in measurements()).items() if v > 1]
    assert dups == [], dups


def test_the_old_my_002_collision_is_gone():
    rows = [m for m in measurements() if m["control_id"] == "MY-002"]
    assert len(rows) == 1
    assert "Кишинёвская" in rows[0]["label"]


def test_migration_records_the_my_002_split():
    moved = [r for r in migration() if r["old_control_id"] != r["new_control_id"]]
    assert moved, "the repair must be recorded"
    assert any(r["old_control_id"] == "MY-002" and "Титова" in r["label"] for r in moved)
    for r in moved:
        assert r["reason"].strip()


def test_migration_is_a_historical_repair_log():
    """It records every id that CHANGED (and keeps them across re-runs); it is not
    a per-measurement index, so it must not be regenerated empty."""
    rows = migration()
    assert rows, "the repair history must survive a re-run"
    changed = [r for r in rows if r["old_control_id"] != r["new_control_id"]]
    assert changed, "at least the MY-002 split must stay on record"
    for r in changed:
        assert r["reason"].strip()
        assert r["destination_lat"] and r["destination_lon"]


def test_every_renamed_id_is_still_present_in_the_measurements():
    current = {m["control_id"] for m in measurements()}
    for r in migration():
        if r["old_control_id"] != r["new_control_id"]:
            assert r["new_control_id"] in current, r["new_control_id"]


# --- one measurement <-> one control, coordinates agree ---------------------

def test_each_measurement_maps_to_at_most_one_control():
    cids = {c["control_id"] for c in controls()}
    mapped = [m["control_id"] for m in measurements() if m["control_id"] in cids]
    assert len(set(mapped)) == len(mapped)


def test_measurement_coordinates_match_their_control_point():
    byid = {c["control_id"]: c for c in controls()}
    for m in measurements():
        c = byid.get(m["control_id"])
        if not c:
            continue           # an extra landmark row, outside the 86
        d = hav_m(float(m["destination_lat"]), float(m["destination_lon"]),
                  float(c["destination_lat"]), float(c["destination_lon"]))
        assert d <= TOL_M, f"{m['control_id']} is {d:.0f} m from its control point"


def test_rows_outside_the_86_are_marked_as_extra():
    cids = {c["control_id"] for c in controls()}
    for m in measurements():
        if m["control_id"] not in cids:
            assert m["control_id"].startswith("MY-X"), m["control_id"]


def test_no_duplicate_measurement_coordinates():
    coords = [(m["destination_lat"], m["destination_lon"]) for m in measurements()]
    assert len(set(coords)) == len(coords)


# --- counts are derived, never typed in -------------------------------------

def test_checkpoint_counts_are_consistent_with_the_files():
    cp = checkpoint()
    cids = {c["control_id"] for c in controls()}
    measured = {m["control_id"] for m in measurements() if m["control_id"] in cids}
    assert cp["total_controls"] == len(controls()) == 86
    assert cp["measured_controls"] == len(measured)
    assert cp["remaining_controls"] == 86 - len(measured)
    assert cp["measured_controls"] + cp["remaining_controls"] == cp["total_controls"]


def test_checkpoint_next_ids_are_genuinely_unmeasured():
    cp = checkpoint()
    measured = {m["control_id"] for m in measurements()}
    for cid in cp["next_control_ids"]:
        assert cid not in measured


def test_measurements_carry_real_numbers_not_placeholders():
    for m in measurements():
        assert float(m["yandex_fastest_distance_km"]) > 0
        assert float(m["yandex_fastest_duration_min"]) > 0
        assert m["checked_date"]


# --- batch-2 fixes: checkpoint, discrepancies, evidence-based entries -------

def entries():
    return list(csv.DictReader((D / "manual-yandex-confirmed-entries.csv").open(encoding="utf-8")))


def discrepancies():
    return list(csv.DictReader(
        (D / "manual-yandex-address-discrepancies.csv").open(encoding="utf-8")))


def test_last_completed_id_comes_from_the_last_appended_batch():
    cp = checkpoint()
    rows = measurements()
    cids = {c["control_id"] for c in controls()}
    in_set = [r for r in rows if r["control_id"] in cids]
    last_date = in_set[-1]["checked_date"]
    last_batch = []
    for row in reversed(in_set):
        if row["checked_date"] != last_date:
            break
        last_batch.append(row)
    last_batch.reverse()
    assert cp["last_completed_control_id"] == last_batch[-1]["control_id"]
    assert cp["last_batch_size"] == len(last_batch)
    assert cp["last_batch_checked_date"] == last_date


def test_progress_is_72_of_86_with_14_remaining():
    cp = checkpoint()
    assert (cp["total_controls"], cp["measured_controls"], cp["remaining_controls"]) \
        == (86, 72, 14)
    assert cp["blocked_controls"] == 0
    assert cp["extra_landmark_measurements"] == 4
    assert cp["last_completed_control_id"] == "MY-069"


def test_the_fourth_batch_holds_exactly_15_filled_routes():
    rows = measurements()
    batch = rows[-15:]
    assert [r["control_id"] for r in batch] == FOURTH_BATCH_IDS
    assert len(batch) == 15
    for r in batch:
        assert float(r["yandex_fastest_distance_km"]) > 0
        assert float(r["yandex_shortest_distance_km"]) > 0
        assert float(r["yandex_fastest_duration_min"]) > 0
        assert float(r["yandex_shortest_duration_min"]) > 0
        assert int(r["yandex_variant_count"]) >= 1
        assert r["manual_entry_method"] == "EMPTY"
        assert r["manual_entry_confidence"] == "UNKNOWN"
        assert r["yandex_district_entry"] == "UNKNOWN_REQUIRES_MAP_REVIEW"


def test_every_explicit_address_mismatch_is_recorded():
    recorded = {d["control_id"] for d in discrepancies()}
    for cid in ("MY-006", "MY-007", "MY-013", "MY-014", "MY-016", "MY-019"):
        assert cid in recorded, cid


def test_house_number_mismatches_are_flagged_as_such():
    by = {d["control_id"]: d["flag"] for d in discrepancies()}
    assert "HOUSE_NUMBER_DISAGREEMENT" in by.get("MY-014", "")
    assert "HOUSE_NUMBER_DISAGREEMENT" in by.get("MY-019", "")


def test_confirmed_entries_contain_no_unknown():
    for e in entries():
        assert e["confidence"] == "CONFIRMED"
        assert e["confirmed_entry_street"] != "UNKNOWN_REQUIRES_MAP_REVIEW"


def test_entry_is_never_the_destination_street_without_evidence():
    for r in measurements():
        entry = r["yandex_district_entry"]
        if entry == "UNKNOWN_REQUIRES_MAP_REVIEW":
            assert r["yandex_district_entry_confidence"] == "UNKNOWN"
            continue
        assert r["yandex_district_entry_evidence"].strip(), r["control_id"]


def test_destination_street_and_entry_are_separate_fields():
    cols = measurements()[0].keys()
    for c in ("yandex_destination_street", "yandex_district_entry",
              "yandex_main_streets", "yandex_district_entry_confidence"):
        assert c in cols


# --- entries are observed, never inferred from a shared street name ---------

ORIGIN_STREETS = ("улица Сергея Лазо", "улица Суворова", "Первомайская улица",
                  "Коммунистическая улица")


def test_no_entry_is_inferred_from_a_globally_matching_street_name():
    """A different OSM segment carrying the same name elsewhere proves nothing."""
    for e in entries():
        assert e["entry_method"] == "MANUAL_MAP_OBSERVATION", e["control_id"]


def test_sergeya_lazo_is_not_a_confirmed_entry_to_parkany():
    for e in entries():
        if e["district"] == "Парканы":
            assert e["confirmed_entry_street"] != "улица Сергея Лазо"


def test_pervomayskaya_is_not_a_confirmed_entry_to_protyagailovka_without_evidence():
    for e in entries():
        if e["district"] == "Протягайловка":
            assert e["confirmed_entry_street"] != "Первомайская улица"                 or e["entry_evidence"].strip()  # noqa: E501


def test_a_bender_origin_street_is_never_a_confirmed_entry_elsewhere():
    for e in entries():
        if e["district"] in ("Парканы", "Гиска", "Протягайловка"):
            assert e["confirmed_entry_street"] not in ORIGIN_STREETS, e["control_id"]


def test_confirmed_entries_always_carry_method_and_evidence():
    for e in entries():
        assert e["confidence"] == "CONFIRMED"
        assert e["entry_method"] == "MANUAL_MAP_OBSERVATION"
        assert e["entry_evidence"].strip()


def test_unknown_entries_are_never_published_as_confirmed():
    published = {e["control_id"] for e in entries()}
    for r in measurements():
        if r["yandex_district_entry_confidence"] == "UNKNOWN":
            assert r["control_id"] not in published


def test_unconfirmed_rows_say_so_explicitly():
    for r in measurements():
        if r["yandex_district_entry_confidence"] == "UNKNOWN":
            assert r["yandex_district_entry"] == "UNKNOWN_REQUIRES_MAP_REVIEW"


def test_measurements_support_manual_entry_evidence_fields():
    fields = measurements()[0].keys()
    for field in REBUILD.MANUAL_ENTRY_DEFAULTS:
        assert field in fields


def test_confirmed_manual_entry_requires_manual_map_observation():
    row = {
        "control_id": "MY-TEST",
        "manual_entry_street": "улица Тестовая",
        "manual_entry_evidence": "граница визуально отмечена на карте",
        "manual_entry_method": "EMPTY",
        "manual_entry_confidence": "CONFIRMED",
    }
    with pytest.raises(ValueError, match="MANUAL_MAP_OBSERVATION"):
        REBUILD.apply_manual_entry(row)


def test_confirmed_manual_entry_requires_nonempty_evidence():
    row = {
        "control_id": "MY-TEST",
        "manual_entry_street": "улица Тестовая",
        "manual_entry_evidence": "",
        "manual_entry_method": "MANUAL_MAP_OBSERVATION",
        "manual_entry_confidence": "CONFIRMED",
    }
    with pytest.raises(ValueError, match="non-empty evidence"):
        REBUILD.apply_manual_entry(row)


def test_fourth_batch_does_not_publish_route_streets_as_entries():
    published = {row["control_id"] for row in entries()}
    assert published.isdisjoint(FOURTH_BATCH_IDS)
