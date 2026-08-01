"""Extract REAL geometry for the three Bender boundary candidates — ANALYSIS ONLY.

Priority of sources (per corrective brief):
  1. local Moldova PBF + stage-01 pipeline  -> NOT available in this checkout
     (data/raw/moldova-latest.osm.pbf is gitignored & absent; pyosmium/osmium not
     installed). Provenance of that PBF is recorded from reports/stage-01.
  2. a pinned reproducible OSM extract       -> not committed here
  3. official OSM API / Overpass             -> USED (local source insufficient)

For each relation this fetches the full geometry (`out geom meta`) from Overpass,
saves the raw response + sha256, assembles outer/inner rings into a (multi)polygon,
repairs validity, and records every provenance/geometry field the brief requires.
Nothing here is applied to production and no boundary is marked VERIFIED_FOR_TARIFF.

Reproducible: `python scripts/extract_osm_boundaries.py`. Cached raw responses under
data/interim/osm-boundaries/raw are reused (no network) unless --refresh is passed.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
import time
import urllib.request
from pathlib import Path

from shapely.geometry import mapping
from shapely.ops import linemerge, polygonize, unary_union

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/interim/osm-boundaries"
RAW_DIR = OUT_DIR / "raw"
STAGE01 = ROOT / "reports/stage-01/source-audit.json"
PROV_JSON = OUT_DIR / "boundary-extraction-provenance.json"
CAPTURE_LOG = OUT_DIR / "extraction-capture-log.json"


def _now_utc():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
OSM_URL = "https://www.openstreetmap.org/relation/{}"

# The three candidates. 9581354 & 944727 come from the project brief
# (config/boundary-candidates.yml); 12463379 is the admin_level-8 city polygon the
# repo previously used in source-boundaries.geojson (labelled a provisional proxy).
RELATIONS = {
    "12463379": "Bender city (admin_level 8) — repo provisional proxy, NOT a brief candidate",
    "9581354": "Municipiul Bender (admin_level 4) — brief: de-jure municipality",
    "944727": "Tighina / Bender City Council (admin_level 5) — brief: de-facto PMR city",
}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _overpass(query: str) -> bytes:
    """POST an Overpass query, retrying across mirrors with in-process backoff for
    429/timeout. Raises the last error if every attempt fails (recorded, not faked).
    """
    last = None
    for attempt in range(6):
        ep = OVERPASS_ENDPOINTS[attempt % len(OVERPASS_ENDPOINTS)]
        try:
            req = urllib.request.Request(
                ep, data=query.encode("utf-8"),
                headers={"User-Agent": "bender-delivery-zones-audit"})
            return urllib.request.urlopen(req, timeout=180).read()  # noqa: S310
        except Exception as e:  # noqa: BLE001
            last = e
            wait = 15 * (attempt + 1)
            print(f"  overpass {ep} attempt {attempt+1} failed: "
                  f"{type(e).__name__}; waiting {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"all overpass endpoints failed: {type(last).__name__}: {last}")


def fetch(rid: str, refresh: bool) -> dict:
    raw_path = RAW_DIR / f"relation-{rid}.overpass.json"
    if raw_path.exists() and not refresh:
        return json.loads(raw_path.read_text(encoding="utf-8"))
    query = f"[out:json][timeout:120];rel({rid});out geom meta;"
    data = _overpass(query)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    # store pretty + LF so the checksum is stable and diffable
    obj = json.loads(data)
    raw_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True),
                        encoding="utf-8", newline="\n")
    return obj


def assemble(rel: dict):
    """Assemble a (multi)polygon from a relation's way members (outer/inner roles)."""
    outer_lines, inner_lines = [], []
    for m in rel.get("members", []):
        if m.get("type") != "way" or not m.get("geometry"):
            continue
        coords = [(p["lon"], p["lat"]) for p in m["geometry"]]
        if len(coords) < 2:
            continue
        (inner_lines if m.get("role") == "inner" else outer_lines).append(coords)
    from shapely.geometry import LineString
    outers = list(polygonize(linemerge([LineString(c) for c in outer_lines])))
    inners = list(polygonize(linemerge([LineString(c) for c in inner_lines]))) \
        if inner_lines else []
    if not outers:
        return None
    geom = unary_union(outers)
    for hole in inners:
        geom = geom.difference(hole)
    return geom


def _metric(geom):
    """Project lon/lat to a local equirectangular metre CRS at the centroid."""
    lat0 = geom.centroid.y
    mx, my = 111320.0 * math.cos(math.radians(lat0)), 110540.0
    from shapely.affinity import affine_transform
    return affine_transform(geom, [mx, 0, 0, my, 0, 0])


def _bbox(geom):
    x0, y0, x1, y1 = geom.bounds
    return {"min_lon": round(x0, 6), "min_lat": round(y0, 6),
            "max_lon": round(x1, 6), "max_lat": round(y1, 6)}


def _parts_holes(geom):
    if geom.geom_type == "Polygon":
        return 1, len(geom.interiors)
    if geom.geom_type == "MultiPolygon":
        return len(geom.geoms), sum(len(p.interiors) for p in geom.geoms)
    return 0, 0


def stage01_tags():
    if not STAGE01.exists():
        return {}
    d = json.loads(STAGE01.read_text(encoding="utf-8"))
    out = {}
    for c in d.get("candidates", []):
        rel = c.get("relation", {}) or {}
        out[str(c.get("id"))] = rel.get("tags", {}) or {}
    return out


def process(rid: str, note: str, refresh: bool, s01: dict, capture_log: dict) -> dict:
    rel_wrap = fetch(rid, refresh)
    raw_bytes = (RAW_DIR / f"relation-{rid}.overpass.json").read_bytes()
    rel = next((e for e in rel_wrap.get("elements", []) if e.get("type") == "relation"), None)
    if rel is None:
        return {"relation_id": rid, "error": "relation not found in response"}
    tags = rel.get("tags", {})
    raw_geom = assemble(rel)
    valid_before = bool(raw_geom.is_valid) if raw_geom is not None else False
    geom = raw_geom
    repaired = False
    if geom is not None and not geom.is_valid:
        geom = geom.buffer(0)
        repaired = True
    parts, holes = _parts_holes(geom) if geom is not None else (0, 0)
    area_km2 = round(_metric(geom).area / 1e6, 4) if geom is not None else None

    geojson = {"type": "Feature",
               "properties": {"relation_id": rid, "name": tags.get("name"),
                              "admin_level": tags.get("admin_level"),
                              "source": "OpenStreetMap via Overpass (ODbL)"},
               "geometry": mapping(geom) if geom is not None else None}
    geo_path = OUT_DIR / f"relation-{rid}.geojson"
    geo_text = json.dumps(geojson, ensure_ascii=False, indent=2, sort_keys=True)
    geo_path.write_text(geo_text, encoding="utf-8", newline="\n")

    s01_t = s01.get(rid, {})
    name_diverges = bool(s01_t) and s01_t.get("name") != tags.get("name")
    query = f"[out:json][timeout:120];rel({rid});out geom meta;"
    retrieval = capture_log.get(rid)
    return {
        "relation_id": rid, "note": note, "osm_url": OSM_URL.format(rid),
        "name": tags.get("name"), "name_ru": tags.get("name:ru"),
        "object_type": tags.get("type"), "boundary": tags.get("boundary"),
        "admin_level": tags.get("admin_level"), "place": tags.get("place"),
        "wikidata": tags.get("wikidata"), "iso3166_2": tags.get("ISO3166-2"),
        "osm_note": tags.get("note"),
        "version": rel.get("version"),
        # three DISTINCT timestamps, never conflated:
        "source_object_timestamp": rel.get("timestamp"),   # when the OSM object was edited
        "original_retrieval_timestamp_utc": retrieval or "HISTORICAL_METADATA_UNAVAILABLE",
        "changeset": rel.get("changeset"),
        "extraction_source": "Overpass API",
        "extraction_endpoints": OVERPASS_ENDPOINTS,
        "extraction_query": query,
        "extraction_command": ('curl -sS --data-urlencode '
                               f"'data={query}' {OVERPASS_ENDPOINTS[0]}"),
        "reproducibility_command": "python scripts/extract_osm_boundaries.py "
                                   "(offline replay of cached raw) | --capture (network)",
        "license": "ODbL — © OpenStreetMap contributors",
        "raw_artifact_path": f"data/interim/osm-boundaries/raw/relation-{rid}.overpass.json",
        "geometry_artifact_path": f"data/interim/osm-boundaries/relation-{rid}.geojson",
        "raw_to_geometry": "geometry assembled from the raw way members "
                           "(outer/inner roles) via shapely polygonize+difference",
        "raw_sha256": _sha(raw_bytes), "geometry_sha256": _sha(geo_text.encode("utf-8")),
        "source_crs": "EPSG:4326", "output_crs": "EPSG:4326",
        "geometry_type": geom.geom_type if geom is not None else None,
        "valid_before_repair": valid_before,
        "valid_after_repair": bool(geom.is_valid) if geom is not None else False,
        "repair_operation": "shapely buffer(0)" if repaired else "none",
        "area_km2": area_km2, "polygon_parts": parts, "holes": holes,
        "bbox": _bbox(geom) if geom is not None else None,
        "member_count": len(rel.get("members", [])),
        "pbf_provenance": {
            "note": "Canonical stage-01 used a local Moldova PBF (not in this clone)",
            "pbf_local_path": "data/raw/moldova-latest.osm.pbf",
            "pbf_sha256": "09ba0c058e89faacac7e1b1e7c8d0fbb14b4df66061b43abdce590b65ce8813c",
            "pbf_resolved_url": "https://download.geofabrik.de/europe/moldova-260722.osm.pbf",
            "stage01_snapshot_tags_present": bool(s01_t),
            "stage01_name": s01_t.get("name"),
            "name_diverges_from_pbf_snapshot": name_diverges,
        },
    }


def main():
    capture = "--capture" in sys.argv or "--refresh" in sys.argv
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    s01 = stage01_tags()
    capture_log = json.loads(CAPTURE_LOG.read_text(encoding="utf-8")) \
        if CAPTURE_LOG.exists() else {}
    if capture:
        # NETWORK: refetch each relation and stamp the true retrieval time now
        for rid in RELATIONS:
            fetch(rid, refresh=True)
            capture_log[rid] = _now_utc()
        CAPTURE_LOG.write_text(json.dumps(capture_log, ensure_ascii=False, indent=2),
                               encoding="utf-8", newline="\n")
    records = [process(rid, note, False, s01, capture_log)
               for rid, note in RELATIONS.items()]
    PROV_JSON.write_text(
        json.dumps({"generated_by": "scripts/extract_osm_boundaries.py",
                    "relations": records}, ensure_ascii=False, indent=2),
        encoding="utf-8", newline="\n")
    for r in records:
        print(json.dumps({k: r.get(k) for k in
                          ("relation_id", "name", "admin_level", "version",
                           "geometry_type", "area_km2", "polygon_parts", "holes",
                           "valid_before_repair", "raw_sha256")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
