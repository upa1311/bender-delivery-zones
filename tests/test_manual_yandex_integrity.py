"""Integrity of the manual-Yandex control set, ids and measurements."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
D = REPO / "docs/data"
TOL_M = 60.0


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


def test_migration_covers_every_measurement():
    assert len(migration()) == len(measurements())


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
