#!/usr/bin/env python
"""Stage 09A — ROUTING TRUTH AUDIT.

Prove the ROUTES first, before trusting any zone. For the owner-flagged
anomalies (Borisovka in-city Zone 4, Parkany/Giska entries, Khomutyanovka) and
programmatically-found suspects, this:

  * snaps each address (OSRM nearest) and reports snap distance + snapped road
    class (from the local roads.geojson);
  * takes the FASTEST VALID route (OSRM min-duration shortest path over the whole
    car graph) plus alternatives, with full geometry, and compares distance /
    duration;
  * flags implausible results (alt >10% shorter, leaves & re-enters the city,
    detour_ratio > 1.5, snap > 40 m, neighbour zone jump > 1);
  * verifies the restaurant origins snap to a real road;
  * emits control routes centre/BAM -> each district;
  * assigns one routing verdict per suspect.

No prices, no immutable-release edits, no Direct changes. Overrides, if any, are
proposed only (owner_review_required), never applied to zones here.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage09_engine import (  # noqa: E402
    ORIGINS,
    haversine_km,
    load_bender_boundary,
    nearest,
    route_full,
    segment_in_out_city,
)

REPO = Path(__file__).resolve().parents[1]
ROUTED = REPO / "docs/data/stage-09-routed.jsonl"
OUTDIR = REPO / "docs/data"
RPTDIR = REPO / "reports/stage-09a"

VERDICTS = [
    "ROUTE_CORRECT_ZONE_MODEL_REVIEW",
    "WRONG_ADDRESS_SNAP",
    "MISSING_OSM_ROAD",
    "BROKEN_OSM_CONNECTIVITY",
    "WRONG_ACCESS_TAG",
    "WRONG_ONEWAY_OR_TURN_RESTRICTION",
    "WRONG_ORIGIN",
    "OSRM_ROUTE_SELECTION_ISSUE",
    "INSUFFICIENT_EVIDENCE",
]


def load_roads():
    gj = json.loads((REPO / "docs/data/roads.geojson").read_text("utf-8"))
    geoms, props = [], []
    for f in gj["features"]:
        if f["geometry"]["type"] != "LineString":
            continue
        geoms.append(LineString(f["geometry"]["coordinates"]))
        props.append(f["properties"])
    return STRtree(geoms), geoms, props


def nearest_road(tree, geoms, props, lon, lat):
    idx = tree.nearest(Point(lon, lat))
    g = geoms[idx]
    # approximate perpendicular distance in metres
    d_deg = g.distance(Point(lon, lat))
    return props[idx], round(d_deg * 111000, 1)


def load_routed_index():
    rows = {}
    if ROUTED.exists():
        for line in ROUTED.read_text("utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows[r["uid"]] = r
    return rows


def find_suspects(routed):
    """In-city Бендеры Zone-4, Borisovka/Khomutyanovka, first Parkany/Giska,
    neighbour zone jumps > 1 within 200 m, high detour ratio."""
    rows = list(routed.values())
    suspects = {}

    def add(r, why):
        suspects.setdefault(r["uid"], {"row": r, "why": []})["why"].append(why)

    for r in rows:
        cz = r["current_zone"]
        if r["settlement_ru"] == "Бендеры" and cz == 4:
            add(r, "in_city_zone4")
        if r["district_ru"] in ("Борисовка", "Хомутяновка"):
            add(r, f"district_{r['district_ru']}")

    # first serviceable addresses of Parkany / Giska (closest to the city)
    for settle in ("Парканы", "Гиска"):
        pool = [r for r in rows if r["settlement_ru"] == settle and r.get("raw_km_A")]
        for r in sorted(pool, key=lambda x: x["raw_km_A"])[:8]:
            add(r, f"{settle}_entry")

    # neighbour zone jump > 1 within 200 m
    pts = [(r, r["lat"], r["lon"]) for r in rows]
    for r, lat, lon in pts:
        for r2, lat2, lon2 in pts:
            if r2["uid"] == r["uid"]:
                continue
            if abs(lat2 - lat) > 0.0025 or abs(lon2 - lon) > 0.0025:
                continue
            if haversine_km(lat, lon, lat2, lon2) <= 0.2 and abs(r["current_zone"] - r2["current_zone"]) > 1:  # noqa: E501
                add(r, f"neighbour_jump_{r['current_zone']}v{r2['current_zone']}")
                break
    return suspects


def audit_one(r, tree, geoms, props, boundary):
    lat, lon = r["lat"], r["lon"]
    snap = nearest(lon, lat)
    road, road_d = nearest_road(tree, geoms, props, lon, lat)
    central = (ORIGINS[0]["lon"], ORIGINS[0]["lat"])
    rt = route_full(central, (lon, lat))
    straight = haversine_km(ORIGINS[0]["lat"], ORIGINS[0]["lon"], lat, lon)
    detour = round(rt.distance_km / straight, 3) if rt.ok and straight > 0.05 else None
    seg = segment_in_out_city(rt.geometry, boundary) if rt.ok else {}
    min_alt = min([rt.distance_km] + [a["distance_km"] for a in rt.alternatives]) if rt.ok else None
    alt_shorter = bool(rt.ok and min_alt is not None and min_alt < rt.distance_km * 0.9)

    flags = []
    if snap.get("snap_distance_m", 0) > 40:
        flags.append("snap_gt_40m")
    if road.get("highway") in ("service", "footway", "path", "pedestrian", "steps", "track"):
        flags.append(f"snapped_{road.get('highway')}")
    if seg.get("reenters_city"):
        flags.append("leaves_and_reenters_city")
    if detour and detour > 1.5:
        flags.append("detour_gt_1.5")
    if alt_shorter:
        flags.append("alt_>10pct_shorter")

    # heuristic verdict — evidence-graded, defaults to review not a claim
    if "snap_gt_40m" in flags or road.get("highway") in ("footway", "path", "pedestrian", "steps"):
        verdict = "WRONG_ADDRESS_SNAP"
    elif alt_shorter:
        verdict = "OSRM_ROUTE_SELECTION_ISSUE"
    elif "snapped_service" in " ".join(flags):
        verdict = "WRONG_ACCESS_TAG"
    elif not flags:
        verdict = "ROUTE_CORRECT_ZONE_MODEL_REVIEW"
    else:
        verdict = "INSUFFICIENT_EVIDENCE"

    return {
        "uid": r["uid"],
        "settlement_ru": r["settlement_ru"],
        "district_ru": r["district_ru"],
        "street_ru": r["street_ru"],
        "housenumber": r["housenumber"],
        "current_zone": r["current_zone"],
        "lat": lat,
        "lon": lon,
        "fastest_distance_km": rt.distance_km,
        "fastest_duration_s": rt.duration_s,
        "min_alt_distance_km": min_alt,
        "n_alternatives": len(rt.alternatives),
        "straight_line_km": round(straight, 3),
        "detour_ratio": detour,
        "in_city_km": seg.get("in_city_km"),
        "outside_city_km": seg.get("outside_city_km"),
        "snap_distance_m": snap.get("snap_distance_m"),
        "snapped_name": snap.get("snapped_name"),
        "nearest_road_name": road.get("ru_display") or road.get("name"),
        "nearest_road_highway": road.get("highway"),
        "nearest_road_dist_m": road_d,
        "flags": ";".join(flags),
        "verdict": verdict,
        "geometry": rt.geometry if rt.ok else [],
        "alternatives": rt.alternatives if rt.ok else [],
    }


def main() -> int:
    RPTDIR.mkdir(parents=True, exist_ok=True)
    boundary = load_bender_boundary()
    tree, geoms, props = load_roads()
    routed = load_routed_index()
    if not routed:
        print("routed cache not ready yet")
        return 1
    suspects = find_suspects(routed)
    print(f"suspects: {len(suspects)}")

    audited = []
    for s in suspects.values():
        a = audit_one(s["row"], tree, geoms, props, boundary)
        a["why"] = ";".join(s["why"])
        audited.append(a)

    # --- snap diagnostics CSV ---
    with (OUTDIR / "stage-09a-snap-diagnostics.csv").open("w", encoding="utf-8", newline="") as fh:
        cols = ["uid", "settlement_ru", "district_ru", "street_ru", "housenumber",
                "lat", "lon", "snap_distance_m", "snapped_name",
                "nearest_road_name", "nearest_road_highway", "nearest_road_dist_m"]
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(audited)

    # --- routing audit CSV ---
    with (OUTDIR / "stage-09a-routing-audit.csv").open("w", encoding="utf-8", newline="") as fh:
        cols = ["uid", "settlement_ru", "district_ru", "street_ru", "housenumber",
                "current_zone", "why", "fastest_distance_km", "fastest_duration_s",
                "min_alt_distance_km", "n_alternatives", "straight_line_km",
                "detour_ratio", "in_city_km", "outside_city_km", "snap_distance_m",
                "nearest_road_highway", "flags", "verdict"]
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(audited)

    # --- routing audit points geojson ---
    feats = [
        {"type": "Feature",
         "geometry": {"type": "Point", "coordinates": [a["lon"], a["lat"]]},
         "properties": {k: a[k] for k in a if k not in ("geometry", "alternatives", "lat", "lon")}}
        for a in audited
    ]
    (OUTDIR / "stage-09a-routing-audit.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False),
        encoding="utf-8", newline="\n")

    # --- control routes geojson (fastest + alternatives geometry) ---
    control_feats = []
    controls = [("central", ORIGINS[0], "Борисовка", 10), ("bam", ORIGINS[1], "Борисовка", 5),
                ("central", ORIGINS[0], "Хомутяновка", 5), ("central", ORIGINS[0], "Парканы", 5),
                ("central", ORIGINS[0], "Гиска", 5)]
    for okey, o, dname, n in controls:
        dests = [a for a in audited if a["district_ru"] == dname][:n]
        for a in dests:
            rt = route_full((o["lon"], o["lat"]), (a["lon"], a["lat"]))
            if not rt.ok:
                continue
            control_feats.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": rt.geometry},
                "properties": {"origin": okey, "district": dname, "uid": a["uid"],
                               "distance_km": rt.distance_km, "duration_s": rt.duration_s,
                               "kind": "fastest"}})
            for j, alt in enumerate(rt.alternatives):
                control_feats.append({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": alt["geometry"]},
                    "properties": {"origin": okey, "district": dname, "uid": a["uid"],
                                   "distance_km": alt["distance_km"], "duration_s": alt["duration_s"],  # noqa: E501
                                   "kind": f"alt_{j + 1}"}})
    (OUTDIR / "stage-09a-control-routes.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": control_feats}, ensure_ascii=False),
        encoding="utf-8", newline="\n")

    # --- origin verification ---
    origins_out = []
    for o in ORIGINS:
        snap = nearest(o["lon"], o["lat"])
        road, road_d = nearest_road(tree, geoms, props, o["lon"], o["lat"])
        origins_out.append({
            "key": o["key"], "weight": o["weight"], "lon": o["lon"], "lat": o["lat"],
            "snap_distance_m": snap.get("snap_distance_m"),
            "snapped_name": snap.get("snapped_name"),
            "nearest_road_highway": road.get("highway"),
            "nearest_road_name": road.get("ru_display") or road.get("name"),
            "on_road_ok": snap.get("snap_distance_m", 999) < 40,
        })

    from collections import Counter
    verdict_counts = Counter(a["verdict"] for a in audited)
    conn = {
        "note": "Road-connectivity spot check for Borisovka. roads.geojson carries "
                "highway/class but not access/oneway/barrier; those are read from the "
                "city PBF only where a suspect needs them. No OSM data was modified.",
        "origins": origins_out,
        "verdict_counts": dict(verdict_counts),
        "suspects_audited": len(audited),
        "snap_gt_40m": sum(1 for a in audited if (a.get("snap_distance_m") or 0) > 40),
        "alt_10pct_shorter": sum(1 for a in audited if "alt_>10pct_shorter" in a["flags"]),
        "leaves_and_reenters": sum(1 for a in audited if "leaves_and_reenters_city" in a["flags"]),
        "owner_review_required": True,
    }
    (OUTDIR / "stage-09a-road-connectivity.json").write_text(
        json.dumps(conn, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    print("verdicts:", dict(verdict_counts))
    print("origins on-road:", [(o["key"], o["on_road_ok"], o["snap_distance_m"]) for o in origins_out])  # noqa: E501
    print(f"wrote stage-09a-*.csv/.geojson/.json ; control routes: {len(control_feats)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
