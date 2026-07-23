"""Stage-02 service-area QA: allowlist, Varnița exclusion, RU names, determinism.

All offline: validates pure logic plus the committed map artifacts. No PBF, no
network, no osmium-tool.
"""

from __future__ import annotations

import csv
import json

from bender_zones import jsonutil
from bender_zones.service_area import (
    BOUNDARY_MISSING,
    STATUS_NEEDS_REVIEW,
    STATUS_OK,
    SettlementEntry,
    build_settlement_feature,
    load_service_area,
    resolve_ru_name,
    round_coords,
    street_record,
)

ALLOWED = {"bender", "protyagailovka", "giska", "parkany"}
VARNITA_TOKENS = ("varnita", "varniț", "варниц")


def _cfg(repo_root):
    return load_service_area(repo_root / "config" / "service-area.yml")


# --- allowlist / Varnița control -------------------------------------------

def test_allowlist_is_exactly_the_four(repo_root):
    cfg = _cfg(repo_root)
    assert set(cfg.allowed_keys()) == ALLOWED


def test_varnita_absent_from_allowed_present_in_excluded(repo_root):
    cfg = _cfg(repo_root)
    assert "varnita" not in cfg.allowed_keys()
    assert "varnita" in cfg.excluded_keys()


def test_no_extra_settlements_added(repo_root):
    cfg = _cfg(repo_root)
    # Exactly four allowed territories, no silent additions.
    assert len(cfg.allowed) == 4


def test_varnita_not_in_settlements_geojson(repo_root):
    fc = json.loads((repo_root / "docs/data/settlements.geojson").read_text(encoding="utf-8"))
    keys = {f["properties"]["key"] for f in fc["features"]}
    assert keys == ALLOWED
    for f in fc["features"]:
        blob = json.dumps(f["properties"], ensure_ascii=False).lower()
        assert not any(tok in blob for tok in VARNITA_TOKENS), "Varnița leaked into settlements"


# --- boundary_missing must never become a buffer ----------------------------

def test_missing_boundary_is_point_marker_not_buffer():
    entry = SettlementEntry(key="ghost", display_ru="Тест", osm_type="relation", osm_id=1)
    feat = build_settlement_feature(entry, {"name": "X"}, geometry=None,
                                    marker_lonlat=(29.5, 46.8))
    assert feat["properties"]["status"] == BOUNDARY_MISSING
    assert feat["geometry"]["type"] == "Point"  # a marker, not a polygon
    assert feat["geometry"]["type"] not in ("Polygon", "MultiPolygon")


def test_found_boundary_uses_real_polygon():
    entry = SettlementEntry(key="x", display_ru="Т", osm_type="relation", osm_id=2)
    geom = {"type": "MultiPolygon", "coordinates": [[[[0, 0], [0, 1], [1, 1], [0, 0]]]]}
    feat = build_settlement_feature(entry, {}, geometry=geom)
    assert feat["properties"]["status"] == "boundary_found"
    assert feat["geometry"] is geom


# --- RU name resolution -----------------------------------------------------

def test_name_ru_has_priority_over_all_others():
    tags = {
        "name": "Strada Lenin",
        "name:ru": "улица Ленина",
        "official_name:ru": "проспект Официальный",
        "alt_name:ru": "альтернативное",
    }
    display, source, status = resolve_ru_name(tags)
    assert display == "улица Ленина"
    assert source == "name:ru"
    assert status == STATUS_OK


def test_priority_falls_through_to_official_then_alt():
    off = resolve_ru_name({"name": "X", "official_name:ru": "Оф"})
    assert off == ("Оф", "official_name:ru", STATUS_OK)
    alt = resolve_ru_name({"name": "X", "alt_name:ru": "Аль"})
    assert alt == ("Аль", "alt_name:ru", STATUS_OK)


def test_local_table_used_before_giving_up():
    display, source, status = resolve_ru_name({"name": "Strada Mare"},
                                              {"Strada Mare": "улица Маре"})
    assert (display, source, status) == ("улица Маре", "local_table", STATUS_OK)


def test_street_without_ru_gets_needs_review_and_no_transliteration():
    tags = {"name": "Strada Ștefan cel Mare", "name:ro": "Strada Ștefan cel Mare"}
    display, source, status = resolve_ru_name(tags)
    assert status == STATUS_NEEDS_REVIEW
    assert source == "none"
    # display falls back to the ORIGINAL name, never a transliteration
    assert display == "Strada Ștefan cel Mare"


def test_street_record_preserves_all_fields():
    tags = {"name": "N", "name:ru": "Н", "name:ro": "R", "official_name": "O",
            "alt_name": "A", "old_name": "OLD"}
    rec = street_record("way", 42, tags, "bender")
    for key in ("name", "name:ru", "name:ro", "official_name", "alt_name", "old_name"):
        assert rec[key] == tags[key]
    assert rec["osm_id"] == 42 and rec["osm_type"] == "way"


# --- determinism ------------------------------------------------------------

def test_round_coords_is_deterministic_and_stable():
    geom = {"type": "LineString", "coordinates": [[29.481912345, 46.821854321]]}
    once = round_coords(geom, 5)
    twice = round_coords(once, 5)
    assert once == twice
    assert once["coordinates"][0] == [29.48191, 46.82185]


def test_committed_geojson_is_canonical(repo_root):
    # Re-serializing the committed file through the deterministic writer must be
    # a no-op (sorted keys, stable float repr).
    for name in ("settlements.geojson", "roads.geojson"):
        path = repo_root / "docs/data" / name
        text = path.read_text(encoding="utf-8")
        assert jsonutil.dumps(json.loads(text)) == text


# --- committed CSV / summary integrity --------------------------------------

def test_review_csv_flags_missing_ru(repo_root):
    rows = list(csv.DictReader((repo_root / "docs/data/street-names-review.csv")
                               .read_text(encoding="utf-8").splitlines()))
    assert rows, "street CSV should not be empty"
    for row in rows:
        if row["ru_status"] == STATUS_NEEDS_REVIEW:
            assert not (row["name_ru"] or "").strip(), "needs_ru_review row must lack name:ru"


def test_summary_totals_consistent(repo_root):
    s = json.loads((repo_root / "docs/data/summary.json").read_text(encoding="utf-8"))
    per = s["per_settlement"]
    assert s["zones_created"] is False
    assert s["boundary_selected"] is False
    assert s["totals"]["settlements"] == 4
    assert s["totals"]["unique_streets"] == sum(p["unique_streets"] for p in per.values())
    assert s["totals"]["streets_needs_ru_review"] == sum(
        p["streets_needs_ru_review"] for p in per.values())


# --- the public HTML must carry attribution + the "no zones yet" warning ----

def test_html_has_attribution_and_zone_warning(repo_root):
    html = (repo_root / "docs/index.html").read_text(encoding="utf-8")
    assert "© OpenStreetMap contributors" in html
    assert "Финальные зоны доставки ещё не созданы" in html


def test_app_js_uses_local_osm_tiles_with_attribution(repo_root):
    app = (repo_root / "docs/app.js").read_text(encoding="utf-8")
    assert "© OpenStreetMap contributors" in app
    # data comes from local ./data, not Overpass/Nominatim
    assert "overpass" not in app.lower()
    assert "nominatim" not in app.lower()
