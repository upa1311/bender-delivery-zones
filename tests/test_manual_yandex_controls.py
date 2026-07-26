"""Manual Yandex controls — template integrity, no fabrication, calibration rules."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from manual_yandex_controls import (  # noqa: E402
    COLUMNS,
    DISAGREE_PCT,
    ORIGIN_LAT,
    ORIGIN_LON,
    YANDEX_INPUT_COLUMNS,
)

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "docs/data/manual-yandex-route-controls.csv"
RPT = REPO / "reports/manual-yandex-routing"


def rows():
    return list(csv.DictReader(TEMPLATE.open(encoding="utf-8")))


def test_template_exists_with_the_required_columns():
    assert TEMPLATE.exists()
    header = rows()[0].keys()
    for c in COLUMNS:
        assert c in header, c


def test_no_yandex_value_is_fabricated():
    for r in rows():
        for c in YANDEX_INPUT_COLUMNS:
            assert (r[c] or "").strip() == "", f"{c} must be filled by a human, not by us"


def test_every_control_has_exact_coordinates_and_our_baseline():
    for r in rows():
        assert float(r["destination_lat"]) and float(r["destination_lon"])
        assert r["current_osrm_km"], "our own OSRM baseline must be pre-computed"
        assert r["control_reason"], "why the control was chosen must be recorded"


def test_origin_is_the_fixed_central_point():
    assert (ORIGIN_LAT, ORIGIN_LON) == (46.82388, 29.48313)


def test_all_required_districts_are_covered():
    got = {r["target_district"] for r in rows()}
    for d in ("Хомутяновка", "Протягайловка", "Гиска", "Парканы", "Северный", "Борисовка"):
        assert d in got, d


def test_severny_has_all_seven_exact_addresses():
    assert sum(1 for r in rows() if r["target_district"] == "Северный") == 7


def test_owner_named_streets_are_present_as_controls():
    reasons = " ".join(r["control_reason"] for r in rows())
    for st in ("Ечина", "Главана", "Старого", "Московская", "Первомайская", "Некрасова"):
        assert st in reasons, st


def test_owner_landmarks_are_present_as_controls():
    reasons = " ".join(r["control_reason"] for r in rows())
    for lm in ("Пивзавод", "Роддом", "Городская больница"):
        assert lm in reasons, lm


def test_zone_boundary_controls_exist():
    reasons = " ".join(r["control_reason"] for r in rows())
    assert "Zone2/3" in reasons and "Zone3/4" in reasons


def test_every_control_starts_awaiting_a_manual_measurement():
    assert all(r["calibration_status"] == "AWAITING_MANUAL_YANDEX_MEASUREMENT"
               for r in rows())


def test_reports_exist_for_every_district():
    for f in ("khomutyanovka", "protyagailovka", "giska", "parkany", "severny",
              "borisovka", "summary"):
        assert (RPT / f"{f}.md").exists(), f


def test_no_yandex_polyline_tile_or_html_is_stored():
    for p in (REPO / "docs").rglob("*yandex*"):
        assert p.suffix.lower() in (".csv", ".json", ".md"), p
        txt = p.read_text("utf-8", errors="ignore")
        assert "encodedPolyline" not in txt
        assert "<!DOCTYPE" not in txt.upper()


def test_disagreement_threshold_is_ten_percent():
    assert DISAGREE_PCT == 10.0
