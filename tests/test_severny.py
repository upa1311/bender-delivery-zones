"""Stage 08 (final) — real Северный footprint, Varnița split, per-address zones."""

from __future__ import annotations

import csv
import json

from shapely.geometry import shape

from bender_zones.address import full_address_ru

TRUNCATED_LAT = 46.854251
LIPCANI_STREETS = {"улица Энгельса", "переулок Энгельса", "улица Кутузова",
                   "Подольская улица", "Парканская улица", "Колхозная улица",
                   "улица Гайдара"}


def _json(repo_root, rel):
    return json.loads((repo_root / rel).read_text(encoding="utf-8"))


def _audit(repo_root):
    return _json(repo_root, "reports/stage-08/severny-audit.json")


def _units(repo_root):
    text = (repo_root / "docs/data/severny-delivery-units.csv").read_text("utf-8")
    return list(csv.DictReader(text.splitlines()))


# --- the original regression stays fixed ------------------------------------

def test_real_route_terminal_is_not_the_truncated_point(repo_root):
    rf = _audit(repo_root)["regression_fix"]
    assert rf["previous_truncated_terminus"]["lat"] == TRUNCATED_LAT
    assert rf["real_route_terminus"]["lat"] > TRUNCATED_LAT + 0.02
    assert _audit(repo_root)["verification"]["terminus_is_not_truncated_point"] is True


def test_full_routes_resolved_from_full_pbf(repo_root):
    counts = _audit(repo_root)["route_member_counts"]
    assert set(counts) == {"6572078", "6572079", "6572080", "6572081"}
    for c in counts.values():
        assert c["with_geometry"] == c["way_members"] > 0


def test_previous_clusters_recorded_as_rejected_lipcani(repo_root):
    rejected = _audit(repo_root)["rejected_false_candidates_lipcani"]
    assert rejected
    joined = " ".join(s for c in rejected for s in c.get("streets", []))
    assert "Кутузова" in joined or "Подольская" in joined or "Парканская" in joined


def test_known_lipcani_streets_are_not_in_severny(repo_root):
    streets = set(_json(repo_root, "docs/data/severny-service-area.geojson")[
        "features"][0]["properties"]["streets"])
    assert not (streets & LIPCANI_STREETS)


# --- (1) Varnița: admin reference vs excluded village -----------------------

def test_varnita_admin_reference_carries_no_service_meaning(repo_root):
    fc = _json(repo_root, "docs/data/varnita-admin-reference.geojson")
    p = fc["features"][0]["properties"]
    assert p["kind"] == "admin_reference"
    assert "service_status" not in p, "the admin claim must carry no service meaning"


def test_varnita_village_is_the_grey_no_delivery_layer(repo_root):
    p = _json(repo_root, "docs/data/varnita-village-no-delivery.geojson")[
        "features"][0]["properties"]
    assert p["service_status"] == "no_delivery"
    assert p["filled"] is True


def test_severny_footprint_is_not_covered_by_the_varnita_village_fill(repo_root):
    """Map QA: the coloured Северный footprint must not sit under the grey fill."""
    sev = shape(_json(repo_root, "docs/data/severny-service-area.geojson")[
        "features"][0]["geometry"])
    village = shape(_json(repo_root, "docs/data/varnita-village-no-delivery.geojson")[
        "features"][0]["geometry"])
    assert not sev.intersects(village)
    assert _audit(repo_root)["verification"][
        "footprint_intersects_varnita_village_fill"] is False


def test_varnita_village_exclusion_still_proven(repo_root):
    vp = _audit(repo_root)["varnita_proof"]
    assert vp["serviceable_addresses_inside_varnita_village"] == 0
    assert vp["severny_candidate_buildings_inside_varnita_village"] == 0


# --- (2) morphological footprint, no convex hull ----------------------------

def test_footprint_is_morphological_not_convex_hull(repo_root):
    f = _json(repo_root, "docs/data/severny-service-area.geojson")[
        "features"][0]["properties"]
    assert "convex hull" in f["footprint_method"].lower()  # explicitly disclaims it
    assert "morphological" in f["footprint_method"].lower()
    for key in ("raw_candidate_buildings", "final_included_buildings",
                "excluded_isolated_buildings", "component_count", "empty_area_pct"):
        assert key in f, key


def test_isolated_buildings_are_excluded_and_published(repo_root):
    a = _audit(repo_root)
    f = a["footprint"]
    assert f["excluded_isolated_buildings"] > 0
    assert (f["final_included_buildings"] + f["excluded_isolated_buildings"]
            == f["raw_candidate_buildings"])
    dropped = [c for c in a["components"] if not c["kept"]]
    assert dropped, "the dropped components must be published"
    for c in dropped:
        assert c["buildings"] < f["final_included_buildings"]


def test_footprint_is_not_mostly_empty(repo_root):
    """Fields and long corridors would show up as a very high empty fraction."""
    f = _json(repo_root, "docs/data/severny-service-area.geojson")[
        "features"][0]["properties"]
    assert f["empty_area_pct"] < 80.0


def test_raw_candidates_layer_flags_included(repo_root):
    fc = _json(repo_root, "docs/data/severny-candidate-buildings.geojson")
    assert fc["features"]
    assert any(f["properties"]["included"] for f in fc["features"])
    assert any(not f["properties"]["included"] for f in fc["features"])


# --- (3) address provenance -------------------------------------------------

def test_house_numbering_is_an_external_reference_without_provenance(repo_root):
    a = _audit(repo_root)
    assert "official_address_support" not in a, \
        "unverified numbering must not be labelled official"
    ref = a["external_address_reference"]
    assert ref["verified_for_automatic_import"] is False
    src = ref["source"]
    for field in ("title", "retrieval_date", "claim", "confidence",
                  "may_be_imported_as_address"):
        assert field in src, field
    assert src["may_be_imported_as_address"] is False


def test_missing_houses_are_not_synthesized(repo_root):
    ref = _audit(repo_root)["external_address_reference"]
    # only the few referenced examples exist, never a generated 1..105 list
    assert len(ref["external_example_house_numbers"]) <= 10
    units = _units(repo_root)
    real = {u["housenumber"] for u in units if u["housenumber"]}
    assert len(real) < 105, "house numbers must come from OSM, not be generated"


def test_official_address_format_still_renders(repo_root):
    assert full_address_ru("Бендеры", "микрорайон Северный", "", "13") == \
        "Бендеры, микрорайон Северный, дом 13"


# --- (4) per-unit distances and zones ---------------------------------------

def test_every_unit_has_individual_osrm_distances(repo_root):
    units = _units(repo_root)
    assert units, "per-unit CSV must not be empty"
    for u in units:
        assert u["central_km"] and u["bam_km"] and u["expected_km"]
        assert u["assigned_zone"] in {"1", "2", "3", "4"}
        assert u["reachable"] in {"True", "False"}
        assert u["route_through_varnita_village"] in {"True", "False"}
        assert u["lon"] and u["lat"]
        assert u["unit_type"] in ("addressed_residential_building",
                                  "unaddressed_residential_building")


def test_expected_km_uses_85_15_weighting(repo_root):
    for u in _units(repo_root)[:20]:
        c, b, e = float(u["central_km"]), float(u["bam_km"]), float(u["expected_km"])
        assert abs(e - (0.85 * c + 0.15 * b)) < 0.02


def test_per_unit_report_is_published(repo_root):
    r = _audit(repo_root)["per_unit_report"]
    for key in ("units_total", "units_reachable", "unreachable",
                "units_requiring_varnita_transit", "units_per_zone",
                "confirmed_addresses_per_zone", "expected_km"):
        assert key in r, key
    for stat in ("min", "p50", "p90", "max"):
        assert r["expected_km"][stat] is not None
    assert sum(r["units_per_zone"].values()) == r["units_reachable"]


def test_units_geojson_matches_the_csv(repo_root):
    fc = _json(repo_root, "docs/data/severny-delivery-units.geojson")
    assert len(fc["features"]) == len(_units(repo_root))


def test_scenario_A_uses_individual_distances_not_a_centroid(repo_root):
    sa = _audit(repo_root)["scenarios"]["scenario_A"]
    assert sa["uses_individual_distances"] is True
    assert "expected_km_centre" not in sa, "the centroid shortcut must be gone"
    assert sum(sa["units_per_zone"].values()) > 0
    if sa["units_beyond_current_max"] == 0:
        assert sa["zone4_extended_to_km"] is None


def test_scenario_B_uses_stage06_optimiser_and_weights(repo_root):
    b = _audit(repo_root)["scenarios"]["scenario_B"]
    assert "PREVIEW ONLY" in b["note"]
    assert "Stage 06" in b["optimiser"] and "split penalty" in b["optimiser"]
    ctrl = b["control_recompute_without_severny"]
    assert ctrl["edges_km"] == b["current_edges_km"], \
        "the control must reproduce the published edges, else the weighting is wrong"
    assert b["severny_delivery_units_added"] >= b["severny_confirmed_addresses_added"]


def test_scenario_B_impact_is_isolated_from_optimiser_drift(repo_root):
    b = _audit(repo_root)["scenarios"]["scenario_B"]
    ctrl = b["control_recompute_without_severny"]
    assert ctrl["existing_units_changing_zone"] == 0, "baseline drift must be zero"
    assert b["existing_delivery_units_changing_zone"] >= 0


# --- (5) preserved guarantees ------------------------------------------------

def test_k4_direction_and_no_money_preserved(repo_root):
    a = _audit(repo_root)
    assert a["decided_k"] == 4
    assert "Scenario A" in a["production_direction"]
    assert a["prices_assigned"] is False and a["direct_integration"] is False
    assert _json(repo_root, "docs/data/tariff-band-metrics.json")[
        "recommendation"]["decided_k"] == 4


def test_severny_not_declared_added(repo_root):
    a = _audit(repo_root)
    assert a["resolved"] is False
    fc = _json(repo_root, "docs/data/severny-service-area.geojson")
    assert fc["chosen"] is False
    assert fc["resolution_status"] == "candidate_pending_owner_review"
    assert fc["features"][0]["properties"]["resolution"] == "owner_review_required"


# --- final export cleanup ----------------------------------------------------

def test_varnita_admin_reference_is_line_geometry(repo_root):
    """The admin claim must be impossible to render as a filled area."""
    fc = _json(repo_root, "docs/data/varnita-admin-reference.geojson")
    for f in fc["features"]:
        assert f["geometry"]["type"] in ("LineString", "MultiLineString")
        assert f["properties"]["geometry_kind"] == "boundary_line"
        assert "filled" not in f["properties"]


def test_severny_popup_uses_existing_fields(repo_root):
    """app.js must not read fields the footprint no longer publishes."""
    app = (repo_root / "docs/app.js").read_text(encoding="utf-8")
    block = app[app.index("Северный — жилой контур"):]
    block = block[:block.index("overlays[", 10)] if "overlays[" in block[10:] else block
    assert "p.building_count" not in block
    assert "p.official_address_format" not in block
    for field in ("final_included_buildings", "confirmed_address_count",
                  "apartment_building_count"):
        assert field in block, field
    assert "Нумерация 1–105 не подтверждена для импорта" in app
    props = _json(repo_root, "docs/data/severny-service-area.geojson")[
        "features"][0]["properties"]
    for field in ("final_included_buildings", "confirmed_address_count",
                  "apartment_building_count", "north_of_varnita_village", "note"):
        assert field in props, f"popup reads {field} but the data lacks it"


def test_units_have_stable_identity(repo_root):
    units = _units(repo_root)
    seen = set()
    for u in units:
        for field in ("uid", "osm_type", "osm_id", "settlement_ru", "district_ru",
                      "address_status", "source_dataset_version"):
            assert u[field], field
        assert u["osm_type"] in ("n", "w")
        assert u["uid"] == f"{u['osm_type']}{u['osm_id']}"
        assert u["uid"] not in seen, "unit ids must be unique"
        seen.add(u["uid"])
        assert u["settlement_ru"] == "Бендеры"
        assert u["district_ru"] == "Северный"
        assert u["source_dataset_version"].startswith("moldova-pbf:")


def test_canonical_key_only_for_verified_osm_addresses(repo_root):
    for u in _units(repo_root):
        if u["address_status"] == "verified_osm_address":
            assert u["canonical_address_key"], "verified address needs a canonical key"
            assert u["housenumber"] and u["street_ru"]
        else:
            assert not u["canonical_address_key"], \
                "unverified/unaddressed units must not get a canonical key"


def test_no_canonical_keys_invented_for_external_house_numbers(repo_root):
    keys = {u["canonical_address_key"] for u in _units(repo_root)
            if u["canonical_address_key"]}
    ref = _audit(repo_root)["external_address_reference"]
    for hn in ref["external_example_house_numbers"]:
        bogus = f"бендеры|северный|микрорайон северный|{hn.lower()}"
        assert bogus not in keys, "external 1-105 houses must not become addresses"


def test_readiness_is_published_explicitly(repo_root):
    r = _audit(repo_root)["per_unit_report"]["readiness"]
    assert r["geometry_ready"] is True
    assert r["zone_assignment_ready"] is True
    assert r["direct_export_ready"] is False
    assert r["address_catalog_ready"] is False
    assert r["verified_osm_addresses"] == 7
    assert r["unaddressed_delivery_units"] == 50
    assert "verified mapping" in r["missing_requirement"]


def test_readiness_matches_the_unit_data(repo_root):
    r = _audit(repo_root)["per_unit_report"]["readiness"]
    units = _units(repo_root)
    verified = sum(1 for u in units if u["address_status"] == "verified_osm_address")
    unaddressed = sum(1 for u in units
                      if u["address_status"] == "unaddressed_delivery_unit")
    assert r["verified_osm_addresses"] == verified
    assert r["unaddressed_delivery_units"] == unaddressed


def test_all_severny_units_remain_in_zone_4(repo_root):
    for u in _units(repo_root):
        assert u["assigned_zone"] == "4"
