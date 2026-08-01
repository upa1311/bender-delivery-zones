"""Unified boundary comparison + route scenarios across ALL THREE real OSM
boundary geometries — ANALYSIS ONLY.

Consumes the geometries extracted by scripts/extract_osm_boundaries.py and produces:
  * boundary-candidates-comparison-v2.csv  — one row per candidate, unified method
  * boundary-route-scenarios-v2.csv        — 12 real routes x each candidate (36 rows)
  * _boundary-scenarios-summary.json       — machine-readable roll-up for tests/map

No production final_fee is written; every scenario row is labelled SCENARIO and no
boundary is marked VERIFIED_FOR_TARIFF. Formulas are unchanged and imported from
owner_tariff_model (min-5 surcharge always applies to an external address).
"""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

from shapely.geometry import LineString, MultiPolygon, Point, Polygon, shape

ROOT = Path(__file__).resolve().parents[1]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


OC = _load("outside_city_distance", "scripts/outside_city_distance.py")
OT = OC.OT
ZE = OC.ZE

BND_DIR = ROOT / "data/interim/osm-boundaries"
PROV = json.loads((BND_DIR / "boundary-extraction-provenance.json").read_text(encoding="utf-8"))
SETTLEMENTS = ROOT / "docs/data/settlements.geojson"
FEES_CSV = ROOT / "data/interim/outside-city-distance-v1.csv"
COMPARE_CSV = ROOT / "data/interim/boundary-candidates-comparison-v2.csv"
SCEN_CSV = ROOT / "data/interim/boundary-route-scenarios-v2.csv"
SUMMARY = ROOT / "reports/zone-model-audit/_boundary-scenarios-summary.json"

CANDIDATES = ["12463379", "9581354", "944727"]
# Consistent per-relation semantics (single source of truth for every artifact):
# owner label, whether the ORIGINAL brief nominated it, whether it is in the
# analytical comparison, and its tariff-suitability verdict.
OWNER_LABEL = {"12463379": "A", "9581354": "B", "944727": "C"}
ORIGINAL_BRIEF_NOMINATED = {"12463379": False, "9581354": True, "944727": True}
COMPARISON_CANDIDATE = {"12463379": True, "9581354": True, "944727": True}
TARIFF_SUITABILITY = {rid: "CANDIDATE_UNVERIFIED" for rid in CANDIDATES}
ADMIN_MEANING = {
    "12463379": "admin_level 8 — Bender city proper. Not explicitly nominated in the "
                "original brief; discovered from the source inventory "
                "(source-boundaries.geojson) and included as analytical candidate A. "
                "Repo labels it a provisional proxy. Tariff suitability evaluated "
                "separately.",
    "9581354": "admin_level 4 — Municipiul Bender, de-jure municipality per Republic "
               "of Moldova law. Brief candidate (config/boundary-candidates.yml). "
               "Analytical candidate B.",
    "944727": "admin_level 5 — de-facto Bender city under PMR control (OSM name "
              "Tighina/Бендеры). Brief candidate (config/boundary-candidates.yml). "
              "Analytical candidate C. This is a factual administrative boundary, NOT "
              "a separate operational tariff boundary.",
}


def _project_geom(geom):
    """Project lon/lat to the SAME metric CRS outside_city_distance uses (fixed
    origin), so route ∩ boundary lengths are consistent with the v1 audit."""
    def ring(c):
        return [OC.project(x, y) for x, y in c]
    if geom.geom_type == "Polygon":
        return Polygon(ring(geom.exterior.coords),
                       [ring(h.coords) for h in geom.interiors])
    return MultiPolygon([Polygon(ring(p.exterior.coords),
                                 [ring(h.coords) for h in p.interiors])
                         for p in geom.geoms])


def load_boundaries():
    out = {}
    for rid in CANDIDATES:
        g = shape(json.loads((BND_DIR / f"relation-{rid}.geojson").read_text(
            encoding="utf-8"))["geometry"])
        out[rid] = {"lonlat": g, "metric": _project_geom(g)}
    return out


def _crossing_stats(route_line, boundary_metric):
    """Return (outside_km, n_crossings, touching, exits, reentries) for a metric
    route vs a metric boundary polygon."""
    bnd = boundary_metric if boundary_metric.is_valid else boundary_metric.buffer(0)
    outside_km = route_line.difference(bnd).length / 1000.0
    boundary_line = bnd.boundary
    inter = route_line.intersection(boundary_line)
    if inter.is_empty:
        n_cross = 0
    elif inter.geom_type == "Point":
        n_cross = 1
    elif inter.geom_type == "MultiPoint":
        n_cross = len(inter.geoms)
    else:  # line overlap => route runs along the boundary
        n_cross = 0
    touching = route_line.touches(bnd)
    # exits/re-entries: walk the vertices, count inside->outside transitions
    coords = list(route_line.coords)
    states = [bnd.contains(Point(*c)) for c in coords]
    exits = sum(1 for a, b in zip(states, states[1:], strict=False) if a and not b)
    reentries = sum(1 for a, b in zip(states, states[1:], strict=False) if not a and b)
    return outside_km, n_cross, touching, exits, reentries


def build_scenarios(boundaries, inventory, reg):
    rows = []
    for uid, inv in inventory.items():
        if "coords" not in inv:
            continue
        route_line = LineString([OC.project(x, y) for x, y in inv["coords"]])
        rec = reg[uid]
        dest_lonlat = Point(*inv["coords"][-1])
        route_km = rec["route_km"]
        base = OT.base_city_fee(route_km)
        address = ", ".join(str(rec[k]) for k in ("settlement", "street", "house")
                            if rec.get(k))
        for rid in CANDIDATES:
            b = boundaries[rid]
            dest_inside = b["lonlat"].contains(dest_lonlat)
            outside_km, n_cross, touching, exits, reentries = _crossing_stats(
                route_line, b["metric"])
            if dest_inside:
                # destination is a CITY address under this boundary -> city fee only
                surcharge = 0
                final = base
                classification = "inside_city"
            else:
                surcharge = OT.external_surcharge(outside_km)  # min-5 always
                final = base + surcharge
                classification = "outside_city"
            # Second, independent reading: TERRITORY-LABEL rule. The approved tariff
            # treats Парканы/Гиска/Протягайловка as external territories, so the min-5
            # surcharge applies by LABEL even when the destination is geometrically
            # inside the polygon. Where the two readings disagree it is a genuine
            # owner decision (label vs geometry), not something Claude resolves.
            label_external = rec["settlement"] in OC.EXTERNAL_SETTLEMENTS
            terr_surcharge = OT.external_surcharge(outside_km) if label_external else 0
            terr_final = base + terr_surcharge
            conflict = bool(label_external and dest_inside)
            rows.append({
                "canonical_address_id": uid, "route_id": f"route_{uid}",
                "address": address,
                "territory": rec["settlement"], "route_source": inv.get("source", ""),
                "canonical_route_km": route_km,
                "polyline_length_km": round(inv["length_km"], 4),
                "boundary_id": rid, "boundary_admin_level":
                    PROV_BY_ID[rid]["admin_level"],
                "boundary_suitability": "ADMIN_BOUNDARY_CANDIDATE_UNVERIFIED",
                "destination_classification": classification,
                "outside_city_km": round(outside_km, 4),
                "n_crossings": n_cross, "touching_boundary": touching,
                "exits": exits, "reentries": reentries,
                "geometric_base_city_fee": base,
                "geometric_external_surcharge": surcharge,
                "geometric_final_fee": final,
                "territory_label_external": label_external,
                "territory_rule_surcharge": terr_surcharge,
                "territory_rule_final_fee": terr_final,
                "label_geometry_conflict": conflict,
                "note": "SCENARIO ONLY — boundary unverified, not an approved price. "
                        "geometric_* = classify by polygon containment; "
                        "territory_rule_* = external-label min-5 rule (v1)",
            })
    # difference versus the other candidates: min/max geometric final per address
    by_addr = {}
    for r in rows:
        by_addr.setdefault(r["canonical_address_id"], []).append(r)
    for group in by_addr.values():
        finals = [r["geometric_final_fee"] for r in group]
        lo, hi = min(finals), max(finals)
        for r in group:
            r["geometric_final_fee_min_across_candidates"] = lo
            r["geometric_final_fee_max_across_candidates"] = hi
            r["fee_diff_vs_cheapest_candidate"] = r["geometric_final_fee"] - lo
            r["price_changes_across_candidates"] = lo != hi
    return rows


PROV_BY_ID = {r["relation_id"]: r for r in PROV["relations"]}


def settlement_membership(boundaries):
    data = json.loads(SETTLEMENTS.read_text(encoding="utf-8"))
    out = {}
    for f in data["features"]:
        key = f["properties"].get("key")
        if key not in ("parkany", "giska", "protyagailovka", "bender"):
            continue
        c = shape(f["geometry"]).centroid
        out[key] = {rid: bool(boundaries[rid]["lonlat"].contains(c))
                    for rid in CANDIDATES}
    return out


def point_counts(boundaries):
    rows = list(csv.DictReader(FEES_CSV.open(encoding="utf-8-sig")))
    pts = [(float(r["longitude"]), float(r["latitude"]), r["territory"])
           for r in rows if r["latitude"]]
    out = {}
    for rid in CANDIDATES:
        b = boundaries[rid]["lonlat"]
        inside = {}
        n_in = 0
        for x, y, t in pts:
            if b.contains(Point(x, y)):
                n_in += 1
                inside[t] = inside.get(t, 0) + 1
        out[rid] = {"inside_total": n_in, "outside_total": len(pts) - n_in,
                    "inside_by_territory": inside}
    return out, len(pts)


def write_comparison(boundaries, membership, counts):
    rows = []
    for rid in CANDIDATES:
        p = PROV_BY_ID[rid]
        m = membership
        rows.append({
            "candidate_id": f"osm_relation_{rid}", "relation_id": rid,
            "owner_label": OWNER_LABEL[rid],
            "original_brief_nominated": ORIGINAL_BRIEF_NOMINATED[rid],
            "comparison_candidate": COMPARISON_CANDIDATE[rid],
            "tariff_suitability": TARIFF_SUITABILITY[rid],
            "osm_url": p["osm_url"], "name": p["name"], "name_ru": p.get("name_ru"),
            "admin_level": p["admin_level"], "administrative_meaning": ADMIN_MEANING[rid],
            "provenance": p["extraction_source"], "license": p["license"],
            "version": p["version"],
            "source_object_timestamp": p["source_object_timestamp"],
            "original_retrieval_timestamp_utc": p["original_retrieval_timestamp_utc"],
            "geometry_type": p["geometry_type"], "area_km2": p["area_km2"],
            "polygon_parts": p["polygon_parts"], "holes": p["holes"],
            "valid_before_repair": p["valid_before_repair"],
            "valid_after_repair": p["valid_after_repair"],
            "raw_sha256": p["raw_sha256"], "geometry_sha256": p["geometry_sha256"],
            "parkany_inside": m["parkany"][rid], "giska_inside": m["giska"][rid],
            "protyagailovka_inside": m["protyagailovka"][rid],
            "bender_inside": m["bender"][rid],
            "severny_inside": "N/A — no canonical Северный address geometry "
                              "(see severny report)",
            "external_points_inside": counts[rid]["inside_total"],
            "external_points_outside": counts[rid]["outside_total"],
            "inside_by_territory": json.dumps(counts[rid]["inside_by_territory"],
                                              ensure_ascii=False),
            "suitability_as_tariff_start": "CANDIDATE — plausible city definition; "
            "surcharge would begin at this line",
            "verification_status": "DRAFT_UNAPPROVED — administrative boundary is NOT "
            "automatically an operational tariff boundary; owner decision required",
            "reason": _reason(rid, m, counts),
        })
    header = list(rows[0].keys())
    with COMPARE_CSV.open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=header, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return rows


def _reason(rid, m, counts):
    ins = counts[rid]["inside_by_territory"]
    if rid == "12463379":
        return ("Smallest extent (city proper). Парканы/Гиска/Протягайловка mostly "
                f"OUTSIDE (only {counts[rid]['inside_total']} fringe points inside: "
                f"{ins}). Not nominated in the original brief (discovered from the "
                "source inventory, included as analytical candidate A); repo labelled "
                "it provisional.")
    if rid == "9581354":
        return ("De-jure municipality. Протягайловка falls INSIDE "
                f"({ins.get('Протягайловка', 0)} pts); Гиска mostly outside; Парканы "
                "outside. Choosing this makes Протягайловка a city address.")
    return ("De-facto PMR city (largest). BOTH Протягайловка and most of Гиска INSIDE "
            f"({ins}); only Парканы outside. Widest 'city', fewest external addresses.")


def main():
    boundaries = load_boundaries()
    reg = {r["uid"]: r for r in ZE.ZM.load_addresses()}
    external = [r for r in reg.values() if r["settlement"] in OC.EXTERNAL_SETTLEMENTS]
    inventory, _ps, _cf, _te = OC.build_inventory(external, reg)
    membership = settlement_membership(boundaries)
    counts, n_pts = point_counts(boundaries)
    compare = write_comparison(boundaries, membership, counts)
    scen = build_scenarios(boundaries, inventory, reg)
    header = list(scen[0].keys())
    with SCEN_CSV.open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=header, lineterminator="\n")
        w.writeheader()
        w.writerows(scen)
    # price/classification changes across boundaries, per address
    by_addr = {}
    for r in scen:
        by_addr.setdefault(r["canonical_address_id"], {})[r["boundary_id"]] = r
    changes = []
    for uid, per in by_addr.items():
        finals = {rid: per[rid]["geometric_final_fee"] for rid in per}
        classes = {rid: per[rid]["destination_classification"] for rid in per}
        if len(set(finals.values())) > 1 or len(set(classes.values())) > 1:
            changes.append({"canonical_address_id": uid,
                            "territory": next(iter(per.values()))["territory"],
                            "geometric_finals": finals, "classifications": classes})
    conflicts = [{"canonical_address_id": r["canonical_address_id"],
                  "territory": r["territory"], "boundary_id": r["boundary_id"],
                  "geometric_final_fee": r["geometric_final_fee"],
                  "territory_rule_final_fee": r["territory_rule_final_fee"]}
                 for r in scen if r["label_geometry_conflict"]]
    summary = {
        "generated_by": "scripts/boundary_scenarios.py",
        "candidates": CANDIDATES, "external_points_total": n_pts,
        "settlement_membership": membership, "point_counts": counts,
        "n_routes": len({r["canonical_address_id"] for r in scen}),
        "n_scenario_rows": len(scen),
        "price_or_class_changing_addresses": changes,
        "label_geometry_conflicts": conflicts,
        "giska_inside_12463379_points": counts["12463379"]["inside_by_territory"]
        .get("Гиска", 0),
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                       encoding="utf-8", newline="\n")
    print(json.dumps({"candidates": len(compare), "routes": summary["n_routes"],
                      "scenario_rows": len(scen), "changing": len(changes),
                      "conflicts": len(conflicts), "points": n_pts},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
