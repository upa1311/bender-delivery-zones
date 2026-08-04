"""Static and data-contract checks for the GitHub Pages admin console."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN = ROOT / "docs/admin"
REVIEW = ROOT / "docs/review"


def test_admin_uses_the_complete_canonical_registry_and_gate():
    index = json.loads((REVIEW / "data/address-index.json").read_text("utf-8"))
    parkany = json.loads((REVIEW / "data/parkany-route-boundary.json").read_text("utf-8"))
    summary = json.loads(
        (REVIEW / "data/reference-tariff-v3-summary.json").read_text("utf-8")
    )
    assert len(index["addresses"]) == summary["catalog_total"] == 9216
    assert summary["status_counts"] == {"routed": 9215, "duplicate": 1}
    assert summary["routes_crossing_gate"] == 4315
    assert summary["routes_not_crossing_gate"] == 4900
    assert summary["recommended_breaks_price"] == [18.3, 25.7, 33.0, 52.9]
    assert [summary["zone_stats"][str(zone)]["n"] for zone in range(1, 5)] == [
        2729, 2557, 2588, 1341
    ]
    gate = parkany["approved_gate"]
    assert gate["status"] == "owner_approved"
    assert gate["center_lonlat"] == [29.48774, 46.82997]
    assert gate["corridor_route_index"] == 33
    assert gate["approved_at"] == "2026-08-03T22:31:23.434Z"


def test_admin_and_review_share_one_tariff_module_without_a_second_formula():
    html = (ADMIN / "index.html").read_text("utf-8")
    admin = (ADMIN / "admin.js").read_text("utf-8")
    review_html = (REVIEW / "index.html").read_text("utf-8")
    review = (REVIEW / "review.js").read_text("utf-8")
    shared = (REVIEW / "tariff-model.js").read_text("utf-8")
    assert "../review/tariff-model.js" in html
    assert 'src="tariff-model.js"' in review_html
    assert "BenderTariffModel" in admin and "BenderTariffModel" in review
    assert "const basePrice" not in admin
    assert "const basePrice" not in review
    assert "14 + (km - 3) * 4" in shared
    assert "Math.max(5, km * 2)" in shared
    assert "symmetricRouteGateMetrics" in shared


def test_admin_is_static_v1_with_mockable_osrm_and_honest_failure_contract():
    html = (ADMIN / "index.html").read_text("utf-8")
    source = (ADMIN / "admin.js").read_text("utf-8")
    e2e = (ROOT / "tests/browser/admin-console.e2e.mjs").read_text("utf-8")
    for required in (
        "street-filter", "house-filter", "district-filter", "zone-filter",
        "selected-a", "selected-b", "calculate-route", "swap-addresses",
        "download-csv", "admin-map",
    ):
        assert required in html
    assert "router.project-osrm.org" in source
    assert "OSRM недоступен" in source
    assert "Расчёт не выполнен" in source
    assert "DirectDelivery" not in source
    assert "authorization" not in source.casefold()
    assert 'page.route("https://router.project-osrm.org' in e2e
    assert "data-total" in e2e
    assert "mobile" not in e2e  # viewports are supplied by Playwright projects
