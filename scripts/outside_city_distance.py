"""Outside-city route & city-boundary audit — ANALYSIS/TEST layer only.

Key finding: the repository itself documents the Bender OSM boundary
(relation 12463379) as a **provisional proxy** — `stage-09-recompute-summary.json`:
"exact point unknown; current Bender OSM boundary is a provisional proxy". No
reproducible source proves it (or relation 9581354 / 944727) is the APPROVED
operational tariff switch boundary. UPDATE (commit 6d4679c): the full geometry of
ALL THREE candidate relations (12463379, 9581354, 944727) has since been EXTRACTED
from OSM (Overpass, ODbL) and stored under data/interim/osm-boundaries/, so the
earlier "no geometry in repo" state for 9581354 / 944727 no longer holds; the
unified suitability comparison is boundary-candidates-comparison-v2.csv. Still, none
is approved for tariff, so NO external address receives an approved final_fee: the
verdict is BLOCKED_BY_CITY_BOUNDARY. Geometry that CAN be computed (route ∩ each
candidate polygon) is emitted only as clearly-labelled SCENARIO analytics, never as
a production price.

Route inventory: all central-origin external `fastest` polylines from BOTH
stage-09a-control-routes.geojson (9) and stage-09b-map-routes.geojson (3) = 12
unique routes (deduped by canonical_address_id, length-validated to < 5 m).

Analysis/test layer only — production, Direct, releases, routing graph, canonical
addresses, fixed-origin routes, driver cabinet, the driver zone switch, operational
dispatch zones, GitHub Pages and live tariffs are untouched; nothing invented.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path

from shapely.geometry import LineString, MultiPolygon, Polygon, shape

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "owner_tariff_model", ROOT / "scripts/owner_tariff_model.py")
OT = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(OT)
ZE = OT.ZE

BOUNDARIES = ROOT / "docs/data/source-boundaries.geojson"
BOUNDARY_CANDIDATES = ROOT / "config/boundary-candidates.yml"
RECOMPUTE_SUMMARY = ROOT / "docs/data/stage-09-recompute-summary.json"
SEVERNY_FILE = ROOT / "docs/data/severny-delivery-units.csv"
ROUTE_SOURCES = [
    ("docs/data/stage-09a-control-routes.geojson", "fastest",
     "stage-09 control-route audit"),
    ("docs/data/stage-09b-map-routes.geojson", "fastest_time",
     "stage-09 district-entry map routes"),
]

OUT_CSV = ROOT / "data/interim/outside-city-distance-v1.csv"
SCENARIO_CSV = ROOT / "data/interim/outside-city-boundary-scenarios-v1.csv"
INVENTORY_CSV = ROOT / "data/interim/outside-city-route-inventory-v1.csv"
CONTROLS_CSV = ROOT / "data/interim/outside-city-control-addresses-v1.csv"
SUMMARY_JSON = ROOT / "reports/zone-model-audit/_outside-city-summary-v1.json"
OWNER_MD = ROOT / "reports/zone-model-audit/outside-city-distance-v1.md"

ORIGIN_LAT, ORIGIN_LON = 46.82388, 29.48313
MX = 111320.0 * math.cos(math.radians(ORIGIN_LAT))
MY = 111320.0
LENGTH_TOL_KM, LENGTH_TOL_FRAC = 0.05, 0.01     # route acceptance
CONFLICT_TOL_KM, CONFLICT_TOL_FRAC = 0.02, 0.005  # dedup: same-uid polyline disagreement
SENSITIVITY_THRESHOLDS_KM = [0.005, 0.01, 0.02, 0.05, 0.1]
EXTERNAL_SETTLEMENTS = ("Парканы", "Гиска", "Протягайловка")
SEVERNY_ALIASES = ("Северный", "Severny", "Severnyy", "Nord", "микрорайон Северный",
                   "Severnii", "Nordul")
# Candidate tariff boundaries to compare. Only 'bender' has geometry in the repo.
BOUNDARY_CANDIDATE_IDS = {
    "bender_relation_12463379": {
        "osm": "relation 12463379", "key": "bender",
        "brief": "current Bender OSM boundary (source-boundaries.geojson)"},
    "municipiul_bender_9581354": {
        "osm": "relation 9581354", "key": None,
        "brief": "Municipiul Bender / MD-BD (boundary-candidates.yml)"},
    "bender_city_council_944727": {
        "osm": "relation 944727", "key": None,
        "brief": "Bender City Council de-facto (boundary-candidates.yml)"},
}


def project(lon, lat):
    return ((lon - ORIGIN_LON) * MX, (lat - ORIGIN_LAT) * MY)


def _valid(geom):
    return geom if geom.is_valid else geom.buffer(0)


def outside_length_km(route_line: LineString, boundary_poly) -> float:
    """Km of a metric route lying OUTSIDE the metric city polygon (shapely
    difference). Handles multiple crossings, fully inside (0)/outside, edge-touch
    (0), multipolygon and holes; invalid polygon repaired via buffer(0)."""
    return route_line.difference(_valid(boundary_poly)).length / 1000.0


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _polyline_length_km(coords):
    pts = [project(x, y) for x, y in coords]
    return sum(math.hypot(b[0] - a[0], b[1] - a[1])
               for a, b in zip(pts, pts[1:], strict=False)) / 1000.0


# ----------------------- route inventory -----------------------

def collect_route_entries(external_uids):
    entries = []          # {uid, coords, length_km, source, origin, distance_km}
    per_source = {}
    for rel, kind, _purpose in ROUTE_SOURCES:
        data = json.loads((ROOT / rel).read_text(encoding="utf-8"))
        found = 0
        for f in data["features"]:
            p = f["properties"]
            uid = p.get("uid")
            if (p.get("kind") == kind and uid in external_uids
                    and f["geometry"]["type"] == "LineString"
                    and p.get("origin", "central") == "central"):
                coords = f["geometry"]["coordinates"]
                entries.append({
                    "uid": uid, "coords": coords,
                    "length_km": _polyline_length_km(coords),
                    "source": rel, "origin": p.get("origin", "central"),
                    "distance_km": p.get("distance_km")})
                found += 1
        per_source[rel] = {"features": len(data["features"]),
                           "external_central_routes": found,
                           "sha256": _sha(ROOT / rel), "kind": kind}
    return entries, per_source


def build_inventory(external, reg):
    external_uids = {r["uid"] for r in external}
    entries, per_source = collect_route_entries(external_uids)
    by_uid = {}
    for e in entries:
        by_uid.setdefault(e["uid"], []).append(e)

    inventory, conflicts = {}, []
    for uid, es in by_uid.items():
        km = reg[uid]["route_km"]
        if len(es) == 1:
            chosen, status = es[0], "UNIQUE"
        else:
            lengths = [e["length_km"] for e in es]
            spread = max(lengths) - min(lengths)
            tol = max(CONFLICT_TOL_KM, CONFLICT_TOL_FRAC * km)
            if spread <= tol:
                chosen = min(es, key=lambda e: abs(e["length_km"] - km))
                status = "DEDUPED_CONSISTENT"
            else:
                conflicts.append(uid)
                inventory[uid] = {"status": "ROUTE_GEOMETRY_CONFLICT",
                                  "sources": [e["source"] for e in es]}
                continue
        inventory[uid] = {
            "status": status, "coords": chosen["coords"],
            "length_km": chosen["length_km"], "source": chosen["source"],
            "route_km": km, "n_candidates": len(es)}
    return inventory, per_source, conflicts, len(entries)


# ----------------------- city boundary -----------------------

def load_bender_boundary():
    data = json.loads(BOUNDARIES.read_text(encoding="utf-8"))
    feature = next((f for f in data["features"]
                    if f["properties"].get("key") == "bender"), None)
    if feature is None:
        return None, None
    geom = shape(feature["geometry"])
    return _project_geom(geom), feature["properties"]


def _project_geom(geom):
    def ring(c):
        return [project(x, y) for x, y in c]
    if geom.geom_type == "Polygon":
        return Polygon(ring(geom.exterior.coords), [ring(h.coords) for h in geom.interiors])
    if geom.geom_type == "MultiPolygon":
        return MultiPolygon([Polygon(ring(p.exterior.coords),
                                     [ring(h.coords) for h in p.interiors])
                             for p in geom.geoms])
    raise ValueError(geom.geom_type)


EXTRACTION_PROV = ROOT / "data/interim/osm-boundaries/boundary-extraction-provenance.json"


def _extraction_by_relation():
    """Real extracted-geometry provenance for all three relations (produced by
    scripts/extract_osm_boundaries.py). Empty dict if the extraction hasn't run."""
    if not EXTRACTION_PROV.exists():
        return {}
    data = json.loads(EXTRACTION_PROV.read_text(encoding="utf-8"))
    return {r["relation_id"]: r for r in data.get("relations", [])}


def boundary_comparison(bprops, boundary_geom):
    """Compare the three candidate tariff boundaries. As of the boundary-extraction
    stage (commit 6d4679c) the FULL geometry of ALL THREE relations has been extracted
    from OSM (Overpass, ODbL) and stored under data/interim/osm-boundaries/ — the
    earlier 'no geometry in repo' blocker for 9581354 / 944727 is LIFTED. NONE is
    proven to be the approved operational tariff boundary; the unified suitability
    comparison lives in boundary-candidates-comparison-v2.csv."""
    provisional_note = ""
    try:
        rc = json.loads(RECOMPUTE_SUMMARY.read_text(encoding="utf-8"))
        provisional_note = str(rc.get("provenance", {}).get("switch_point", ""))
    except Exception:  # noqa: BLE001
        provisional_note = ""
    prov = _extraction_by_relation()
    rows = []
    for cid, meta in BOUNDARY_CANDIDATE_IDS.items():
        rid = "".join(ch for ch in meta["osm"] if ch.isdigit())
        p = prov.get(rid, {})
        is_repo = meta["key"] == "bender"
        status = ("PROVISIONAL_PROXY" if is_repo
                  else "EXTRACTED_ADMIN_BOUNDARY_UNVERIFIED")
        evidence = (
            f"repo stage-09-recompute-summary.json: {provisional_note!r}; geometry "
            "also extracted from OSM (see provenance)" if is_repo
            else "brief candidate; geometry extracted from OSM at commit 6d4679c — "
                 "administrative boundary, NOT auto-approved for tariff")
        rows.append({
            "candidate_id": cid, "osm": meta["osm"], "brief": meta["brief"],
            "geometry_extracted": "yes" if p else "no",
            "geometry_in_repo": "yes" if is_repo else "no",
            "raw_source_path": p.get("raw_artifact_path", ""),
            "geometry_path": p.get("geometry_artifact_path", ""),
            "source_file": ("docs/data/source-boundaries.geojson" if is_repo
                            else p.get("geometry_artifact_path", "")),
            "raw_sha256": p.get("raw_sha256", ""),
            "geometry_sha256": p.get("geometry_sha256", ""),
            "sha256": _sha(BOUNDARIES) if is_repo else p.get("geometry_sha256", ""),
            "input_crs": p.get("source_crs", "EPSG:4326"),
            "working_projection": "local equirectangular at origin (<0.1% length error)",
            "geometry_type": p.get("geometry_type", ""),
            "valid": p.get("valid_after_repair", ""),
            "area_km2": p.get("area_km2", bprops.get("area_km2") if is_repo else ""),
            "polygon_parts": p.get("polygon_parts", ""), "holes": p.get("holes", ""),
            "admin_level": p.get("admin_level", ""),
            "extraction_source": p.get("extraction_source", ""),
            "source_object_timestamp": p.get("source_object_timestamp", ""),
            "original_retrieval_timestamp_utc": p.get(
                "original_retrieval_timestamp_utc", ""),
            "note": p.get("name", meta["brief"]),
            "verification_status": status, "verification_evidence": evidence,
        })
    verified = [r for r in rows if r["verification_status"] == "VERIFIED_FOR_TARIFF"]
    return rows, (verified[0]["candidate_id"] if verified else None), provisional_note


# ----------------------- main -----------------------

CSV_HEADER = [
    "canonical_address_id", "address", "territory", "latitude", "longitude",
    "route_km", "route_geometry_source", "polyline_length_km",
    "route_length_difference_km", "route_length_difference_m",
    "route_length_difference_percent", "route_validation_status", "boundary_source",
    "boundary_verification_status", "outside_city_km", "base_city_fee",
    "external_surcharge", "final_fee", "calculation_status", "status_reason",
    "geographic_zone_analytics_only"]


def _validate_length(length, km):
    diff = abs(length - km)
    tol = max(LENGTH_TOL_KM, LENGTH_TOL_FRAC * km)
    return diff, ("LENGTH_OK" if diff <= tol else "LENGTH_MISMATCH")


def main():
    reg = {r["uid"]: r for r in ZE.ZM.load_addresses()}
    external = [r for r in reg.values() if r["settlement"] in EXTERNAL_SETTLEMENTS]
    inventory, per_source, conflicts, total_entries = build_inventory(external, reg)
    boundary_geom, bprops = load_bender_boundary()
    bcompare, verified_boundary, provisional_note = boundary_comparison(bprops, boundary_geom)
    boundary_verified = verified_boundary is not None

    # main production-readiness CSV: NO approved final_fee (boundary unverified)
    rows, inv_rows, scenario_rows = [], [], []
    for a in sorted(external, key=lambda r: r["uid"]):
        uid, km = a["uid"], a["route_km"]
        base = OT.base_city_fee(km)
        row = {c: "" for c in CSV_HEADER}
        row.update({
            "canonical_address_id": uid, "address": f'{a["street"]} {a["house"]}',
            "territory": a["settlement"], "latitude": ZE.ZM._round(a["lat"], 6),
            "longitude": ZE.ZM._round(a["lon"], 6), "route_km": ZE.ZM._round(km),
            "base_city_fee": base, "geographic_zone_analytics_only": a["zone_id"]})
        inv = inventory.get(uid)
        if inv is None:
            row["calculation_status"] = "ROUTE_GEOMETRY_UNAVAILABLE"
            row["status_reason"] = "no central-origin route polyline in repo"
        elif inv["status"] == "ROUTE_GEOMETRY_CONFLICT":
            row["calculation_status"] = "ROUTE_GEOMETRY_CONFLICT"
            row["status_reason"] = f"disagreeing polylines: {inv['sources']}"
        else:
            length = inv["length_km"]
            diff, vstatus = _validate_length(length, km)
            row["route_geometry_source"] = inv["source"]
            row["polyline_length_km"] = ZE.ZM._round(length, 4)
            row["route_length_difference_km"] = ZE.ZM._round(diff, 4)
            row["route_length_difference_m"] = ZE.ZM._round(diff * 1000, 1)
            row["route_length_difference_percent"] = ZE.ZM._round(100 * diff / km, 3)
            row["route_validation_status"] = vstatus
            row["boundary_source"] = "bender_relation_12463379 (PROVISIONAL_PROXY)"
            row["boundary_verification_status"] = (
                "VERIFIED_FOR_TARIFF" if boundary_verified else "PROVISIONAL_UNVERIFIED")
            if vstatus != "LENGTH_OK":
                row["calculation_status"] = "ROUTE_LENGTH_MISMATCH"
                row["status_reason"] = f"len {length:.3f} vs route_km {km:.3f}"
            elif not boundary_verified:
                # route ok, but no approved tariff boundary → no price
                row["calculation_status"] = "CITY_BOUNDARY_UNAVAILABLE"
                row["status_reason"] = (
                    "route geometry OK, but no VERIFIED_FOR_TARIFF city boundary "
                    "(12463379 is a provisional proxy); see scenario CSV")
                # SCENARIO computation under the provisional boundary (non-production)
                if boundary_geom is not None:
                    line = LineString([project(x, y) for x, y in inv["coords"]])
                    outside = max(0.0, min(outside_length_km(line, boundary_geom),
                                           length + 0.01))
                    surcharge = OT.external_surcharge(outside)
                    scenario_rows.append({
                        "canonical_address_id": uid, "territory": a["settlement"],
                        "route_km": ZE.ZM._round(km),
                        "boundary_candidate": "bender_relation_12463379",
                        "boundary_verification_status": "PROVISIONAL_PROXY",
                        "scenario_outside_city_km": ZE.ZM._round(outside, 4),
                        "scenario_base_city_fee": base,
                        "scenario_external_surcharge": surcharge,
                        "scenario_final_fee": base + surcharge,
                        "note": "SCENARIO ONLY — not an approved price; boundary unverified"})
            else:
                row["calculation_status"] = "CALCULATED"  # only if a boundary is verified
        rows.append(row)
        if inv is not None and inv["status"] != "ROUTE_GEOMETRY_CONFLICT":
            inv_rows.append({"canonical_address_id": uid, "territory": a["settlement"],
                             "source": inv["source"], "dedup_status": inv["status"],
                             "n_candidates": inv["n_candidates"],
                             "polyline_length_km": ZE.ZM._round(inv["length_km"], 4),
                             "route_km": ZE.ZM._round(km)})

    _write(OUT_CSV, CSV_HEADER, rows)
    _write(INVENTORY_CSV, ["canonical_address_id", "territory", "source",
                           "dedup_status", "n_candidates", "polyline_length_km",
                           "route_km"], inv_rows)
    if scenario_rows:
        _write(SCENARIO_CSV, list(scenario_rows[0].keys()), scenario_rows)
    else:
        _write(SCENARIO_CSV, ["canonical_address_id", "note"], [])

    sensitivity = _sensitivity(inventory, reg)
    severny = investigate_severny(list(reg.values()))
    summary = _summary(external, inventory, per_source, conflicts, total_entries,
                       bcompare, boundary_verified, provisional_note, sensitivity,
                       severny, rows, scenario_rows)
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8", newline="\n")
    controls = _controls(rows, inv_rows)
    _write(CONTROLS_CSV, CSV_HEADER, controls)
    _write_md(summary, controls, bcompare)
    print(json.dumps({"verdict": summary["verdict"],
                      "usable_routes": summary["unique_usable_routes"],
                      "approved_priced": summary["approved_priced_addresses"]},
                     ensure_ascii=False))


def _write(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=header, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def _sensitivity(inventory, reg):
    usable = [(uid, inv) for uid, inv in inventory.items()
              if inv["status"] in ("UNIQUE", "DEDUPED_CONSISTENT")]
    out = []
    for thr in SENSITIVITY_THRESHOLDS_KM:
        accepted = sum(1 for uid, inv in usable
                       if abs(inv["length_km"] - reg[uid]["route_km"]) <= thr)
        out.append({"threshold_km": thr, "accepted_routes": accepted,
                    "total_routes": len(usable)})
    # every route matches to < 5 m, so all thresholds >= 0.005 accept all → no
    # address changes acceptance; price is blocked regardless of threshold.
    changes = len({o["accepted_routes"] for o in out}) > 1
    return {"by_threshold": out, "acceptance_changes_across_thresholds": changes,
            "price_impact": "none (boundary unverified → no approved price at any threshold)"}


def investigate_severny(all_rows):
    present = sorted({r["settlement"] for r in all_rows if r["settlement"] in SEVERNY_ALIASES})
    ext_count = 0
    if SEVERNY_FILE.exists():
        with SEVERNY_FILE.open(encoding="utf-8-sig", newline="") as h:
            ext_count = sum(1 for _ in csv.DictReader(h))
    return {
        "in_canonical_9216": bool(present), "matched_aliases": present,
        "aliases_checked": list(SEVERNY_ALIASES),
        "canonical_settlements_scanned": sorted({r["settlement"] for r in all_rows}),
        "separate_source_file": "docs/data/severny-delivery-units.csv",
        "separate_source_addresses": ext_count,
        "status": "TERRITORY_DATA_UNAVAILABLE",
        "how_to_obtain": ("Северный addresses exist only in the non-canonical "
                          "severny-delivery-units.csv; a future analysis-only step could "
                          "map them to OSM/verified coordinates and route them, but "
                          "promoting them into the canonical release is a production step "
                          "and is out of scope."),
    }


def _stats(vals):
    vals = sorted(v for v in vals if v != "")
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "min": vals[0], "median": ZE._pct(vals, 0.5), "max": vals[-1]}


def _summary(external, inventory, per_source, conflicts, total_entries, bcompare,
             boundary_verified, provisional_note, sensitivity, severny, rows,
             scenario_rows):
    usable = [u for u, inv in inventory.items()
              if inv["status"] in ("UNIQUE", "DEDUPED_CONSISTENT")]
    status_counts = {}
    for r in rows:
        status_counts[r["calculation_status"]] = status_counts.get(
            r["calculation_status"], 0) + 1
    per_territory = {}
    for terr in EXTERNAL_SETTLEMENTS:
        tr = [r for r in rows if r["territory"] == terr]
        with_geom = [r for r in tr if r["polyline_length_km"] != ""]
        per_territory[terr] = {
            "total_addresses": len(tr),
            "route_geometries_found": len(with_geom),
            "unique_valid_routes": sum(
                1 for r in with_geom if r["route_validation_status"] == "LENGTH_OK"),
            "geometry_verified_routes": len(with_geom),
            "approved_priced_addresses": sum(1 for r in tr
                                             if r["calculation_status"] == "CALCULATED"),
            "unavailable_addresses": sum(1 for r in tr
                                         if r["calculation_status"] != "CALCULATED"),
            "route_km_stats": _stats([float(r["route_km"]) for r in tr]),
            "verified_outside_city_km_stats": {"n": 0, "reason": "boundary unverified"},
            "verified_final_fee_stats": {"n": 0, "reason": "boundary unverified"},
        }
    return {
        "verdict": "BLOCKED_BY_CITY_BOUNDARY" if not boundary_verified
        else "OUTSIDE_TARIFF_ANALYSIS_COMPLETE",
        "reason": ("No VERIFIED_FOR_TARIFF city boundary yet: the Bender OSM boundary "
                   "(relation 12463379) is a provisional proxy per the repo. The full "
                   "geometry of ALL THREE candidate relations (12463379, 9581354, "
                   "944727) has now been EXTRACTED from OSM (see "
                   "data/interim/osm-boundaries/ and boundary-candidates-comparison-"
                   "v2.csv); the earlier 'no geometry in repo' blocker for 9581354 / "
                   "944727 is lifted. None is approved as the operational tariff "
                   "boundary, so the 12 external routes still cannot be priced without "
                   "an owner boundary decision."),
        "provisional_boundary_evidence": provisional_note,
        "route_sources": per_source,
        "route_source_entries_total": total_entries,
        "unique_usable_routes": len(usable),
        "route_conflicts": conflicts,
        "external_addresses_total": len(external),
        "approved_priced_addresses": status_counts.get("CALCULATED", 0),
        "status_counts": status_counts,
        "boundary_candidates": bcompare,
        "verified_tariff_boundary": None,
        "sensitivity": sensitivity,
        "scenario_rows_provisional": len(scenario_rows),
        "per_territory": per_territory,
        "severny": severny,
        "note": ("Analysis/test layer only; production, Direct, releases, routing "
                 "graph, canonical addresses, driver cabinet, driver zone switch, "
                 "operational dispatch zones and live tariffs untouched."),
    }


def _controls(rows, inv_rows):
    with_geom = [r for r in rows if r["polyline_length_km"] != ""]
    with_geom.sort(key=lambda r: float(r["route_km"]))
    picks = list(with_geom)  # all 12 real routed addresses
    for terr in EXTERNAL_SETTLEMENTS:
        tr = [r for r in rows if r["territory"] == terr
              and r["calculation_status"] == "ROUTE_GEOMETRY_UNAVAILABLE"]
        tr.sort(key=lambda r: float(r["route_km"]))
        picks += tr[:3] + tr[-3:]
    seen, out = set(), []
    for r in picks:
        if r["canonical_address_id"] not in seen:
            seen.add(r["canonical_address_id"])
            out.append(r)
    return out


SYNTHETIC_FIXTURES = [
    "fully_inside", "fully_outside", "single_crossing", "multiple_crossings",
    "touching_boundary", "multipolygon", "hole", "invalid_route", "invalid_boundary",
    "missing_geometry"]


def _write_md(summary, controls, bcompare):
    lines = [
        "# Outside-city route & city-boundary audit v1", "",
        f"**Verdict: {summary['verdict']}**", "",
        summary["reason"], "",
        f"Repo evidence the boundary is provisional: "
        f"`{summary['provisional_boundary_evidence']}`", "",
        "Analysis/test layer only; production, Direct, releases, routing graph,",
        "canonical addresses, driver cabinet, the driver zone switch, operational",
        "dispatch zones, GitHub Pages and live tariffs are untouched.", "",
        "## Route inventory", "",
        "| Source | features | external central routes | sha256 |",
        "|---|---:|---:|---|"]
    for src, s in summary["route_sources"].items():
        lines.append(f"| {src} | {s['features']} | {s['external_central_routes']} | "
                     f"{s['sha256'][:12]}… |")
    lines += ["",
              f"- Unique usable external routes (deduped): **{summary['unique_usable_routes']}**",
              f"- Route conflicts: {summary['route_conflicts'] or 'none'}", "",
              "## Route-length sensitivity", "",
              "| Threshold km | Accepted | Total |", "|---:|---:|---:|"]
    for o in summary["sensitivity"]["by_threshold"]:
        lines.append(f"| {o['threshold_km']} | {o['accepted_routes']} | {o['total_routes']} |")
    lines += ["",
              f"Acceptance changes across thresholds: "
              f"**{summary['sensitivity']['acceptance_changes_across_thresholds']}**; "
              f"price impact: {summary['sensitivity']['price_impact']}.", "",
              "## City-boundary candidates (all three geometries extracted)", "",
              "All three relation geometries have been extracted from OSM (Overpass, "
              "ODbL) at commit 6d4679c and stored under data/interim/osm-boundaries/. "
              "Unified suitability comparison: boundary-candidates-comparison-v2.csv.",
              "",
              "| relation | admin_level | geometry extracted | verification | area km² "
              "| geometry path | geom sha256 | name |",
              "|---|---|---|---|---:|---|---|---|"]
    for c in bcompare:
        lines.append(
            f"| {c['osm']} | {c['admin_level']} | {c['geometry_extracted']} | "
            f"**{c['verification_status']}** | {c['area_km2']} | "
            f"`{c['geometry_path']}` | {(c['geometry_sha256'] or '')[:12]}… | "
            f"{c['note']} |")
    lines += ["",
              "Provenance per relation: raw_source_path, geometry_path, raw_sha256, "
              "geometry_sha256, source_object_timestamp and "
              "original_retrieval_timestamp_utc are recorded in "
              "`data/interim/osm-boundaries/boundary-extraction-provenance.json`. The "
              "'no geometry in repo' blocker (relations 9581354 / 944727) was lifted "
              "at the boundary-extraction stage (commit 6d4679c).", "",
              "**Critical rule:** an OSM administrative boundary is NOT automatically "
              "the approved operational tariff boundary. None of the candidates has "
              "reproducible proof of being the tariff switch boundary, so none is "
              "VERIFIED_FOR_TARIFF and no address gets an approved final_fee.", "",
              "## Coverage per external territory", "",
              "| Territory | Total | Routes found | Valid routes | Approved-priced | Unavailable |",
              "|---|---:|---:|---:|---:|---:|"]
    for terr, t in summary["per_territory"].items():
        lines.append(f"| {terr} | {t['total_addresses']} | {t['route_geometries_found']} | "
                     f"{t['unique_valid_routes']} | {t['approved_priced_addresses']} | "
                     f"{t['unavailable_addresses']} |")
    lines += ["", "### Status counts", ""]
    for s, n in sorted(summary["status_counts"].items()):
        lines.append(f"- {s}: {n}")
    sv = summary["severny"]
    lines += ["", "## Северный", "",
              f"- In canonical 9,216: **{sv['in_canonical_9216']}** "
              f"(aliases checked: {', '.join(sv['aliases_checked'])}; "
              f"settlements scanned: {', '.join(sv['canonical_settlements_scanned'])})",
              f"- Non-canonical source: {sv['separate_source_addresses']} rows in "
              f"`{sv['separate_source_file']}`", f"- {sv['how_to_obtain']}", "",
              "## Scenario analytics (NON-PRODUCTION)", "",
              f"Under the PROVISIONAL boundary 12463379, `outside_city_km` and would-be "
              f"fees are computed for the {summary['scenario_rows_provisional']} routed "
              "addresses ONLY as scenario analytics in "
              "`data/interim/outside-city-boundary-scenarios-v1.csv`. These are NOT "
              "approved prices and are kept separate from the production-readiness CSV "
              "(whose final_fee is empty for every external address).", "",
              "## Control addresses", "",
              "### A. Real canonical routes",
              "| id | territory | route_km | polyline_km | Δm | route_val | status |",
              "|---|---|---:|---:|---:|---|---|"]
    for r in controls:
        lines.append(f"| {r['canonical_address_id']} | {r['territory']} | {r['route_km']} | "
                     f"{r['polyline_length_km'] or '—'} | "
                     f"{r['route_length_difference_m'] or '—'} | "
                     f"{r['route_validation_status'] or '—'} | {r['calculation_status']} |")
    lines += ["", "### B. Synthetic geometry fixtures (unit tests, not real addresses)",
              "", ", ".join(SYNTHETIC_FIXTURES), "",
              "Verdict: BLOCKED_BY_CITY_BOUNDARY.", ""]
    OWNER_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
