#!/usr/bin/env python
"""Stage 03 — derive the CANDIDATE working service area from housing density.

Local-only pipeline (needs the Moldova PBF + osmium-tool). Produces:

* docs/data/source-boundaries.geojson       untouched OSM admin boundaries (reference)
* docs/data/candidate-service-area.geojson  bender_core, bender_lipcani,
                                            protyagailovka, giska, parkany
* docs/data/excluded-large-areas.geojson    farmland / forest / empty land, with reasons
* docs/data/sparse-building-review.geojson  isolated groups below the threshold
* docs/data/boundary-questions.geojson      owner-wording ambiguities to confirm
* docs/data/service-area-diff.json          areas, reduction %, building counts
* reports/stage-03/service-area-trimming.{json,md}

It never edits OSM data, never merges the candidates into one production polygon,
and creates no zones, tariffs or routing.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import osmium
from shapely import voronoi_polygons
from shapely.geometry import LineString, MultiPoint, Point, Polygon, mapping, shape
from shapely.ops import linemerge, unary_union
from shapely.strtree import STRtree

from bender_zones import jsonutil
from bender_zones.config import load_audit, load_sources
from bender_zones.extract import extract_boundary
from bender_zones.service_area import classify_road, load_service_area
from bender_zones.service_trim import (
    EXCL_EMPTY,
    EXCL_FARMLAND,
    EXCL_FOREST_PARK,
    EXCL_OWNER_LIMIT,
    EXCL_SPARSE,
    REASON_ACCESS,
    REASON_DENSE,
    REASON_OWNER,
    REASON_STREET,
    TrimParams,
    area_m2,
    build_candidate_geometry,
    clip_to_side,
    count_points_within,
    drop_small_components,
    local_projection,
    points_within,
    polygon_components,
    reduction_pct,
    side_of_line,
    street_is_relevant,
    to_degrees,
    to_metres,
)

WARNING_RU = ("Рабочая территория создана по плотности жилой застройки и указаниям "
              "владельца. Это ещё не четыре зоны доставки.")

FARMLAND_TAGS = {"farmland", "farmyard", "orchard", "vineyard", "meadow", "greenhouse_horticulture"}
FOREST_TAGS = {"forest", "wood", "scrub", "grass", "park", "garden", "nature_reserve",
               "cemetery", "recreation_ground"}


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- OSM feature extraction -------------------------------------------------

class CityFeatures:
    def __init__(self):
        self.building_polys = []      # metric polygons/points
        self.building_points = []     # metric centroids
        self.addressed_points = []    # metric points of addr:housenumber objects
        self.streets = []             # dicts: name, osm_id, geom (metric)
        self.landuse = []             # (metric polygon, tags)
        self.places = []              # (osm_id, tags, metric Point)


def load_city_features(city_pbf: Path, proj) -> CityFeatures:
    feats = CityFeatures()
    for obj in osmium.FileProcessor(str(city_pbf)).with_locations():
        tags = {k: v for k, v in obj.tags}
        kind = obj.type_str()

        if kind == "n":
            pt = Point(*proj.to_m(obj.lon, obj.lat))
            if tags.get("building") is not None:
                feats.building_polys.append(pt)
                feats.building_points.append(pt)
            if tags.get("addr:housenumber") is not None:
                feats.addressed_points.append(pt)
            if tags.get("place") is not None or tags.get("name"):
                feats.places.append((obj.id, tags, pt))
            continue

        if kind != "w":
            continue

        coords = []
        ok = True
        for nd in obj.nodes:
            if not nd.location.valid():
                ok = False
                break
            coords.append(proj.to_m(nd.lon, nd.lat))
        if not ok or len(coords) < 2:
            continue

        is_closed = len(coords) >= 4 and coords[0] == coords[-1]

        if tags.get("building") is not None:
            if is_closed:
                try:
                    poly = Polygon(coords)
                    if poly.is_valid and poly.area > 0:
                        feats.building_polys.append(poly)
                        feats.building_points.append(poly.centroid)
                except Exception:
                    pass
            if tags.get("addr:housenumber") is not None and feats.building_points:
                feats.addressed_points.append(feats.building_points[-1])
            continue

        if tags.get("addr:housenumber") is not None and is_closed:
            try:
                feats.addressed_points.append(Polygon(coords).centroid)
            except Exception:
                pass

        landuse_val = tags.get("landuse") or tags.get("natural") or tags.get("leisure")
        if landuse_val and is_closed:
            try:
                poly = Polygon(coords)
                if poly.is_valid and poly.area > 0:
                    feats.landuse.append((poly, tags))
            except Exception:
                pass
            continue

        if tags.get("highway") is not None and tags.get("name"):
            road_class, is_address, _ = classify_road(tags)
            if is_address:
                feats.streets.append({"name": tags["name"], "osm_id": obj.id,
                                      "geom": LineString(coords), "road_class": road_class})
    return feats


# --- candidate construction -------------------------------------------------

def select_relevant_streets(feats: CityFeatures, params: TrimParams):
    """Two passes: density/addresses first, then required access roads."""
    building_tree = STRtree(feats.building_points) if feats.building_points else None
    addressed_tree = STRtree(feats.addressed_points) if feats.addressed_points else None

    scored = []
    for st in feats.streets:
        corridor = st["geom"].buffer(params.street_building_radius_m)
        n_b = 0
        if building_tree is not None:
            n_b = sum(1 for i in building_tree.query(corridor)
                      if corridor.covers(feats.building_points[int(i)]))
        n_a = 0
        if addressed_tree is not None:
            n_a = sum(1 for i in addressed_tree.query(corridor)
                      if corridor.covers(feats.addressed_points[int(i)]))
        relevant, reason = street_is_relevant(n_b, n_a, False, params)
        scored.append({**st, "buildings_near": n_b, "addressed_near": n_a,
                       "relevant": relevant, "reason": reason})

    primary = [s for s in scored if s["relevant"]]
    if not primary:
        return scored, primary

    core = unary_union([s["geom"].buffer(params.street_buffer_m) for s in primary])
    # Pass 2: a street that touches the included fabric and serves at least one
    # building is kept as a required access road.
    for s in scored:
        if s["relevant"] or s["buildings_near"] < 1:
            continue
        if s["geom"].intersects(core):
            s["relevant"] = True
            s["reason"] = REASON_ACCESS
    return scored, [s for s in scored if s["relevant"]]


def build_territory_candidate(feats: CityFeatures, boundary_m, params: TrimParams):
    scored, relevant = select_relevant_streets(feats, params)
    geom = build_candidate_geometry(feats.building_polys,
                                    [s["geom"] for s in relevant], params)
    geom = geom.intersection(boundary_m)
    kept, sparse = drop_small_components(geom, feats.building_points, params)
    return kept, sparse, scored, relevant


# --- excluded areas ---------------------------------------------------------

def _exclusion_reason(tags: dict) -> str:
    value = tags.get("landuse") or tags.get("natural") or tags.get("leisure") or ""
    if value in FARMLAND_TAGS:
        return EXCL_FARMLAND
    if value in FOREST_TAGS:
        return EXCL_FOREST_PARK
    return EXCL_EMPTY


def collect_excluded_areas(boundary_m, candidate_m, feats: CityFeatures,
                           params: TrimParams, territory: str):
    """Large parts of the admin boundary that the candidate deliberately drops."""
    out = []
    leftover = boundary_m.difference(candidate_m)
    if leftover.is_empty:
        return out, leftover

    explained = []
    for poly, tags in feats.landuse:
        piece = poly.intersection(leftover)
        if piece.is_empty or area_m2(piece) < params.min_excluded_area_m2:
            continue
        explained.append(piece)
        out.append({"geom": piece, "reason": _exclusion_reason(tags),
                    "name": tags.get("name"), "territory": territory,
                    "landuse": tags.get("landuse") or tags.get("natural")
                    or tags.get("leisure")})

    remainder = leftover
    if explained:
        remainder = leftover.difference(unary_union(explained))
    for comp in polygon_components(remainder):
        if area_m2(comp) >= params.min_empty_land_area_m2:
            out.append({"geom": comp, "reason": EXCL_EMPTY, "name": None,
                        "territory": territory, "landuse": None})
    return out, leftover


# --- geojson helpers --------------------------------------------------------

def _feature(geom_deg, props: dict) -> dict:
    return {"type": "Feature", "properties": props,
            "geometry": _round_geom(mapping(geom_deg))}


def _round_geom(obj, nd: int = 5):
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, (list, tuple)):
        return [_round_geom(x, nd) for x in obj]
    if isinstance(obj, dict):
        return {k: _round_geom(v, nd) for k, v in obj.items()}
    return obj


def _out(geom_m, proj, params: TrimParams):
    """Simplify in metres, then convert to WGS84 for output."""
    if geom_m.is_empty:
        return geom_m
    simplified = geom_m.simplify(params.simplify_tolerance_m)
    if simplified.is_empty:
        simplified = geom_m
    return to_degrees(simplified, proj)


def build(pbf: Path, repo_root: Path) -> int:
    import yaml
    cfg = yaml.safe_load((repo_root / "config" / "service-trim.yml").read_text(encoding="utf-8"))
    params = TrimParams(**cfg["parameters"])
    audit_cfg = load_audit(repo_root / "config" / "audit.yml")
    sa_cfg = load_service_area(repo_root / "config" / "service-area.yml")
    workdir = repo_root / audit_cfg.workdir

    territories = cfg["territories"]
    relations = sorted({t["source_relation"] for t in territories})

    # --- load each distinct source relation once ---
    sources = {}
    for rel in relations:
        result = extract_boundary(pbf, rel, workdir, strategy=audit_cfg.osmium_strategy)
        gj = jsonutil_load(result.boundary_geojson)
        boundary_deg = None
        for f in gj.get("features", []):
            g = shape(f["geometry"])
            if g.geom_type in ("Polygon", "MultiPolygon"):
                boundary_deg = g
                break
        if boundary_deg is None:
            print(f"error: no polygon for relation {rel}", file=sys.stderr)
            return 2
        c = boundary_deg.centroid
        proj = local_projection(c.y, c.x)
        sources[rel] = {
            "boundary_deg": boundary_deg,
            "proj": proj,
            "boundary_m": to_metres(boundary_deg, proj),
            "features": load_city_features(result.city_pbf, proj),
        }

    # --- landmark resolution (Kavkaz) ---
    landmark_cfg = cfg.get("landmarks", {}).get("kavkaz", {})
    kavkaz = _resolve_landmark(sources, landmark_cfg)

    candidate_features = []
    source_features = []
    excluded_features = []
    sparse_features = []
    question_features = []
    diff = {}
    notes = []
    owner_limit_meta: dict = {}
    building_layers: list = []

    # --- per source relation: one candidate, later split for Bender ---
    computed = {}
    for rel, src in sources.items():
        kept, sparse, scored, relevant = build_territory_candidate(
            src["features"], src["boundary_m"], params)
        computed[rel] = {"candidate_m": kept, "sparse": sparse,
                         "scored": scored, "relevant": relevant}

    for terr in territories:
        key = terr["key"]
        rel = terr["source_relation"]
        src = sources[rel]
        proj = src["proj"]
        comp = computed[rel]
        candidate_m = comp["candidate_m"]
        source_m = src["boundary_m"]
        feats = src["features"]
        inclusion = {REASON_DENSE, REASON_STREET}
        exclusion = set()
        if any(s["reason"] == REASON_ACCESS for s in comp["relevant"]):
            inclusion.add(REASON_ACCESS)
        if feats.addressed_points:
            inclusion.add("addressed_buildings")

        # --- Bender is split into Lipcani and the rest by suburb Voronoi cell ---
        role = terr.get("role")
        if role in ("bender_suburb", "bender_rest"):
            lipcani_node = next((t.get("suburb_place_node") for t in territories
                                 if t.get("role") == "bender_suburb"), None)
            cell = _lipcani_cell(feats, lipcani_node, sources[rel])
            if cell is None:
                notes.append("Lipcani suburb node not found; Bender left unsplit.")
            elif role == "bender_suburb":
                candidate_m = candidate_m.intersection(cell)
                source_m = source_m.intersection(cell)
                inclusion.add(REASON_OWNER)
            else:
                candidate_m = candidate_m.difference(cell)
                source_m = source_m.difference(cell)

        # --- owner-named limit streets (Protyagailovka) ---
        limits = terr.get("owner_limits")
        if limits:
            candidate_m, applied, qs, limit_meta = _apply_owner_limits(
                candidate_m, feats, limits, proj, params)
            inclusion.add(REASON_OWNER)
            if applied:
                exclusion.add(EXCL_OWNER_LIMIT)
            question_features.extend(qs)
            if limit_meta:
                owner_limit_meta[key] = limit_meta

        # --- Kavkaz: exclude the empty land to the east of the landmark ---
        if kavkaz and kavkaz["territory"] == key and kavkaz["resolved"]:
            anchor = Point(*proj.to_m(kavkaz["lon"], kavkaz["lat"]))
            east_empty = _east_empty_area(source_m, candidate_m, anchor, params)
            if not east_empty.is_empty:
                excluded_features.append(_feature(_out(east_empty, proj, params), {
                    "territory": key, "reason": EXCL_OWNER_LIMIT,
                    "note": "поля справа (восточнее) ориентира «Кавказ» — исключены",
                    "area_m2": round(area_m2(east_empty)),
                }))
                exclusion.add(EXCL_OWNER_LIMIT)

        # --- stats ---
        inside_pts = points_within(candidate_m, feats.building_points)
        source_pts = points_within(source_m, feats.building_points)
        inside_set = {id(p) for p in inside_pts}
        outside_pts = [p for p in source_pts if id(p) not in inside_set]
        b_in = len(inside_pts)
        b_total = len(source_pts)
        addr_in = count_points_within(candidate_m, feats.addressed_points)
        building_layers.append((key, True, [proj.to_deg(p.x, p.y) for p in inside_pts]))
        building_layers.append((key, False, [proj.to_deg(p.x, p.y) for p in outside_pts]))
        src_area, cand_area = area_m2(source_m), area_m2(candidate_m)

        for _poly, _n in comp["sparse"]:
            exclusion.add(EXCL_SPARSE)
        for tag_reason in {_exclusion_reason(t) for _p, t in feats.landuse}:
            exclusion.add(tag_reason)

        diff[key] = {
            "display_ru": terr["display_ru"],
            "source_relation": rel,
            "source_area_km2": round(src_area / 1e6, 4),
            "candidate_area_km2": round(cand_area / 1e6, 4),
            "reduction_pct": reduction_pct(src_area, cand_area),
            "buildings_included": b_in,
            "buildings_excluded": max(b_total - b_in, 0),
            "addresses_inside": addr_in,
            "inclusion_reasons": sorted(inclusion),
            "exclusion_reasons": sorted(exclusion),
        }

        candidate_features.append(_feature(_out(candidate_m, proj, params), {
            "key": key, "display_ru": terr["display_ru"], "kind": "candidate_working_area",
            "source_relation": rel, "zones_created": False,
            **{k: diff[key][k] for k in ("source_area_km2", "candidate_area_km2",
                                         "reduction_pct", "buildings_included",
                                         "buildings_excluded", "addresses_inside",
                                         "inclusion_reasons", "exclusion_reasons")},
        }))

    # --- source boundaries (untouched reference layer) ---
    for entry in sa_cfg.allowed:
        rel = entry.osm_id
        if rel not in sources:
            continue
        src = sources[rel]
        source_features.append(_feature(_out(src["boundary_m"], src["proj"], params), {
            "key": entry.key, "display_ru": entry.display_ru, "kind": "source_osm_boundary",
            "osm_type": "relation", "osm_id": rel,
            "area_km2": round(area_m2(src["boundary_m"]) / 1e6, 4),
            "note": "Исходная административная граница OSM. Не изменялась.",
        }))

    # --- excluded + sparse layers per relation ---
    for terr in territories:
        rel, key = terr["source_relation"], terr["key"]
        if terr.get("role") == "bender_suburb":
            continue  # reported under bender_core to avoid duplicate geometry
        src, comp = sources[rel], computed[rel]
        proj = src["proj"]
        excl, _ = collect_excluded_areas(src["boundary_m"], comp["candidate_m"],
                                         src["features"], params, key)
        for item in excl:
            excluded_features.append(_feature(_out(item["geom"], proj, params), {
                "territory": key, "reason": item["reason"], "name": item["name"],
                "landuse": item["landuse"], "area_m2": round(area_m2(item["geom"])),
            }))
        for poly, n in comp["sparse"]:
            sparse_features.append(_feature(_out(poly, proj, params), {
                "territory": key, "status": "sparse_building_review",
                "buildings": n, "reason": EXCL_SPARSE,
                "note": "Изолированная группа <5 зданий — требует решения владельца.",
            }))

    _write_outputs(repo_root, cfg, params, candidate_features, source_features,
                   excluded_features, sparse_features, question_features, diff,
                   kavkaz, notes, owner_limit_meta, building_layers)
    print(f"territories: {len(candidate_features)} | excluded: {len(excluded_features)} "
          f"| sparse: {len(sparse_features)} | questions: {len(question_features)}")
    for k, v in diff.items():
        print(f"  {k}: {v['source_area_km2']} -> {v['candidate_area_km2']} km2 "
              f"(-{v['reduction_pct']}%) buildings {v['buildings_included']}"
              f"/+{v['buildings_excluded']} excl, addr {v['addresses_inside']}")
    return 0


def jsonutil_load(path: Path) -> dict:
    import json
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _resolve_landmark(sources, landmark_cfg):
    """Find the Kavkaz landmark; never invent a coordinate."""
    if not landmark_cfg:
        return None
    names = [n.casefold() for n in landmark_cfg.get("search_names", [])]
    matches = []
    for _rel, src in sources.items():
        proj = src["proj"]
        for osm_id, tags, pt in src["features"].places:
            for field in ("name", "name:ru", "alt_name", "official_name"):
                val = tags.get(field)
                if val and any(n == val.casefold() or n in val.casefold() for n in names):
                    lon, lat = proj.to_deg(pt.x, pt.y)
                    matches.append({"osm_id": osm_id, "name": val, "field": field,
                                    "place": tags.get("place"), "lon": round(lon, 6),
                                    "lat": round(lat, 6),
                                    "tags": {k: v for k, v in tags.items()
                                             if k in ("place", "name", "name:ru", "amenity")}})
                    break
    # Prefer an unambiguous place=* object (a district), not a POI of the same name.
    place_matches = [m for m in matches if m["place"]]
    resolved = len(place_matches) == 1
    chosen = place_matches[0] if resolved else None
    return {
        "resolved": resolved,
        "territory": landmark_cfg.get("territory"),
        "direction": landmark_cfg.get("exclude_direction"),
        "chosen": chosen,
        "candidates": matches,
        "lon": chosen["lon"] if chosen else None,
        "lat": chosen["lat"] if chosen else None,
        "message": None if resolved else "Kavkaz landmark unresolved",
    }


def _lipcani_cell(feats: CityFeatures, lipcani_node_id: int, src: dict):
    """Voronoi cell of the Lipcani suburb node among Bender's place nodes.

    Lipcani has no separate OSM boundary, so its share of Bender is approximated
    by the Voronoi cell of its ``place=suburb`` node. Both bender_lipcani (which
    intersects the cell) and bender_core (which subtracts it) use the same cell,
    so together they exactly tile the Bender candidate and stay connected.
    """
    suburb_pts = [(oid, pt) for oid, tags, pt in feats.places if tags.get("place") in
                  ("suburb", "quarter", "neighbourhood", "city", "town")]
    if len(suburb_pts) < 2:
        return None
    target = next((pt for oid, pt in suburb_pts if oid == lipcani_node_id), None)
    if target is None:
        return None
    mp = MultiPoint([pt for _oid, pt in suburb_pts])
    cells = voronoi_polygons(mp, extend_to=src["boundary_m"].envelope)
    for cell in cells.geoms:
        if cell.covers(target):
            return cell
    return None


def _apply_owner_limits(candidate_m, feats: CityFeatures, limits: dict, proj,
                        params: TrimParams):
    """Clip by the owner's left-limit street; publish ambiguities as questions.

    The owner's wording ("the left edge runs along Glavnaya, exclude everything
    to the left of it") does not map onto a compass direction here: Glavnaya runs
    SW-NE, and the other owner-named limit streets (Munteanu, Lesovaya) lie to
    its *west*. Reading "left" as "west" would delete the very streets the owner
    named as limits. So instead of guessing a compass side we apply an explicit,
    deterministic rule -- keep the side of Glavnaya that contains the owner's
    other named limit streets -- and publish the ambiguity as a map question.
    """
    questions = []
    applied = False
    meta: dict = {}
    left_name = limits.get("left_limit_street")
    other_names = list(limits.get("limit_streets", []))

    def street_line(name):
        segs = [s["geom"] for s in feats.streets if s["name"] == name]
        if not segs:
            return None
        merged = linemerge(segs) if len(segs) > 1 else segs[0]
        if merged.geom_type == "MultiLineString":
            merged = max(merged.geoms, key=lambda g: g.length)
        return merged

    other_lines = [ln for ln in (street_line(n) for n in other_names) if ln is not None]

    if left_name:
        line = street_line(left_name)
        if line is None:
            questions.append(_question(proj, candidate_m,
                                       f"Улица «{left_name}» не найдена в OSM — "
                                       "левый предел не применён.", kind="unresolved"))
        else:
            if other_lines:
                keep_point = unary_union(other_lines).centroid
                rule = ("сторона, на которой лежат другие названные владельцем "
                        "предельные улицы (Мунтяна, Лесовая, Первомайская)")
            else:
                keep_point = candidate_m.centroid
                rule = "сторона с основной жилой застройкой"
            clipped, applied = clip_to_side(candidate_m, line, keep_point)
            kept_sign = side_of_line(line, keep_point)
            if applied:
                candidate_m = clipped
            line_deg = to_degrees(line, proj)
            meta = {
                "left_limit_street": left_name,
                "applied": applied,
                "keep_rule": rule,
                "kept_side_sign": kept_sign,
                "line_lonlat": [[round(x, 6), round(y, 6)] for x, y in line_deg.coords],
            }
            questions.append(_question(
                proj, line,
                f"«Левее» улицы «{left_name}» невозможно свести к стороне света: "
                "улица идёт с юго-запада на северо-восток, а названные владельцем "
                "предельные улицы Мунтяна и Лесовая лежат западнее неё. "
                f"Оставлена {rule}"
                f"{'; отсечение применено' if applied else '; отсечение НЕ применено'}. "
                "Подтвердите сторону.",
                kind="interpretation" if applied else "unresolved"))
            questions.append(_line_feature(line_deg, {
                "layer": "protyagailovka_boundary_questions",
                "kind": "limit_street", "street": left_name,
                "role": "left_limit", "question": "Левый предел по указанию владельца.",
            }))

    for name in other_names:
        line = street_line(name)
        if line is None:
            questions.append(_question(proj, candidate_m,
                                       f"Предельная улица «{name}» не найдена в OSM.",
                                       kind="unresolved"))
            continue
        questions.append(_line_feature(to_degrees(line, proj), {
            "layer": "protyagailovka_boundary_questions",
            "kind": "limit_street", "street": name, "role": "side_limit",
            "question": (f"Улица «{name}» названа владельцем как предел. Какая именно "
                         "сторона («с одной стороны» / «с другой стороны») имелась в "
                         "виду — не задано однозначно; застройка вдоль улицы включена."),
        }))
    return candidate_m, applied, questions, meta


def _question(proj, geom_m, text: str, kind: str = "question"):
    geom = geom_m.centroid if geom_m.geom_type in ("Polygon", "MultiPolygon") else geom_m
    if geom.geom_type == "LineString":
        geom = geom.centroid
    return _feature(to_degrees(geom, proj), {
        "layer": "protyagailovka_boundary_questions",
        "kind": kind, "question": text,
    })


def _line_feature(line_deg, props: dict) -> dict:
    """A limit street drawn on the questions layer so the owner can see the line."""
    return _feature(line_deg, props)


def _east_empty_area(source_m, candidate_m, anchor: Point, params: TrimParams):
    """Empty land east of the landmark that the candidate excludes."""
    minx, miny, maxx, maxy = source_m.bounds
    east = Polygon([(anchor.x, miny - 1000), (maxx + 1000, miny - 1000),
                    (maxx + 1000, maxy + 1000), (anchor.x, maxy + 1000)])
    leftover = source_m.intersection(east).difference(candidate_m)
    keep = [c for c in polygon_components(leftover)
            if area_m2(c) >= params.min_empty_land_area_m2]
    return unary_union(keep) if keep else Polygon()


def _write_outputs(repo_root, cfg, params, candidate_features, source_features,
                   excluded_features, sparse_features, question_features, diff,
                   kavkaz, notes, owner_limit_meta, building_layers):
    data_dir = repo_root / "docs" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    def fc(features):
        return {"type": "FeatureCollection", "features": features}

    candidate_features.sort(key=lambda f: f["properties"]["key"])
    source_features.sort(key=lambda f: f["properties"]["osm_id"])
    excluded_features.sort(key=lambda f: (f["properties"]["territory"],
                                          f["properties"]["reason"],
                                          -f["properties"].get("area_m2", 0)))
    sparse_features.sort(key=lambda f: (f["properties"]["territory"],
                                        -f["properties"]["buildings"]))

    jsonutil.write_compact(data_dir / "source-boundaries.geojson", fc(source_features))
    jsonutil.write_compact(data_dir / "candidate-service-area.geojson", fc(candidate_features))
    jsonutil.write_compact(data_dir / "excluded-large-areas.geojson", fc(excluded_features))
    jsonutil.write_compact(data_dir / "sparse-building-review.geojson", fc(sparse_features))
    jsonutil.write(data_dir / "boundary-questions.geojson", fc(question_features))

    # Buildings as compact MultiPoint groups (one per territory x inside/outside):
    # ~24k individual features would bloat the repo and the page load.
    building_features = []
    for terr_key, inside, pts in sorted(building_layers, key=lambda x: (x[0], not x[1])):
        if not pts:
            continue
        building_features.append({
            "type": "Feature",
            "properties": {"territory": terr_key, "inside_candidate": inside,
                           "count": len(pts)},
            "geometry": {"type": "MultiPoint",
                         "coordinates": [[round(lon, 5), round(lat, 5)] for lon, lat in pts]},
        })
    jsonutil.write_compact(data_dir / "buildings.geojson", fc(building_features))

    generated = _utc_now_iso()
    diff_doc = {
        "schema": "bender-service-area-diff/3",
        "generated_at": generated,
        "zones_created": False,
        "routing_created": False,
        "merged_production_polygon": False,
        "warning_ru": WARNING_RU,
        "territories": diff,
        "totals": {
            "territories": len(diff),
            "source_area_km2": round(sum(v["source_area_km2"] for v in diff.values()), 4),
            "candidate_area_km2": round(sum(v["candidate_area_km2"] for v in diff.values()), 4),
            "buildings_included": sum(v["buildings_included"] for v in diff.values()),
            "buildings_excluded": sum(v["buildings_excluded"] for v in diff.values()),
            "addresses_inside": sum(v["addresses_inside"] for v in diff.values()),
        },
    }
    jsonutil.write(data_dir / "service-area-diff.json", diff_doc)

    reports = repo_root / "reports" / "stage-03"
    reports.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "bender-service-area-trimming/3",
        "generated_at": generated,
        "zones_created": False,
        "routing_created": False,
        "direct_integration": False,
        "osm_boundaries_modified": False,
        "parameters": cfg["parameters"],
        "territories": diff,
        "kavkaz_landmark": kavkaz,
        "owner_limits": owner_limit_meta,
        "boundary_questions": [f["properties"] for f in question_features],
        "sparse_building_review_count": len(sparse_features),
        "excluded_area_count": len(excluded_features),
        "notes": notes,
        "limitations": [
            "The candidate working area is NOT an official boundary and does not "
            "replace the OSM administrative boundaries, which are unmodified.",
            "No popularity/traffic data exists; street relevance is proxied by "
            "residential fabric (buildings and addresses near the street).",
            "The five candidates are deliberately NOT merged into one production "
            "polygon, and no delivery zones, tariffs or routing were created.",
            "Lipcani has no separate OSM boundary; it is separated from the rest of "
            "Bender by the Voronoi cell of its place=suburb node — an approximation "
            "to confirm with the owner.",
            "OSM building/address coverage is community-contributed and incomplete.",
        ],
    }
    jsonutil.write(reports / "service-area-trimming.json", report)
    (reports / "service-area-trimming.md").write_text(
        _render_md(report, diff_doc), encoding="utf-8", newline="\n")


def _render_md(report: dict, diff_doc: dict) -> str:
    lines = ["# Stage 03 — candidate working service area (housing density)", "",
             f"- Generated (UTC): `{report['generated_at']}`",
             f"- zones_created: **{report['zones_created']}** · routing: "
             f"**{report['routing_created']}** · Direct: **{report['direct_integration']}**",
             f"- OSM boundaries modified: **{report['osm_boundaries_modified']}**", "",
             "> " + WARNING_RU, "",
             "## Areas per territory", "",
             "| Территория | Source км² | Candidate км² | Сокращение | Здания вкл. |"
             " Здания искл. | Адреса |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for key, v in report["territories"].items():
        lines.append(f"| {v['display_ru']} (`{key}`) | {v['source_area_km2']} | "
                     f"{v['candidate_area_km2']} | {v['reduction_pct']}% | "
                     f"{v['buildings_included']} | {v['buildings_excluded']} | "
                     f"{v['addresses_inside']} |")
    lines += ["", "## Inclusion / exclusion reasons", ""]
    for v in report["territories"].values():
        lines += [f"- **{v['display_ru']}** — включено: "
                  f"{', '.join('`'+r+'`' for r in v['inclusion_reasons'])}; исключено: "
                  f"{', '.join('`'+r+'`' for r in v['exclusion_reasons']) or '—'}"]
    k = report["kavkaz_landmark"] or {}
    lines += ["", "## Ориентир «Кавказ»", ""]
    if k.get("resolved"):
        c = k["chosen"]
        lines += [f"- Найден: **{c['name']}** (node {c['osm_id']}, place={c['place']}), "
                  f"lon/lat {c['lon']}/{c['lat']}",
                  f"- Применено: исключены незастроенные территории к востоку "
                  f"({k.get('direction')})."]
    else:
        lines += ["- **Kavkaz landmark unresolved** — однозначный объект не выбран.",
                  "- Возможные совпадения для выбора владельцем:"]
        for c in k.get("candidates", []):
            lines += [f"  - node {c['osm_id']} «{c['name']}» place={c['place']} "
                      f"({c['lon']}/{c['lat']})"]
    lines += ["", "## Спорные места (boundary questions)", ""]
    qs = report["boundary_questions"]
    lines += [f"- [{q['kind']}] {q['question']}" for q in qs] or ["- нет"]
    lines += ["", "## Limitations", ""]
    lines += [f"- {x}" for x in report["limitations"]]
    lines += [""]
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pbf", default=None)
    parser.add_argument("--source", default="osm_moldova")
    parser.add_argument("--repo-root", default=".")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root)
    sources = load_sources(repo_root / "config" / "sources.yml")
    pbf = repo_root / (args.pbf or sources[args.source].destination)
    if not pbf.is_file():
        print(f"error: PBF not found: {pbf}", file=sys.stderr)
        return 2
    return build(pbf, repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
