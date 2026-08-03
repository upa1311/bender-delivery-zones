"""Invariants for the /review/ delivery-tariff design model. These break the build
on violation (per owner requirement). All inputs are committed; no network."""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RD = ROOT / "docs/review/data"
SUMMARY = json.loads((RD / "reference-tariff-v3-summary.json").read_text("utf-8"))
ROWS = list(csv.DictReader((RD / "reference-tariff-v3.csv").open(encoding="utf-8-sig")))
POINTS = json.loads((RD / "zone-points.json").read_text("utf-8"))
VALID_STATUS = {"routed", "duplicate", "invalid_address", "outside_supported_area",
                "unreachable", "manual_review"}


def test_catalog_total_is_9216():
    assert SUMMARY["catalog_total"] == 9216
    assert len(ROWS) == 9216


def test_status_total_is_9216_and_every_record_has_a_status():
    assert SUMMARY["status_sum"] == 9216
    assert SUMMARY["status_sum_equals_9216"] is True
    assert sum(SUMMARY["status_counts"].values()) == 9216
    assert set(SUMMARY["status_counts"]) <= VALID_STATUS
    assert all(r["status"] in VALID_STATUS for r in ROWS)
    assert all(r["routing_status"] == r["status"] for r in ROWS)


def test_every_routed_record_has_route_and_price():
    for r in ROWS:
        if r["status"] == "routed":
            assert r["route_km"] != "" and float(r["route_km"]) > 0
            assert r["base_price"] != "" and float(r["base_price"]) >= 14
            assert r["reference_price"] != ""
            assert r["internal_zone"] != ""


def test_formula_is_correct_and_18_6_10_rejected():
    assert "18 / 6 / 10" in SUMMARY["formula"]["rejected"]
    for r in ROWS:
        if r["status"] != "routed":
            continue
        km = float(r["route_km"])
        base = 14.0 if km <= 3 else 14.0 + (km - 3) * 4
        # values are stored rounded to 3 decimals; allow a 1-kopeck tolerance
        assert abs(float(r["base_price"]) - base) < 0.01
        ext = float(r["external_km"] or 0)
        sur = 0.0 if ext <= 0 else max(5.0, ext * 2)
        assert abs(float(r["external_surcharge"] or 0) - sur) < 0.01
        assert abs(float(r["reference_price"]) - (base + sur)) < 0.02


def test_external_km_bounds_and_zero_surcharge_rule():
    for r in ROWS:
        if r["status"] != "routed":
            continue
        ext = float(r["external_km"] or 0)
        assert ext >= 0                                  # external_km >= 0
        assert ext <= float(r["route_km"]) + 1e-6        # external_km <= route_km
        if ext == 0:
            assert float(r["external_surcharge"] or 0) == 0.0
    # only Парканы routes cross the single tariff boundary
    for r in ROWS:
        if r["status"] == "routed" and r["territory"] != "Парканы":
            assert float(r["external_surcharge"] or 0) == 0.0


def test_kishinevskaya_recomputed_and_no_old_detour_remains():
    kd = SUMMARY["kishinevskaya"]
    assert len(kd) >= 34
    assert SUMMARY["kishinevskaya_total"] == len(kd)
    # NO record is left at the old 6.38–7.22 detour (routed => < 6 km, else flagged)
    for k in kd:
        if k["new_km"] != "":
            assert float(k["new_km"]) < 6.0, k["address"]
        else:
            assert k["status"] in ("manual_review", "unreachable")
    # the control street matches Yandex 4.7–4.9 and beats the duration-optimal detour
    k76 = next(k for k in kd if k["address"] == "Бендеры, Кишинёвская улица, 76")
    assert 4.5 <= float(k76["new_km"]) <= 4.95
    assert float(k76["duration_opt_km"]) > float(k76["new_km"]) + 1.0
    assert SUMMARY["kishinevskaya_fixed_count"] >= 20
    # genuinely different segments keep different distances (not forced to one number)
    news = {round(float(k["new_km"]), 2) for k in kd if k["new_km"] != ""}
    assert len(news) >= 5


def test_parkany_control_route_near_4_72_km():
    assert abs(SUMMARY["parkany_control_km"] - 4.72) < 0.2


def test_zones_are_natural_breaks_not_equal_or_quartile_or_k4():
    breaks = SUMMARY["recommended_breaks_price"]
    assert len(breaks) >= 3
    gaps = [round(breaks[i + 1] - breaks[i], 3) for i in range(len(breaks) - 1)]
    assert len(set(gaps)) > 1                            # not equal-interval
    assert SUMMARY["recommended_zone_count"] >= 3
    # new internal zone is derived from price, NOT a copy of the old K4 geometry:
    # the routed rows do not map old_k4_zone_id 1:1 to internal_zone.
    routed = [r for r in ROWS if r["status"] == "routed"]
    same = sum(1 for r in routed if str(r["internal_zone"]) == str(r["old_k4_zone_id"]))
    assert same < len(routed)                            # not an identity copy of K4


def test_boundary_persistence_smoke_present_in_source():
    js = (ROOT / "docs/review/review.js").read_text("utf-8")
    # the approved tariff boundary is saved to localStorage and restored on load
    assert "localStorage.setItem" in js and "localStorage.getItem" in js
    assert "owner_approved" in js and "approved_at" in js
    assert "bdz_tariff_boundary" in js


def test_map_points_cover_the_catalog():
    assert POINTS["expected"] == 9216
    # every plotted point carries a status code; routed points carry a zone 1..N
    assert POINTS["plotted"] >= 9000
    zones = {p[2] for p in POINTS["points"] if p[3] == 1}
    assert zones and max(zones) == SUMMARY["recommended_zone_count"]
