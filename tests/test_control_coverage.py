"""Coverage, candidate and provisional-boundary audit tests."""

from __future__ import annotations

import csv
import importlib.util
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data/interim"
REPORTS = REPO / "reports/full-address-routing-audit"

SPEC = importlib.util.spec_from_file_location(
    "analyze_control_coverage",
    REPO / "scripts/analyze_control_coverage.py",
)
assert SPEC and SPEC.loader
ANALYZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYZER)


def rows(name: str) -> list[dict[str, str]]:
    with (DATA / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_coverage_output_has_one_allowed_level_per_address():
    coverage = rows("address-control-coverage-v1.csv")
    assert len(coverage) == 9_216
    assert len({row["address_id"] for row in coverage}) == len(coverage)
    assert {row["coverage_level"] for row in coverage} <= ANALYZER.VALID_COVERAGE


def test_uncovered_is_never_automatically_declared_safe():
    uncovered = [
        row
        for row in rows("address-control-coverage-v1.csv")
        if row["coverage_level"] == "UNCOVERED"
    ]
    assert uncovered
    assert all(row["manual_review_recommended"] == "True" for row in uncovered)


def test_district_match_alone_cannot_create_strong_coverage():
    address = {
        "destination_lon": "29.40",
        "destination_lat": "46.80",
        "router_main_streets": "Unrelated street",
        "route_last_nodes": "1;2",
        "corridor_signature": "address-corridor",
        "terminal_node_signature": "address-terminal",
        "bridge_or_rail": "NONE_OBSERVED",
        "street": "Unrelated street",
        "district": "Same district",
    }
    control = {
        "control_id": "control",
        "district": "Same district",
        "street": "Different street",
        "lat": 46.90,
        "lon": 29.50,
        "streets": ["Different street"],
        "corridor_signature": "control-corridor",
        "terminal_signature": "control-terminal",
        "last_nodes": {"3", "4"},
        "bridge": "NONE_OBSERVED",
    }
    score, evidence = ANALYZER.score_coverage(address, control)
    assert ANALYZER.coverage_level(score, evidence) == "UNCOVERED"


def test_critical_candidates_survive_cluster_deduplication():
    audit = rows("all-address-router-audit-v1.csv")
    coverage_rows = rows("address-control-coverage-v1.csv")
    coverage = {row["address_id"]: row for row in coverage_rows}
    candidates = {row["address_id"] for row in rows("additional-manual-route-candidates-v1.csv")}
    corridor_count = Counter(row["corridor_signature"] for row in audit)
    critical = {
        row["address_id"]
        for row in audit
        if ANALYZER.candidate_priority(
            row, coverage[row["address_id"]], corridor_count
        )[0]
        == "CRITICAL"
    }
    assert critical
    assert critical <= candidates


def test_neighbor_comparisons_are_partitioned_by_territory_district_and_street():
    source = (REPO / "scripts/evaluate_all_addresses_against_router.py").read_text(
        encoding="utf-8"
    )
    assert '(row["territory"], row["district"], row["street"])' in source
    source = (REPO / "scripts/analyze_control_coverage.py").read_text(encoding="utf-8")
    assert '(row["territory"], row["district"], row["street"])' in source


def test_provisional_review_has_no_zone_id_or_release_mutation_fields():
    boundary = rows("provisional-zone-boundary-review-v1.csv")
    assert boundary
    assert "zone_id" not in boundary[0]
    assert "provisional_zone" in boundary[0]
    assert all(row["manual_review_required"] == "True" for row in boundary)


def test_coverage_is_not_only_a_district_comparison():
    source = (REPO / "scripts/analyze_control_coverage.py").read_text(encoding="utf-8")
    function = source[source.index("def score_coverage"):source.index("def coverage_level")]
    assert "district" not in function
    assert "corridor_signature" in function
    assert "route_last_nodes" in function


def test_reports_are_reproducible_from_the_three_analysis_csvs():
    audit = rows("all-address-router-audit-v1.csv")
    coverage = rows("address-control-coverage-v1.csv")
    candidates = rows("additional-manual-route-candidates-v1.csv")
    boundary = rows("provisional-zone-boundary-review-v1.csv")
    minimal_ids = {
        row["address_id"]
        for row in candidates
        if row["recommended_manual_action"].startswith("MINIMAL_SET")
    }
    extended_ids = {row["address_id"] for row in candidates}
    generated = ANALYZER.report_tables(
        audit, coverage, candidates, minimal_ids, extended_ids, boundary
    )
    for name, text in generated.items():
        assert (REPORTS / name).read_text(encoding="utf-8").rstrip() == text.rstrip()


def test_every_required_report_exists():
    expected = {
        "all-address-summary-v1.md",
        "anomalies-v1.md",
        "control-coverage-v1.md",
        "manual-review-plan-v1.md",
        "provisional-zone-boundary-review-v1.md",
    }
    assert expected <= {path.name for path in REPORTS.glob("*.md")}
