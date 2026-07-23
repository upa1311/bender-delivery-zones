"""Stage-03 candidate service area: housing-density trimming rules.

Offline: pure geometry logic plus assertions on the committed map artifacts.
No PBF, no network, no osmium-tool.
"""

from __future__ import annotations

import json

from shapely.geometry import LineString, Point, Polygon, shape

from bender_zones import jsonutil
from bender_zones.service_trim import (
    EXCLUSION_REASONS,
    INCLUSION_REASONS,
    REASON_ACCESS,
    REASON_ADDRESSED,
    REASON_DENSE,
    TrimParams,
    area_m2,
    build_candidate_geometry,
    clip_to_side,
    drop_small_components,
    polygon_components,
    reduction_pct,
    side_of_line,
    street_is_relevant,
)

PARAMS = TrimParams()
REQUIRED_KEYS = {"bender_core", "bender_lipcani", "protyagailovka", "giska", "parkany"}
VARNITA_TOKENS = ("varnita", "varniț", "варниц")


def _load(repo_root, name):
    return json.loads((repo_root / "docs/data" / name).read_text(encoding="utf-8"))


def _report(repo_root):
    return json.loads((repo_root / "reports/stage-03/service-area-trimming.json")
                      .read_text(encoding="utf-8"))


def _square(cx, cy, half):
    return Polygon([(cx - half, cy - half), (cx + half, cy - half),
                    (cx + half, cy + half), (cx - half, cy + half)])


# --- street relevance rules -------------------------------------------------

def test_street_without_buildings_does_not_extend_area():
    relevant, reason = street_is_relevant(0, 0, False, PARAMS)
    assert relevant is False
    assert reason is None


def test_street_with_enough_buildings_is_included():
    relevant, reason = street_is_relevant(PARAMS.min_buildings_near_street, 0, False, PARAMS)
    assert relevant is True
    assert reason == REASON_DENSE


def test_street_with_enough_addressed_buildings_is_included():
    relevant, reason = street_is_relevant(
        0, PARAMS.min_addressed_buildings_near_street, False, PARAMS)
    assert relevant is True
    assert reason == REASON_ADDRESSED


def test_required_access_road_is_preserved():
    # An access road to an included cluster survives even with no houses on it.
    relevant, reason = street_is_relevant(0, 0, True, PARAMS)
    assert relevant is True
    assert reason == REASON_ACCESS


def test_short_street_with_houses_is_not_dropped_for_length():
    short = LineString([(0, 0), (25, 0)])  # 25 m long
    geom = build_candidate_geometry([], [short], PARAMS)
    assert not geom.is_empty
    assert street_is_relevant(6, 0, False, PARAMS)[0] is True


# --- fields are never included just because of the admin boundary -----------

def test_fields_inside_admin_boundary_are_not_included():
    """A huge admin polygon must not pull empty land into the candidate."""
    boundary = _square(0, 0, 2000)                       # 4 km x 4 km admin area
    houses = [_square(0, 0, 8), _square(30, 0, 8), _square(60, 0, 8)]
    geom = build_candidate_geometry(houses, [], PARAMS).intersection(boundary)
    assert area_m2(geom) < 0.02 * area_m2(boundary)      # far smaller than the boundary
    assert not geom.covers(Point(1500, 1500))            # a distant field stays out


def test_distant_clusters_are_not_bridged_by_empty_land():
    a = [_square(0, 0, 8), _square(20, 0, 8)]
    b = [_square(1500, 0, 8), _square(1520, 0, 8)]
    geom = build_candidate_geometry(a + b, [], PARAMS)
    assert len(polygon_components(geom)) == 2            # no hull across the gap
    assert not geom.covers(Point(750, 0))                # the field between stays out


# --- isolated clusters go to the sparse review layer ------------------------

def test_small_isolated_cluster_goes_to_sparse_review():
    big = [_square(x * 20, 0, 8) for x in range(8)]      # 8 buildings
    small = [_square(2000 + x * 20, 0, 8) for x in range(2)]   # 2 buildings, far away
    points = [g.centroid for g in big + small]
    geom = build_candidate_geometry(big + small, [], PARAMS)
    kept, sparse = drop_small_components(geom, points, PARAMS)
    assert len(sparse) == 1
    assert sparse[0][1] == 2                             # the two-building group
    assert not kept.covers(points[-1])                   # dropped from the candidate


# --- owner limit clipping ---------------------------------------------------

def test_clip_to_side_keeps_only_the_requested_side():
    poly = _square(0, 0, 100)
    line = LineString([(0, -500), (0, 500)])             # vertical divider
    kept, applied = clip_to_side(poly, line, Point(50, 0))
    assert applied is True
    assert kept.covers(Point(50, 0))
    assert not kept.covers(Point(-50, 0))


def test_reduction_pct_math():
    assert reduction_pct(100.0, 25.0) == 75.0
    assert reduction_pct(0.0, 0.0) == 0.0


# --- committed artifacts ----------------------------------------------------

def test_candidate_has_the_five_separate_features(repo_root):
    fc = _load(repo_root, "candidate-service-area.geojson")
    keys = {f["properties"]["key"] for f in fc["features"]}
    assert keys == REQUIRED_KEYS
    assert len(fc["features"]) == 5          # kept separate, NOT merged


def test_varnita_is_absent_everywhere(repo_root):
    for name in ("candidate-service-area.geojson", "source-boundaries.geojson"):
        blob = (repo_root / "docs/data" / name).read_text(encoding="utf-8").lower()
        assert not any(tok in blob for tok in VARNITA_TOKENS), f"Varnița leaked into {name}"


def test_zones_are_not_created(repo_root):
    diff = _load(repo_root, "service-area-diff.json")
    assert diff["zones_created"] is False
    assert diff["routing_created"] is False
    assert diff["merged_production_polygon"] is False
    report = _report(repo_root)
    assert report["zones_created"] is False
    assert report["direct_integration"] is False
    assert report["osm_boundaries_modified"] is False
    for props in (f["properties"] for f in
                  _load(repo_root, "candidate-service-area.geojson")["features"]):
        assert props["zones_created"] is False


def test_every_candidate_is_smaller_than_its_source(repo_root):
    diff = _load(repo_root, "service-area-diff.json")
    for key, d in diff["territories"].items():
        assert d["candidate_area_km2"] < d["source_area_km2"], key
        assert d["reduction_pct"] > 0, key


def test_giska_and_lipcani_are_substantially_reduced(repo_root):
    diff = _load(repo_root, "service-area-diff.json")["territories"]
    for key in ("giska", "bender_lipcani"):
        d = diff[key]
        assert d["candidate_area_km2"] < d["source_area_km2"]
        assert d["reduction_pct"] >= 25.0, key


def test_parkany_does_not_use_the_whole_council_relation(repo_root):
    diff = _load(repo_root, "service-area-diff.json")["territories"]["parkany"]
    assert diff["source_relation"] == 7431263
    # The working area follows the built-up village, not the whole village council.
    assert diff["candidate_area_km2"] < 0.25 * diff["source_area_km2"]
    assert diff["reduction_pct"] > 75.0


def test_sparse_review_layer_only_holds_small_groups(repo_root):
    fc = _load(repo_root, "sparse-building-review.geojson")
    assert fc["features"], "expected some sparse groups for review"
    for f in fc["features"]:
        p = f["properties"]
        assert p["status"] == "sparse_building_review"
        assert p["buildings"] < PARAMS.min_component_buildings


def test_excluded_areas_use_the_documented_reason_vocabulary(repo_root):
    fc = _load(repo_root, "excluded-large-areas.geojson")
    assert fc["features"]
    for f in fc["features"]:
        assert f["properties"]["reason"] in EXCLUSION_REASONS


def test_inclusion_reasons_use_the_documented_vocabulary(repo_root):
    fc = _load(repo_root, "candidate-service-area.geojson")
    for f in fc["features"]:
        for reason in f["properties"]["inclusion_reasons"]:
            assert reason in INCLUSION_REASONS
        for reason in f["properties"]["exclusion_reasons"]:
            assert reason in EXCLUSION_REASONS


def test_protyagailovka_covers_both_sides_of_glavnaya(repo_root):
    """Owner correction: Glavnaya is included in full, houses on BOTH sides.

    The earlier "exclude everything left of Glavnaya" clip is cancelled, so the
    candidate must now have area on both sides of the street.
    """
    # Stage 04 is the current authoritative builder for the candidate geometry.
    report04 = json.loads((repo_root / "reports/stage-04/residential-demand-audit.json")
                          .read_text(encoding="utf-8"))
    meta = report04["owner_limits"]["protyagailovka"]
    assert meta["clipped_by_side"] is False
    assert "Главная улица" in meta["include_full_length_streets"]

    questions = json.loads((repo_root / "docs/data/boundary-questions.geojson")
                           .read_text(encoding="utf-8"))
    line_feat = next(f for f in questions["features"]
                     if f["properties"].get("street") == "Главная улица")
    line = LineString(line_feat["geometry"]["coordinates"])

    geom = None
    for f in _load(repo_root, "candidate-service-area.geojson")["features"]:
        if f["properties"]["key"] == "protyagailovka":
            geom = shape(f["geometry"])
    assert geom is not None

    tolerance_deg = 5.0 / 111320.0  # ignore vertices sitting on the line itself
    sides = set()
    for poly in polygon_components(geom):
        for x, y in poly.exterior.coords:
            pt = Point(x, y)
            if pt.distance(line) <= tolerance_deg:
                continue
            side = side_of_line(line, pt)
            if side != 0.0:
                sides.add(side)
    assert sides == {1.0, -1.0}, f"expected both sides of Главная, got {sides}"


def test_source_boundaries_are_kept_as_a_separate_untouched_layer(repo_root):
    fc = _load(repo_root, "source-boundaries.geojson")
    assert fc["features"]
    for f in fc["features"]:
        p = f["properties"]
        assert p["kind"] == "source_osm_boundary"
        assert p["osm_type"] == "relation"
        assert "не изменял" in p["note"].lower() or "не изменя" in p["note"]


def test_boundary_questions_are_published(repo_root):
    fc = _load(repo_root, "boundary-questions.geojson")
    assert fc["features"], "ambiguous owner wording must be published, not guessed"
    for f in fc["features"]:
        assert f["properties"]["layer"] == "protyagailovka_boundary_questions"
        assert f["properties"]["question"]


def test_kavkaz_landmark_status_is_reported(repo_root):
    k = _report(repo_root)["kavkaz_landmark"]
    assert "resolved" in k
    if k["resolved"]:
        assert k["chosen"]["osm_id"] and k["chosen"]["place"]
    else:
        # Never invent a coordinate: surface the message and the options instead.
        assert k["message"] == "Kavkaz landmark unresolved"
        assert k["candidates"]


# --- determinism ------------------------------------------------------------

def test_stage03_geojson_is_canonical_and_deterministic(repo_root):
    for name in ("source-boundaries.geojson", "candidate-service-area.geojson",
                 "excluded-large-areas.geojson", "sparse-building-review.geojson",
                 "buildings.geojson"):
        text = (repo_root / "docs/data" / name).read_text(encoding="utf-8")
        assert jsonutil.dumps_compact(json.loads(text)) == text, name


def test_geometry_construction_is_deterministic():
    houses = [_square(x * 30, 0, 9) for x in range(6)]
    streets = [LineString([(0, 0), (150, 0)])]
    first = build_candidate_geometry(houses, streets, PARAMS)
    second = build_candidate_geometry(houses, streets, PARAMS)
    assert first.equals(second)
    assert first.wkt == second.wkt
