"""Verified outside-city route distance for the external tariff — ANALYSIS layer.

Computes outside_city_km GEOMETRICALLY (route polyline ∩ Bender city boundary),
never by straight line, territory name or a share of total route_km. Where a
verified per-address route polyline is not available, the address is left
unpriced with an explicit status — no invented value.

Boundary: docs/data/source-boundaries.geojson, key=bender (OSM relation 12463379,
"Исходная административная граница OSM. Не изменялась."). Route polylines:
docs/data/stage-09b-map-routes.geojson, kind=fastest_time — the same OSRM
fixed-origin routes whose length equals the canonical route_km to within metres.

Projection: pyproj is unavailable here, so a deterministic local equirectangular
projection centred on the dispatch origin (46.82388, 29.48313) is used —
x = (lon-lon0)·111320·cos(lat0), y = (lat-lat0)·111320. Over this ~10 km study
area its length error is < 0.1 %; it is validated by the polyline length matching
canonical route_km to < 2 m. All geometric ops run in this metric CRS.

Analysis/test layer only — production, Direct, releases, routing graph, canonical
addresses, fixed-origin routes, GitHub Pages and live tariffs are untouched.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path

from shapely.geometry import LineString, shape

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "owner_tariff_model", ROOT / "scripts/owner_tariff_model.py")
OT = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(OT)
ZE = OT.ZE

BOUNDARIES = ROOT / "docs/data/source-boundaries.geojson"
MAP_ROUTES = ROOT / "docs/data/stage-09b-map-routes.geojson"
OUT_CSV = ROOT / "data/interim/outside-city-distance-v1.csv"
CONTROLS_CSV = ROOT / "data/interim/outside-city-control-addresses-v1.csv"
SUMMARY_JSON = ROOT / "reports/zone-model-audit/_outside-city-summary-v1.json"
OWNER_MD = ROOT / "reports/zone-model-audit/outside-city-distance-v1.md"

ORIGIN_LAT, ORIGIN_LON = 46.82388, 29.48313
MX = 111320.0 * math.cos(math.radians(ORIGIN_LAT))
MY = 111320.0
# Length consistency: accept a polyline as the canonical route when its length is
# within max(0.05 km, 1% of route_km) — the three available routes match to < 2 m.
LENGTH_TOL_KM = 0.05
LENGTH_TOL_FRAC = 0.01
EXTERNAL_TERRITORIES = ("Парканы", "Гиска", "Протягайловка", "Северный")
# Северный aliases checked when investigating its absence from the 9,216 canonical set.
SEVERNY_ALIASES = ("Северный", "Severny", "Severnyy", "Nord", "микрорайон Северный")


def project(lon: float, lat: float) -> tuple[float, float]:
    return ((lon - ORIGIN_LON) * MX, (lat - ORIGIN_LAT) * MY)


def _valid(geom):
    return geom if geom.is_valid else geom.buffer(0)


def outside_length_km(route_line: LineString, boundary_poly) -> float:
    """Kilometres of a metric route LineString lying OUTSIDE the metric city
    polygon. shapely.difference handles: multiple crossings, fully inside (0),
    fully outside (full length), touching the edge (0), multipolygon and holes
    (a hole is not-city, so a route through it counts as outside)."""
    outside = route_line.difference(_valid(boundary_poly))
    return outside.length / 1000.0


def load_city_boundary():
    data = json.loads(BOUNDARIES.read_text(encoding="utf-8"))
    feature = next((f for f in data["features"]
                    if f["properties"].get("key") == "bender"), None)
    if feature is None:
        return None, None
    ring = shape(feature["geometry"])
    projected = _project_geom(ring)
    return _valid(projected), feature["properties"]


def _project_geom(geom):
    def ring(coords):
        return [project(x, y) for x, y in coords]
    from shapely.geometry import MultiPolygon, Polygon
    if geom.geom_type == "Polygon":
        return Polygon(ring(geom.exterior.coords),
                       [ring(h.coords) for h in geom.interiors])
    if geom.geom_type == "MultiPolygon":
        return MultiPolygon([
            Polygon(ring(p.exterior.coords), [ring(h.coords) for h in p.interiors])
            for p in geom.geoms])
    raise ValueError(f"unexpected boundary geometry {geom.geom_type}")


def load_route_polylines():
    """uid -> {coords(lon,lat), length_km} for the canonical fastest route."""
    data = json.loads(MAP_ROUTES.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for f in data["features"]:
        p = f["properties"]
        if p.get("kind") != "fastest_time":
            continue
        uid = p.get("uid")
        coords = f["geometry"]["coordinates"]
        if uid and len(coords) >= 2:
            out[uid] = {"coords": coords, "distance_km": p.get("distance_km")}
    return out


def _polyline_length_km(coords):
    pts = [project(x, y) for x, y in coords]
    return sum(math.hypot(b[0] - a[0], b[1] - a[1])
               for a, b in zip(pts, pts[1:], strict=False)) / 1000.0


def compute(address, boundary, boundary_props, polylines):
    """Return the full result row for one external address."""
    uid = address["uid"]
    km = address["route_km"]
    base = OT.base_city_fee(km)
    row = {
        "canonical_address_id": uid,
        "address": f'{address["street"]} {address["house"]}',
        "territory": address["settlement"], "latitude": ZE.ZM._round(address["lat"], 6),
        "longitude": ZE.ZM._round(address["lon"], 6), "route_km": ZE.ZM._round(km),
        "route_geometry_source": "", "polyline_length_km": "",
        "route_length_difference": "", "boundary_source": "",
        "outside_city_km": "", "base_city_fee": base, "external_surcharge": "",
        "final_fee": "", "calculation_status": "", "status_reason": "",
        "geographic_zone_analytics_only": address["zone_id"],
    }
    if boundary is None:
        row["calculation_status"] = "CITY_BOUNDARY_UNAVAILABLE"
        row["status_reason"] = "no bender polygon in source-boundaries.geojson"
        return row
    row["boundary_source"] = (
        f'source-boundaries.geojson#{boundary_props.get("key")} '
        f'({boundary_props.get("osm_type")} {boundary_props.get("osm_id")})')
    poly = polylines.get(uid)
    if poly is None:
        row["calculation_status"] = "ROUTE_GEOMETRY_UNAVAILABLE"
        row["status_reason"] = (
            "no per-address route polyline stored; only canonical route_km exists. "
            "Regenerating requires the OSRM engine + protected routing graph.")
        return row
    length = _polyline_length_km(poly["coords"])
    diff = abs(length - km)
    row["route_geometry_source"] = "stage-09b-map-routes.geojson#fastest_time"
    row["polyline_length_km"] = ZE.ZM._round(length, 4)
    row["route_length_difference"] = ZE.ZM._round(diff, 4)
    tol = max(LENGTH_TOL_KM, LENGTH_TOL_FRAC * km)
    if diff > tol:
        row["calculation_status"] = "ROUTE_LENGTH_MISMATCH"
        row["status_reason"] = f"polyline {length:.3f} km vs route_km {km:.3f} > tol {tol:.3f}"
        return row
    try:
        line = LineString([project(x, y) for x, y in poly["coords"]])
        if not line.is_valid:
            row["calculation_status"] = "INVALID_ROUTE_GEOMETRY"
            row["status_reason"] = "route polyline is not a valid LineString"
            return row
        outside = outside_length_km(line, boundary)
    except Exception as exc:  # noqa: BLE001 — record, never invent
        row["calculation_status"] = "INVALID_ROUTE_GEOMETRY"
        row["status_reason"] = f"geometry op failed: {type(exc).__name__}"
        return row
    # numeric guards: 0 <= outside <= route_km (+ small justified tolerance)
    outside = max(0.0, min(outside, km + tol))
    surcharge = OT.external_surcharge(outside)
    row["outside_city_km"] = ZE.ZM._round(outside, 4)
    row["external_surcharge"] = surcharge
    row["final_fee"] = base + surcharge
    row["calculation_status"] = "CALCULATED"
    row["status_reason"] = "route ∩ bender boundary, projected metric CRS"
    return row


def _stats(vals):
    vals = sorted(v for v in vals if v != "")
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "min": vals[0], "median": ZE._pct(vals, 0.5), "max": vals[-1]}


def investigate_severny(all_rows):
    present = any(r["settlement"] in SEVERNY_ALIASES for r in all_rows)
    sev_file = ROOT / "docs/data/severny-delivery-units.csv"
    external_count = 0
    if sev_file.exists():
        with sev_file.open(encoding="utf-8-sig", newline="") as h:
            external_count = sum(1 for _ in csv.DictReader(h))
    return {
        "in_canonical_9216": present,
        "aliases_checked": list(SEVERNY_ALIASES),
        "separate_source_addresses": external_count,
        "separate_source_file": "docs/data/severny-delivery-units.csv",
        "gap": ("Северный is NOT among the 9,216 canonical addresses (verified via "
                "settlement + alias scan). A separate non-canonical source "
                "(severny-delivery-units.csv) exists; promoting it into the canonical "
                "release is a PRODUCTION change and is out of scope here."),
        "status": "TERRITORY_DATA_UNAVAILABLE",
    }


def main():
    rows_all = ZE.ZM.load_addresses()  # via zone_model_audit through ZE.ZM
    external = [r for r in rows_all if r["settlement"] in ("Парканы", "Гиска", "Протягайловка")]
    boundary, bprops = load_city_boundary()
    polylines = load_route_polylines()

    results = [compute(a, boundary, bprops, polylines)
               for a in sorted(external, key=lambda r: r["uid"])]

    header = ["canonical_address_id", "address", "territory", "latitude", "longitude",
              "route_km", "route_geometry_source", "polyline_length_km",
              "route_length_difference", "boundary_source", "outside_city_km",
              "base_city_fee", "external_surcharge", "final_fee", "calculation_status",
              "status_reason", "geographic_zone_analytics_only"]
    with OUT_CSV.open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=header, lineterminator="\n")
        w.writeheader()
        w.writerows(results)

    # >= 30 control examples: all CALCULATED + representative others per territory
    controls = [r for r in results if r["calculation_status"] == "CALCULATED"]
    for terr in ("Парканы", "Гиска", "Протягайловка"):
        terr_rows = [r for r in results if r["territory"] == terr]
        terr_rows.sort(key=lambda r: float(r["route_km"]))
        for r in terr_rows[:4] + terr_rows[len(terr_rows) // 2:len(terr_rows) // 2 + 3] \
                + terr_rows[-3:]:
            if r not in controls:
                controls.append(r)
    # dedupe, keep >=30
    seen, deduped = set(), []
    for r in controls:
        if r["canonical_address_id"] not in seen:
            seen.add(r["canonical_address_id"])
            deduped.append(r)
    with CONTROLS_CSV.open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=header, lineterminator="\n")
        w.writeheader()
        w.writerows(deduped)

    by_status: dict[str, int] = {}
    for r in results:
        by_status[r["calculation_status"]] = by_status.get(r["calculation_status"], 0) + 1
    per_territory = {}
    for terr in ("Парканы", "Гиска", "Протягайловка"):
        tr = [r for r in results if r["territory"] == terr]
        calc = [r for r in tr if r["calculation_status"] == "CALCULATED"]
        per_territory[terr] = {
            "total_addresses": len(tr),
            "valid_route_polylines": sum(1 for r in tr if r["polyline_length_km"] != ""),
            "geometry_verified_calculated": len(calc),
            "priced_addresses": len(calc),
            "unavailable_addresses": len(tr) - len(calc),
            "unavailable_reasons": {s: sum(1 for r in tr if r["calculation_status"] == s)
                                    for s in sorted({r["calculation_status"] for r in tr})
                                    if s != "CALCULATED"},
            "route_km_stats": _stats([float(r["route_km"]) for r in tr]),
            "outside_city_km_stats": _stats([float(r["outside_city_km"]) for r in calc]),
            "final_fee_stats": _stats([r["final_fee"] for r in calc]),
        }

    boundary_checksum = hashlib.sha256(BOUNDARIES.read_bytes()).hexdigest()
    summary = {
        "verdict": "PARTIAL_COVERAGE_OWNER_REVIEW_REQUIRED",
        "boundary_provenance": {
            "file": "docs/data/source-boundaries.geojson", "key": "bender",
            "osm": (f'{bprops.get("osm_type")} {bprops.get("osm_id")}' if bprops else None),
            "area_km2": (bprops.get("area_km2") if bprops else None),
            "note": (bprops.get("note") if bprops else None),
            "input_crs": "EPSG:4326",
            "working_projection": ("local equirectangular at origin 46.82388,29.48313; "
                                   "<0.1% length error over the study area"),
            "manual_edits": "none",
            "sha256": boundary_checksum,
        },
        "route_geometry_provenance": {
            "file": "docs/data/stage-09b-map-routes.geojson", "kind": "fastest_time",
            "provider": "OSRM (stage-09 engine)", "origin": [ORIGIN_LAT, ORIGIN_LON],
            "length_tolerance_km": "max(0.05, 1% * route_km)",
            "note": ("only 3 external addresses have a stored canonical polyline; "
                     "their polyline length matches route_km to < 2 m."),
        },
        "external_addresses_total": len(external),
        "priced_addresses_total": by_status.get("CALCULATED", 0),
        "status_counts": by_status,
        "per_territory": per_territory,
        "severny": investigate_severny(rows_all),
        "note": "Analysis/test layer only; no production/Direct/release/tariff change.",
    }
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8", newline="\n")
    _write_md(summary, deduped, header)
    print(json.dumps({"priced": summary["priced_addresses_total"],
                      "status_counts": by_status}, ensure_ascii=False))


def _write_md(summary, controls, header):
    b = summary["boundary_provenance"]
    lines = [
        "# Verified outside-city route distance — analysis v1", "",
        f"**Verdict: {summary['verdict']}**. Analysis/test layer only; production,",
        "Direct, releases, routing graph, canonical addresses, fixed-origin routes,",
        "GitHub Pages and live tariffs are untouched. Numbers generated from",
        "`data/interim/outside-city-distance-v1.csv`.", "",
        "## City boundary provenance", "",
        f"- File: `{b['file']}` key `{b['key']}` — OSM {b['osm']}, area {b['area_km2']} km²",
        f"- Note: {b['note']}",
        f"- Input CRS {b['input_crs']}; working projection: {b['working_projection']}",
        f"- Manual edits: {b['manual_edits']}; sha256 `{b['sha256'][:16]}…`", "",
        "## Route geometry provenance", "",
        f"- File: `{summary['route_geometry_provenance']['file']}` "
        f"kind `{summary['route_geometry_provenance']['kind']}`, "
        f"{summary['route_geometry_provenance']['provider']}",
        f"- Length tolerance: {summary['route_geometry_provenance']['length_tolerance_km']}",
        f"- {summary['route_geometry_provenance']['note']}", "",
        "## Outside-city method", "",
        "Project route + boundary to the metric CRS; `outside_city_km = length("
        "route.difference(boundary)) / 1000`. Handles multiple crossings, fully "
        "inside (0), fully outside, edge-touching (0), multipolygon and holes; "
        "invalid geometry is repaired with buffer(0) or flagged. Guards: "
        "`0 ≤ outside_city_km ≤ route_km + tol`. Tariff: "
        "`base_city_fee + max(5, ceil(outside_city_km*2))`.", "",
        "## Coverage per external territory", "",
        "| Territory | Total | Valid polylines | Priced (geometry-verified) | Unavailable |",
        "|---|---:|---:|---:|---:|",
    ]
    for terr, t in summary["per_territory"].items():
        lines.append(f"| {terr} | {t['total_addresses']} | {t['valid_route_polylines']} | "
                     f"{t['priced_addresses']} | {t['unavailable_addresses']} |")
    lines += ["", "### Status counts (all external)", ""]
    for s, n in sorted(summary["status_counts"].items()):
        lines.append(f"- {s}: {n}")
    sv = summary["severny"]
    lines += ["", "## Северный", "",
              f"- In canonical 9,216: **{sv['in_canonical_9216']}** "
              f"(aliases checked: {', '.join(sv['aliases_checked'])})",
              f"- Separate non-canonical source: {sv['separate_source_addresses']} rows in "
              f"`{sv['separate_source_file']}`", f"- {sv['gap']}", "",
              "## Control addresses (from data)", "",
              "| id | territory | route_km | polyline_km | outside_km | final_fee | status |",
              "|---|---|---:|---:|---:|---:|---|"]
    for r in controls:
        lines.append(
            f"| {r['canonical_address_id']} | {r['territory']} | {r['route_km']} | "
            f"{r['polyline_length_km'] or '—'} | {r['outside_city_km'] or '—'} | "
            f"{r['final_fee'] if r['final_fee'] != '' else '—'} | {r['calculation_status']} |")
    lines += ["", "## Blocker / gap", "",
              "Only 3 of the external addresses have a stored canonical route polyline, "
              "so only those are geometry-priced. The remaining external addresses are "
              "`ROUTE_GEOMETRY_UNAVAILABLE`. **Minimal fix:** persist (or regenerate with "
              "the same OSRM engine, profile and central origin that produced the "
              "canonical route_km) the per-address `fastest_time` polylines for every "
              "external address, then re-run this script — no other change is required. "
              "Northern (Северный) additionally needs its addresses promoted into the "
              "canonical release (a production step, out of scope).", "",
              "Verdict: PARTIAL_COVERAGE_OWNER_REVIEW_REQUIRED.", ""]
    OWNER_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
