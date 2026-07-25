#!/usr/bin/env python
"""Stage 10 — ROAD_TRUTH verdicts from the AVAILABLE multi-source evidence.

Pluggable multi-engine harness. In this environment only OSRM is live (on the
FULL Moldova PBF); GraphHopper/Valhalla/openrouteservice and the external QA
sources are unavailable (see stage10-source-status.json) and are NEVER faked.
Verdicts therefore use OSRM + the local OSM topology + the owner-confirmed public
-transport corridors (Stage 09B/09C). Cross-engine and imagery verdicts that need
the missing sources are marked INSUFFICIENT_EVIDENCE (pending), not invented.

It also aggregates, for the owner: every real district entry, the suspect OSM
ways/nodes found so far, and the count of addresses with an overstated current
route. Read-only; no OSM edit, no immutable release, no Direct, no price, no zone.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage10_sources import probe  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
D = REPO / "docs/data"

VERDICTS = [
    "CONFIRMED_BY_ALL", "OSM_DATA_MISSING", "OSM_CONNECTIVITY_BROKEN",
    "OSRM_PROFILE_ERROR", "ROUTER_DISAGREEMENT", "ONEWAY_DIRECTION_DIFFERENCE",
    "TURN_RESTRICTION_ISSUE", "PUBLIC_TRANSPORT_CORRIDOR_CONFIRMED",
    "IMAGERY_CONFIRMED", "INSUFFICIENT_EVIDENCE",
]


def read_csv(name):
    p = D / name
    return list(csv.DictReader(p.open(encoding="utf-8"))) if p.exists() else []


def owner_corridors():
    """Owner-confirmed corridors and their Stage 09B/09C verification state."""
    return [
        {"corridor": "Borisovka north (путепровод Кишинёв–Тирасполь)",
         "districts": "Борисовка", "osm_match_ways": 67,
         "osrm_traversable": True, "in_pbf": True, "oneway_asymmetric": True,
         "pt_source": "EasyWay route №5 (owner)",
         "note": "Кишинёв–Тирасполь bridge=yes layer=2; shortest route uses it; "
                 "168/511 Borisovka homes cheaper on the shortest km."},
        {"corridor": "Khomutyanovka A (пл.Героев→Пивзавод→Ечина)",
         "districts": "Хомутяновка", "osm_match_ways": 5,
         "osrm_traversable": True, "in_pbf": True, "oneway_asymmetric": True,
         "pt_source": "EasyWay route №5 south (owner)",
         "note": "Ленинский primary level crossing (way 115331526); does NOT shorten "
                 "Khomutyanovka (routes already optimal)."},
        {"corridor": "Khomutyanovka B (Московская→Первомайская→Некрасова→Ечина)",
         "districts": "Хомутяновка", "osm_match_ways": 22,
         "osrm_traversable": True, "in_pbf": True, "oneway_asymmetric": True,
         "pt_source": "EasyWay route (owner)",
         "note": "all hops routable in OSRM; corridorB never beats unrestricted route."},
        {"corridor": "Protyagailovka (Старого→Мира→Протягайловка)",
         "districts": "Протягайловка", "osm_match_ways": 10,
         "osrm_traversable": True, "in_pbf": True, "oneway_asymmetric": True,
         "pt_source": "EasyWay route (owner)",
         "note": "Старого→Мира routable both ways (oneway-asymmetric); does not shorten."},
    ]


def verdict_for(c, engines_live):
    # We have OSRM + OSM + the owner PT corridor. Cross-engine agreement needs the
    # missing routers/imagery -> pending.
    if not c["in_pbf"]:
        return "OSM_DATA_MISSING"
    if not c["osrm_traversable"]:
        return "OSM_CONNECTIVITY_BROKEN"
    base = "PUBLIC_TRANSPORT_CORRIDOR_CONFIRMED"
    cross = "CONFIRMED_BY_ALL" if len(engines_live) >= 3 else "INSUFFICIENT_EVIDENCE"
    return f"{base}; cross_engine={cross}"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    status = probe()
    (D / "stage10-source-status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    live = status["live_local_routers"]

    # 1. road-truth verdicts per owner corridor
    rt_rows = []
    for c in owner_corridors():
        rt_rows.append({**c, "engines_live": ",".join(live),
                        "road_truth_verdict": verdict_for(c, live),
                        "cross_engine_pending": "GraphHopper/Valhalla/openrouteservice (need JVM/Docker)",  # noqa: E501
                        "imagery_pending": "Mapillary/KartaView (need token)",
                        "external_qa_pending": "Yandex/Google Routes (need API key)",
                        "owner_review_required": True})
    _csv("stage10-road-truth.csv", rt_rows)

    # 2. all real entries (Stage 09B) + PT corridor entries -> one geojson
    ent = read_csv("stage-09b-district-entries.csv")
    feats = []
    for e in ent:
        if e.get("entry_lon") in ("", None):
            continue
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [float(e["entry_lon"]), float(e["entry_lat"])]},  # noqa: E501
                      "properties": {k: e.get(k) for k in
                                     ("entry_id", "district_or_settlement", "basis", "road_name",
                                      "highway", "connected_to_city_graph", "owner_review_required")}})  # noqa: E501
    (D / "stage10-entries.geojson").write_text(
        json.dumps({"type": "FeatureCollection",
                    "note": "All real car entries per district (Stage 09B), connectivity by shared graph node.",  # noqa: E501
                    "features": feats}, ensure_ascii=False), encoding="utf-8", newline="\n")

    # 3. engine-disagreement layer — only OSRM is live, so no cross-engine rows yet
    disagreements = []
    if len(live) < 2:
        note = ("Only OSRM is live. Multi-engine disagreement detection is PENDING a "
                "JVM (GraphHopper/openrouteservice) and/or Docker (Valhalla) on the full "
                "Moldova PBF. No disagreement is fabricated.")
    else:
        note = "multi-engine comparison ran"
    _csv("stage10-engine-disagreements.csv",
         disagreements or [{"status": "PENDING_MULTI_ENGINE", "note": note}])

    # 4. suspect OSM ways/nodes gathered so far (real, from Stage 09A/09B)
    suspect = []
    for r in read_csv("stage-09a-routing-audit.csv"):
        if r.get("verdict") in ("WRONG_ADDRESS_SNAP", "WRONG_ACCESS_TAG"):
            suspect.append({"source": "stage-09a", "kind": r["verdict"],
                            "uid": r.get("uid"), "district": r.get("district_ru"),
                            "detail": f"snap {r.get('snap_distance_m')}m, road {r.get('nearest_road_highway')}",  # noqa: E501
                            "owner_review_required": True})
    for r in read_csv("stage-09b-road-rail-crossings.csv"):
        if r.get("classification") in ("BROKEN_CONNECTIVITY", "GEOMETRY_ONLY_NO_CONNECTION",
                                       "UNKNOWN_OWNER_REVIEW"):
            suspect.append({"source": "stage-09b-crossings", "kind": r["classification"],
                            "uid": r.get("car_way_id"), "district": "rail-corridor",
                            "detail": f"{r.get('car_highway')} {r.get('car_name')} @ {r.get('lat')},{r.get('lon')}",  # noqa: E501
                            "owner_review_required": True})
    _csv("stage10-suspect-osm-ways.csv", suspect)

    # 5. overstated-address counts across districts (real, from prior stages)
    def count_over(name, kmcol, bestcol):
        rows = read_csv(name)
        n = 0
        for r in rows:
            try:
                if float(r[kmcol]) > 1.10 * float(r[bestcol]):
                    n += 1
            except (KeyError, ValueError, TypeError):
                pass
        return len(rows), n

    over = []
    # Borisovka: shortest vs fastest (Stage 09B metric comparison)
    bmc = read_csv("stage-09b-metric-comparison.csv")
    b_over = sum(1 for r in bmc if r.get("district") == "Борисовка"
                 and _f(r, "central_B_distance_km") and _f(r, "central_shortest_distance_km")
                 and _f(r, "central_shortest_distance_km") < 0.9 * _f(r, "central_B_distance_km"))
    over.append({"district": "Борисовка", "basis": "shortest >10% under fastest (metric)", "overstated": b_over,  # noqa: E501
                 "note": "north путепровод shortcut"})
    kn, ko = count_over("stage-09c-khomutyanovka-comparison.csv", "current_route_km", "best_valid_km")  # noqa: E501
    over.append({"district": "Хомутяновка", "basis": "current >10% over best valid", "overstated": ko, "note": f"n={kn}"})  # noqa: E501
    pn, po = count_over("stage-09c-protyagailovka-comparison.csv", "current_route_km", "best_valid_km")  # noqa: E501
    over.append({"district": "Протягайловка", "basis": "current >10% over best valid", "overstated": po, "note": f"n={pn}"})  # noqa: E501
    _csv("stage10-overstated-addresses.csv", over)

    print("ROAD_TRUTH verdicts:")
    for r in rt_rows:
        print(f"  {r['corridor'][:44]:44s} {r['road_truth_verdict']}")
    print("live engines:", live, "| OSRM full-PBF:", status["osrm_on_full_moldova_pbf"])
    print("entries:", len(feats), "| suspect ways:", len(suspect))
    print("overstated:", {o["district"]: o["overstated"] for o in over})
    return 0


def _f(r, k):
    try:
        return float(r[k])
    except (KeyError, ValueError, TypeError):
        return None


def _csv(name, rows):
    p = D / name
    if not rows:
        p.write_text("", encoding="utf-8")
        return
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
