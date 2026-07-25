#!/usr/bin/env python
"""Stage 09B — forced-entry routing, segment validation and metric comparison.

For control homes and every origin (central/BAM/outer) this records the
unrestricted fastest-time route, the shortest-distance variant, OSRM
alternatives, and routes FORCED through each key district entry (via a waypoint),
then VALIDATES the chosen fastest route segment-by-segment: OSRM
`annotations=nodes` gives the OSM node sequence, which is mapped back to OSM ways
(shared-node graph) to read each segment's highway/access/oneway/bridge/tunnel/
layer. A route touching a suspicious segment -> OWNER_REVIEW_ROUTE, and no zone is
proposed from it. Four comparison metrics are computed side by side; none is
auto-chosen. Read-only; no OSM edit, no release, no Direct, no zone.
"""

from __future__ import annotations

import csv
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage09_engine import (  # noqa: E402
    ORIGINS,
    OUTSIDE_MULTIPLIER,
    equivalent_city_km,
    haversine_km,
    load_address_points,
    load_bender_boundary,
    nearest,
    nearest_osm_place,
    segment_in_out_city,
)
from stage09b_entries import build_topo  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
OSRM = "http://127.0.0.1:5000"
SUSPICIOUS_HW = {"service", "footway", "path", "pedestrian", "steps", "track", "construction"}


def _get(path):
    with urllib.request.urlopen(f"{OSRM}/{path}", timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def route_detailed(coords_lonlat):
    """coords_lonlat: list of (lon,lat) waypoints. Returns fastest route with
    OSM node annotations + geometry, plus alternatives (for the 2-point case)."""
    pts = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in coords_lonlat)
    q = urllib.parse.urlencode({
        "overview": "full", "geometries": "geojson",
        "alternatives": "3" if len(coords_lonlat) == 2 else "false",
        "steps": "true", "annotations": "nodes",
    })
    data = _get(f"route/v1/driving/{pts}?{q}")
    if data.get("code") != "Ok" or not data.get("routes"):
        return None
    r = data["routes"][0]
    nodes = []
    for leg in r["legs"]:
        ann = leg.get("annotation", {})
        nodes.extend(ann.get("nodes", []))
    alts = [{"distance_km": round(a["distance"] / 1000, 4), "duration_s": round(a["duration"], 1),
             "geometry": a["geometry"]["coordinates"]} for a in data["routes"][1:]]
    return {
        "distance_km": round(r["distance"] / 1000, 4),
        "duration_s": round(r["duration"], 1),
        "geometry": r["geometry"]["coordinates"],
        "nodes": nodes,
        "alternatives": alts,
    }


def validate_segments(nodes, node_to_ways, ways):
    """Map consecutive OSM node pairs to a way and read its tags. Returns
    (segments, suspicious_flags). Segments outside the local extract are
    'unmapped' (not suspicious)."""
    segs = []
    flags = set()
    unmapped = 0
    for n1, n2 in zip(nodes, nodes[1:], strict=False):
        cand = node_to_ways.get(n1, set()) & node_to_ways.get(n2, set())
        if not cand:
            unmapped += 1
            continue
        wid = next(iter(cand))
        t = ways[wid]["tags"]
        hw = t.get("highway")
        acc_ok = t.get("access") not in ("no", "private") and t.get("motor_vehicle") not in ("no", "private")  # noqa: E501
        seg = {
            "way_id": wid, "highway": hw, "name": t.get("name") or t.get("ru_display") or "",
            "access": t.get("access") or "", "motor_vehicle": t.get("motor_vehicle") or "",
            "oneway": t.get("oneway") or "", "bridge": t.get("bridge") or "",
            "tunnel": t.get("tunnel") or "", "layer": t.get("layer") or "",
            "maxspeed": t.get("maxspeed") or "", "surface": t.get("surface") or "",
        }
        segs.append(seg)
        if hw in SUSPICIOUS_HW:
            flags.add(f"segment_highway_{hw}")
        if not acc_ok:
            flags.add("segment_access_restricted")
    return segs, flags, unmapped


def metrics(fastest, shortest, seg_in_out):
    """Four comparison indices (NOT prices)."""
    gen = equivalent_city_km(seg_in_out["in_city_km"], seg_in_out["outside_city_km"])
    return {
        "A_duration_min": round(fastest["duration_s"] / 60, 2),
        "B_distance_km": fastest["distance_km"],
        "C_generalized_km": gen,
        # D: distance + provisional time value (0.5 km-equivalent per extra minute)
        "D_time_value_index": round(fastest["distance_km"] + 0.5 * fastest["duration_s"] / 60, 3),
        "shortest_distance_km": shortest["distance_km"] if shortest else fastest["distance_km"],
        "shortest_duration_min": round((shortest or fastest)["duration_s"] / 60, 2),
    }


def control_set(pts):
    serv = [p for p in pts if p["service_status"] in ("standard", "low_density")
            and p["address_status"] == "verified_osm_address"]
    for p in serv:
        p["district"] = (nearest_osm_place(p["lat"], p["lon"])[0]
                         if p["settlement_ru"] == "Бендеры" else p["settlement_ru"])
    out = []
    out += [p for p in serv if p["district"] in ("Борисовка", "Хомутяновка")]
    out += [p for p in serv if p["settlement_ru"] == "Северный" or p["district"] == "Северный"]
    for settle in ("Парканы", "Гиска"):
        pool = sorted([p for p in serv if p["settlement_ru"] == settle],
                      key=lambda x: haversine_km(x["lat"], x["lon"], ORIGINS[0]["lat"], ORIGINS[0]["lon"]))  # noqa: E501
        n = len(pool)
        idx = list(range(30)) + list(range(n // 2 - 15, n // 2 + 15)) + list(range(n - 30, n))
        out += [pool[i] for i in idx if 0 <= i < n]
    prot = [p for p in serv if p["settlement_ru"] == "Протягайловка"]
    out += prot[::max(1, len(prot) // 40)]  # representative sample
    return out


def key_entries():
    rows = list(csv.DictReader(
        (REPO / "docs/data/stage-09b-district-entries.csv").open(encoding="utf-8")))
    by_d = {}
    for r in rows:
        if r["entry_lon"] == "" or r["connected_to_city_graph"] != "True":
            continue
        d = r["district_or_settlement"]
        by_d.setdefault(d, [])
        # prefer rail crossings + higher road classes; cap 12 per district
        if r["basis"] == "rail_level_crossing_node" or r["highway"] in (
                "primary", "secondary", "tertiary", "unclassified", "residential"):
            by_d[d].append(r)
    for d in by_d:
        by_d[d] = by_d[d][:12]
    return by_d


def main() -> int:
    (REPO / "reports/stage-09b").mkdir(parents=True, exist_ok=True)
    boundary = load_bender_boundary()
    h = build_topo()
    pts = load_address_points()
    controls = control_set(pts)
    entries = key_entries()
    print(f"control homes: {len(controls)}; key entries per district: "
          f"{ {k: len(v) for k, v in entries.items()} }")

    metric_rows, seg_rows, entry_rows = [], [], []
    invalid_routes = 0
    seg_budget = 400  # cap detailed segment validations
    for _hi, p in enumerate(controls):
        dest = (p["lon"], p["lat"])
        snap = nearest(p["lon"], p["lat"])
        per_origin_metric = {}
        for o in ORIGINS:
            det = route_detailed([(o["lon"], o["lat"]), dest])
            if not det:
                continue
            shortest = min([det] + det["alternatives"],
                           key=lambda r: r["distance_km"]) if det["alternatives"] else det
            seg_io = segment_in_out_city(det["geometry"], boundary)
            m = metrics(det, shortest, seg_io)
            per_origin_metric[o["key"]] = m
            # segment validation only from central origin, budgeted
            if o["key"] == "central" and seg_budget > 0:
                segs, flags, unmapped = validate_segments(det["nodes"], h.node_to_ways, h.ways)
                seg_budget -= 1
                status = "OWNER_REVIEW_ROUTE" if flags else "OK"
                if flags:
                    invalid_routes += 1
                for s in segs[:60]:
                    seg_rows.append({"uid": p["uid"], "district": p["district"],
                                     "origin": "central", **s})
                m["segment_status"] = status
                m["segment_flags"] = ";".join(sorted(flags))
                m["segments_unmapped_outside_extract"] = unmapped
        c = per_origin_metric.get("central", {})
        metric_rows.append({
            "uid": p["uid"], "settlement_ru": p["settlement_ru"], "district": p["district"],
            "street_ru": p["street_ru"], "housenumber": p["housenumber"],
            "current_zone": p["zone_id"], "snap_distance_m": snap.get("snap_distance_m"),
            "central_A_duration_min": c.get("A_duration_min"),
            "central_B_distance_km": c.get("B_distance_km"),
            "central_C_generalized_km": c.get("C_generalized_km"),
            "central_D_time_value": c.get("D_time_value_index"),
            "central_shortest_distance_km": c.get("shortest_distance_km"),
            "central_segment_status": c.get("segment_status", ""),
            "central_segment_flags": c.get("segment_flags", ""),
            "bam_B_distance_km": per_origin_metric.get("bam", {}).get("B_distance_km"),
            "outer_B_distance_km": per_origin_metric.get("outer_other", {}).get("B_distance_km"),
        })

    # forced-entry comparison: 10 homes per district x each key entry (central origin)
    from collections import defaultdict
    by_dist = defaultdict(list)
    for p in controls:
        by_dist[p["district"]].append(p)
    for dname, ents in entries.items():
        homes = by_dist.get(dname, [])[:10]
        for p in homes:
            unrestricted = route_detailed([(ORIGINS[0]["lon"], ORIGINS[0]["lat"]), (p["lon"], p["lat"])])  # noqa: E501
            best_unres = unrestricted["distance_km"] if unrestricted else None
            for e in ents:
                via = route_detailed([(ORIGINS[0]["lon"], ORIGINS[0]["lat"]),
                                      (float(e["entry_lon"]), float(e["entry_lat"])),
                                      (p["lon"], p["lat"])])
                if not via:
                    continue
                entry_rows.append({
                    "district": dname, "uid": p["uid"], "entry_id": e["entry_id"],
                    "entry_road": e["road_name"], "entry_basis": e["basis"],
                    "via_distance_km": via["distance_km"], "via_duration_s": via["duration_s"],
                    "unrestricted_distance_km": best_unres,
                    "delta_km": round(via["distance_km"] - best_unres, 4) if best_unres else None,
                })

    _write_csv("docs/data/stage-09b-metric-comparison.csv", metric_rows)
    _write_csv("docs/data/stage-09b-route-segments.csv", seg_rows)
    _write_csv("docs/data/stage-09b-entry-route-comparison.csv", entry_rows)
    print(f"metric rows {len(metric_rows)}, segment rows {len(seg_rows)}, "
          f"entry-route rows {len(entry_rows)}, invalid routes (owner review) {invalid_routes}")
    print(f"outside_multiplier={OUTSIDE_MULTIPLIER}")
    return 0


def _write_csv(rel, rows):
    p = REPO / rel
    if not rows:
        p.write_text("", encoding="utf-8")
        return
    cols = list(rows[0].keys())
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
