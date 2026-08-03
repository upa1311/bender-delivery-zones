"""Fail-closed invariants for the route-geometry /review/ design model."""

from __future__ import annotations

import csv
import importlib.util
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RD = ROOT / "docs/review/data"
SUMMARY = json.loads((RD / "reference-tariff-v3-summary.json").read_text("utf-8"))
ROWS = list(csv.DictReader((RD / "reference-tariff-v3.csv").open(encoding="utf-8-sig")))
POINTS = json.loads((RD / "zone-points.json").read_text("utf-8"))
ROUTE_GEOMETRIES = json.loads((RD / "review-route-geometries.json").read_text("utf-8"))
PARKANY = json.loads((RD / "parkany-route-boundary.json").read_text("utf-8"))
KISH_MANIFEST = json.loads(
    (RD / "kishinevskaya-authoritative-manifest.json").read_text("utf-8")
)
VALID_STATUS = {
    "routed", "duplicate", "invalid_address", "outside_supported_area",
    "unreachable", "manual_review",
}

spec = importlib.util.spec_from_file_location(
    "review_model_core", ROOT / "scripts/review_model_core.py"
)
assert spec and spec.loader
CORE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CORE)


def independent_weighted_jenks(values: list[float], class_count: int) -> list[float]:
    """Independent reference DP used to audit the production implementation."""
    levels = sorted(Counter(values).items())
    count = [0]
    total = [0.0]
    squares = [0.0]
    for value, frequency in levels:
        count.append(count[-1] + frequency)
        total.append(total[-1] + value * frequency)
        squares.append(squares[-1] + value * value * frequency)

    def variance(first: int, last: int) -> float:
        weight = count[last] - count[first - 1]
        value_sum = total[last] - total[first - 1]
        return squares[last] - squares[first - 1] - value_sum * value_sum / weight

    n = len(levels)
    scores = [[float("inf")] * (n + 1) for _ in range(class_count + 1)]
    starts = [[0] * (n + 1) for _ in range(class_count + 1)]
    scores[0][0] = 0.0
    for group in range(1, class_count + 1):
        for last in range(group, n + 1):
            for first in range(group, last + 1):
                score = scores[group - 1][first - 1] + variance(first, last)
                if score < scores[group][last] - 1e-12:
                    scores[group][last] = score
                    starts[group][last] = first
    breaks = []
    last = n
    for group in range(class_count, 0, -1):
        first = starts[group][last]
        breaks.append(levels[last - 1][0])
        last = first - 1
    return list(reversed(breaks))


def test_catalog_and_status_totals_are_exact():
    assert SUMMARY["catalog_total"] == 9216 == len(ROWS)
    assert SUMMARY["status_sum"] == 9216
    assert SUMMARY["status_sum_equals_9216"] is True
    assert sum(SUMMARY["status_counts"].values()) == 9216
    assert set(SUMMARY["status_counts"]) <= VALID_STATUS
    assert all(row["routing_status"] == row["status"] for row in ROWS)


def test_every_routed_record_has_real_geometry_and_complete_calculation():
    routed = [row for row in ROWS if row["status"] == "routed"]
    assert len(routed) == 9215
    assert ROUTE_GEOMETRIES["route_count"] == len(ROUTE_GEOMETRIES["routes"]) == 9215
    assert {row["uid"] for row in routed} == set(ROUTE_GEOMETRIES["routes"])
    for row in routed:
        assert float(row["route_km"]) > 0
        assert row["crosses_checkpoint"] in {"True", "False"}
        assert row["external_km"] != ""
        assert row["base_price"] != ""
        assert row["reference_price"] != ""
        assert row["internal_zone"] != ""
        geometry_km = float(ROUTE_GEOMETRIES["routes"][row["uid"]][0])
        assert abs(geometry_km - float(row["route_km"])) <= 0.002


def test_frequency_weighted_jenks_uses_all_9215_observations():
    observations = [
        round(float(row["reference_price"]), 1) for row in ROWS if row["status"] == "routed"
    ]
    assert len(observations) == SUMMARY["jenks_input_observation_count"] == 9215
    expected = independent_weighted_jenks(observations, SUMMARY["recommended_zone_count"])
    assert expected == SUMMARY["recommended_breaks_price"]
    assert expected == [18.1, 24.9, 31.9, 43.8]
    assert expected != [21.4, 28.9, 36.4, 43.8]
    assert SUMMARY["jenks_distinct_level_count"] == len(set(observations))


def test_tariff_formula_and_external_invariants():
    for row in ROWS:
        if row["status"] != "routed":
            continue
        route_km = float(row["route_km"])
        external_km = float(row["external_km"])
        base = 14.0 if route_km <= 3 else 14.0 + (route_km - 3) * 4
        surcharge = 0.0 if external_km <= 0 else max(5.0, external_km * 2)
        assert 0 <= external_km <= route_km + 1e-6
        assert abs(float(row["base_price"]) - base) < 0.01
        assert abs(float(row["external_surcharge"]) - surcharge) < 0.01
        assert abs(float(row["reference_price"]) - base - surcharge) < 0.02
        if row["crosses_checkpoint"] == "False":
            assert row["intersection_chainage_km"] == ""
            assert external_km == 0
            assert float(row["external_surcharge"]) == 0
        else:
            chainage = float(row["intersection_chainage_km"])
            assert 0 <= chainage <= route_km
            assert abs(external_km - (route_km - chainage)) < 0.001


def test_crossing_is_not_inferred_from_territory_or_fixed_boundary():
    source = (ROOT / "scripts/build_review_model.py").read_text("utf-8")
    assert "is_park" not in source
    assert "route_km - boundary" not in source
    assert 'row["settlement"] == "Парканы"' not in source
    assert "route_gate_metrics" in source
    assert SUMMARY["routes_crossing_gate"] + SUMMARY["routes_not_crossing_gate"] == 9215


def test_route_crosses_gate_and_uses_first_intersection():
    gate = [(0.0, -1.0), (0.0, 1.0)]
    metrics = CORE.route_gate_metrics([(-2.0, 0.0), (2.0, 0.0)], 4.0, gate)
    assert metrics["crosses_checkpoint"] is True
    assert abs(metrics["intersection_chainage_km"] - 2.0) < 1e-6
    assert abs(metrics["external_km"] - 2.0) < 1e-6
    multiple = CORE.route_gate_metrics(
        [(-2.0, 0.0), (2.0, 0.0), (-2.0, 0.5), (2.0, 0.5)], 12.0, gate
    )
    assert abs(multiple["intersection_chainage_km"] - 2.0) < 0.02


def test_route_near_gate_does_not_cross():
    metrics = CORE.route_gate_metrics([(-2.0, 1.1), (2.0, 1.1)], 4.0,
                                      [(0.0, -1.0), (0.0, 1.0)])
    assert metrics == {
        "crosses_checkpoint": False,
        "intersection_chainage_km": None,
        "external_km": 0.0,
    }


def test_route_endpoint_on_gate_is_a_valid_intersection():
    gate = [(0.0, -1.0), (0.0, 1.0)]
    start = CORE.route_gate_metrics([(0.0, 0.0), (2.0, 0.0)], 2.0, gate)
    end = CORE.route_gate_metrics([(-2.0, 0.0), (0.0, 0.0)], 2.0, gate)
    assert start["intersection_chainage_km"] == 0
    assert abs(end["intersection_chainage_km"] - 2.0) < 1e-6


def test_crossing_behavior_is_independent_of_settlement_label():
    gate = [(0.0, -1.0), (0.0, 1.0)]
    not_parkany_but_crosses = CORE.route_gate_metrics([(-1.0, 0.0), (1.0, 0.0)], 2.0, gate)
    parkany_but_misses = CORE.route_gate_metrics([(-1.0, 2.0), (1.0, 2.0)], 2.0, gate)
    assert not_parkany_but_crosses["crosses_checkpoint"] is True
    assert parkany_but_misses["crosses_checkpoint"] is False


def test_single_provisional_gate_with_multiple_provenance_sources():
    assert "boundary_candidates" not in PARKANY
    gate = PARKANY["provisional_gate"]
    assert gate["status"] == "PROVISIONAL"
    assert gate["geometry"]["type"] == "LineString"
    assert len(gate["geometry"]["coordinates"]) == 2
    assert len(gate["provenance"]["sources"]) == 3


def test_kishinevskaya_manifest_is_exact_and_explains_35th_candidate():
    authoritative = {entry["uid"] for entry in KISH_MANIFEST["entries"] if entry["included"]}
    actual = {item["id"] for item in SUMMARY["kishinevskaya"]}
    assert SUMMARY["kishinevskaya_total"] == 34
    assert actual == authoritative
    assert len(KISH_MANIFEST["entries"]) == 35
    excluded = [entry for entry in KISH_MANIFEST["entries"] if not entry["included"]]
    assert len(excluded) == 1
    assert excluded[0]["uid"] == "w319620046"
    assert excluded[0]["source_tags"]["addr:street"] == "улица Титова"
    assert all(entry["reason"] for entry in KISH_MANIFEST["entries"])


def test_kishinevskaya_routes_remain_corrected_and_control_is_close():
    for item in SUMMARY["kishinevskaya"]:
        assert float(item["new_km"]) < 6.0
    control = next(
        item for item in SUMMARY["kishinevskaya"]
        if item["address"] == "Бендеры, Кишинёвская улица, 76"
    )
    assert 4.5 <= float(control["new_km"]) <= 4.95
    assert float(control["duration_opt_km"]) > float(control["new_km"]) + 1.0
    assert abs(SUMMARY["parkany_control_km"] - 4.72) < 0.2


def test_review_client_recalculates_full_catalog_and_persists_gate():
    javascript = (ROOT / "docs/review/review.js").read_text("utf-8")
    for required in (
        "recalculateCatalog", "routeGateMetrics", "weightedJenks", "9 215",
        "localStorage.setItem", "localStorage.getItem", "moveGateToIndex",
        "zoneCounts", "selected", "resetGate",
    ):
        assert required in javascript
    assert "territory" not in javascript
    assert "boundaryKm" not in javascript


def test_browser_e2e_is_installed_and_executed_by_ci():
    package = json.loads((ROOT / "package.json").read_text("utf-8"))
    assert package["devDependencies"]["@playwright/test"] == "1.62.1"
    assert package["scripts"]["test:e2e"] == "playwright test"
    assert (ROOT / "package-lock.json").is_file()

    config = (ROOT / "playwright.config.mjs").read_text("utf-8")
    for required in (
        'name: "desktop-chromium"', 'width: 1440', 'height: 900',
        'name: "mobile-chromium"', 'width: 412', 'height: 915',
    ):
        assert required in config

    workflow = (ROOT / ".github/workflows/ci.yml").read_text("utf-8")
    for required in (
        "browser-e2e:", "npm ci", "npx playwright install --with-deps chromium",
        "python -m http.server 8765", "npx playwright test",
    ):
        assert required in workflow

    e2e = (ROOT / "tests/browser/review-gate-recalculation.e2e.mjs").read_text("utf-8")
    for required in (
        "expect.poll", "data-review-ready", "page.reload()", "toEqual(initial)",
        'page.waitForEvent("download")', "readFile(downloadPath", "layout.panel",
    ):
        assert required in e2e


def test_checkpoint_export_has_public_schema_and_keeps_internal_state_private():
    javascript = (ROOT / "docs/review/review.js").read_text("utf-8")
    assert "function exportCheckpoint()" in javascript
    assert "return { checkpoint: { lat:" in javascript
    assert "lon: +center[0].toFixed(6)" in javascript
    assert 'anchor.download = "tariff-checkpoint.json"' in javascript
    assert "JSON.stringify(exportCheckpoint()" in javascript
    assert "localStorage.setItem(LSKEY, JSON.stringify(approved))" in javascript


def test_map_points_cover_catalog_with_uid_linkage():
    assert POINTS["expected"] == 9216
    assert POINTS["plotted"] >= 9000
    assert all(len(point) == 7 and isinstance(point[0], str) for point in POINTS["points"])
    zones = {point[3] for point in POINTS["points"] if point[4] == 1}
    assert max(zones) == SUMMARY["recommended_zone_count"]
