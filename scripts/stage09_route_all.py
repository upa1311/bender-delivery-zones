#!/usr/bin/env python
"""Stage 09 — route every serviceable verified address from every origin with the
FASTEST VALID route (OSRM min-duration shortest path over the full car graph),
split it into in-city / outside-city km against the real Bender OSM boundary, and
cache compact per-address metrics for the zone recompute and reports.

No prices, no immutable-release edits, no Direct changes. `equivalent_city_km` is
a provisional relative difficulty weight (owner_review), not money.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage09_engine import (  # noqa: E402
    ORIGINS,
    OUTSIDE_MULTIPLIER,
    equivalent_city_km,
    load_address_points,
    load_bender_boundary,
    nearest_osm_place,
    route_full,
    segment_in_out_city,
)

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs/data/stage-09-routed.jsonl"


def main() -> int:
    boundary = load_bender_boundary()
    pts = load_address_points()
    serviceable = [
        p
        for p in pts
        if p["service_status"] in ("standard", "low_density")
        and p["address_status"] == "verified_osm_address"
    ]
    print(f"routing {len(serviceable)} serviceable addresses x {len(ORIGINS)} origins")
    t0 = time.time()
    with OUT.open("w", encoding="utf-8", newline="\n") as fh:
        for i, p in enumerate(serviceable):
            if p["settlement_ru"] == "Бендеры":
                district, dist_to_place = nearest_osm_place(p["lat"], p["lon"])
            else:
                district, dist_to_place = p["settlement_ru"], 0.0
            per_origin = {}
            for o in ORIGINS:
                r = route_full((o["lon"], o["lat"]), (p["lon"], p["lat"]))
                if not r.ok:
                    per_origin[o["key"]] = None
                    continue
                seg = segment_in_out_city(r.geometry, boundary)
                per_origin[o["key"]] = {
                    "distance_km": r.distance_km,
                    "duration_s": r.duration_s,
                    "in_city_km": seg["in_city_km"],
                    "outside_city_km": seg["outside_city_km"],
                    "crosses_boundary": seg["crosses_boundary"],
                    "reenters_city": seg["reenters_city"],
                    "first_exit_lonlat": seg["first_exit_lonlat"],
                    "eq_km": equivalent_city_km(seg["in_city_km"], seg["outside_city_km"]),
                    "n_alternatives": len(r.alternatives),
                    # shortest-distance among fastest + alternatives (for QA flags)
                    "min_alt_distance_km": min(
                        [r.distance_km] + [a["distance_km"] for a in r.alternatives]
                    ),
                }
            c = per_origin.get("central")
            bam = per_origin.get("bam")
            outer = per_origin.get("outer_other")

            def wsum(key, wc, wb, wo, c=c, bam=bam, outer=outer):
                parts, wt = 0.0, 0.0
                for src, w in ((c, wc), (bam, wb), (outer, wo)):
                    if src is not None:
                        parts += src[key] * w
                        wt += w
                return round(parts / wt, 4) if wt else None

            rec = {
                "uid": p["uid"],
                "settlement_ru": p["settlement_ru"],
                "district_ru": district,
                "dist_to_place_km": dist_to_place,
                "street_ru": p["street_ru"],
                "housenumber": p["housenumber"],
                "lat": p["lat"],
                "lon": p["lon"],
                "current_zone": p["zone_id"],
                "catalog_central_km": p["central_km"],
                "catalog_bam_km": p["bam_km"],
                "catalog_expected_km": p["expected_km"],
                "per_origin": per_origin,
                # weighted raw km — variant A (85/15 central/bam) and B (85/10/5)
                "raw_km_A": wsum("distance_km", 0.85, 0.15, 0.0),
                "raw_km_B": wsum("distance_km", 0.85, 0.10, 0.05),
                # weighted equivalent-city km — same two weightings
                "eq_km_A": wsum("eq_km", 0.85, 0.15, 0.0),
                "eq_km_B": wsum("eq_km", 0.85, 0.10, 0.05),
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if (i + 1) % 1000 == 0:
                print(f"  {i + 1}/{len(serviceable)}  {time.time() - t0:.0f}s")
    print(f"done {len(serviceable)} in {time.time() - t0:.0f}s -> {OUT.name}")
    print(f"outside_multiplier={OUTSIDE_MULTIPLIER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
