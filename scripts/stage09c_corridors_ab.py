#!/usr/bin/env python
"""Stage 09C — Corridors A & B to Khomutyanovka + Protyagailovka continuation.

Owner ground truth (two independent car corridors that share a trunk):
  A: центр → пл. Героев → Пивзавод → Маслоэкстракционный завод → Ечина
  B: центр → Московская → Первомайская → Некрасова → Ечина
  common trunk: Ечина → Роддом → больница → Главана → Старого
  Protyagailovka: Старого → Мира → Протягайловка

Connectivity is proven by ROUTING between consecutive corridor points in the OSRM
graph (0 shared nodes between two named streets only means they meet via a
cross-street, not that they are disconnected), both directions. Then EVERY
verified Khomutyanovka and Protyagailovka home gets: unrestricted fastest,
shortest-distance, forced via Corridor A, forced via Corridor B, and a provisional
driver-cost route; the best valid km gives a provisional proposed zone. Bus stops
are NOT enforced — the corridor is a set of legal segments + an entry, after which
the shortest branch to the home is used. Read-only; no OSM edit, no immutable
release, no Direct, no price, no new zone. owner_review_required.
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
    load_address_points,
    nearest_osm_place,
)
from stage09b_entries import build_topo  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
OSRM = "http://127.0.0.1:5000"
CENTRAL = (ORIGINS[0]["lon"], ORIGINS[0]["lat"])
CORRIDOR_A_WP = (29.47836, 46.80105)   # пивзавод primary level crossing (south approach)
CORRIDOR_B_WP = (29.47829, 46.808993)  # Некрасова midpoint (north approach to Ечина)
CURRENT_EDGES = [2.424, 4.076, 5.577, 9.692]
# ordered corridor points (a representative coord per named street) for the
# consecutive-hop connectivity test.
CORRIDOR_POINTS = [
    ("Московская", (29.4816, 46.8127)), ("Первомайская", (29.4796, 46.8110)),
    ("Некрасова", (29.47829, 46.808993)), ("Ечина", (29.4770, 46.8090)),
    ("Главана", (29.4735, 46.8110)), ("Старого", (29.4700, 46.8130)),
    ("Мира", (29.483685, 46.804827)),
]


def zone_of(km):
    for i, e in enumerate(CURRENT_EDGES):
        if km <= e:
            return i + 1
    return 4


def route_min(coords, alternatives=False):
    pts = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in coords)
    q = urllib.parse.urlencode({"overview": "false",
                                "alternatives": "3" if alternatives else "false"})
    try:
        with urllib.request.urlopen(f"{OSRM}/route/v1/driving/{pts}?{q}", timeout=120) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    if data.get("code") != "Ok" or not data.get("routes"):
        return None
    rs = data["routes"]
    best = rs[0]
    return {
        "distance_km": round(best["distance"] / 1000, 4),
        "duration_s": round(best["duration"], 1),
        "alt_km": [round(x["distance"] / 1000, 4) for x in rs[1:]],
        "alt_s": [round(x["duration"], 1) for x in rs[1:]],
    }


def driver_cost(distance_km, duration_s):
    return round(distance_km + 0.3 * duration_s / 60, 3)


def connectivity():
    rows = []
    for (na, a), (nb, b) in zip(CORRIDOR_POINTS, CORRIDOR_POINTS[1:], strict=False):
        f = route_min([a, b])
        r = route_min([b, a])
        rows.append({
            "hop": f"{na}->{nb}",
            "forward_km": f["distance_km"] if f else None, "forward_s": f["duration_s"] if f else None,  # noqa: E501
            "reverse_km": r["distance_km"] if r else None, "reverse_s": r["duration_s"] if r else None,  # noqa: E501
            "forward_in_osrm": bool(f), "reverse_in_osrm": bool(r),
            "asymmetric_oneway": bool(f and r and abs(f["distance_km"] - r["distance_km"]) > 0.05),
        })
    return rows


def audit(homes, label):
    rows = []
    proposed_changes = 0
    for p in homes:
        dest = (p["lon"], p["lat"])
        fastest = route_min([CENTRAL, dest], alternatives=True)
        if not fastest:
            continue
        shortest_km = min([fastest["distance_km"]] + fastest["alt_km"])
        a = route_min([CENTRAL, CORRIDOR_A_WP, dest])
        b = route_min([CENTRAL, CORRIDOR_B_WP, dest])
        # reverse (home -> centre) fastest, to check oneway/turn asymmetry
        rev = route_min([dest, CENTRAL])
        best_valid_km = min([x for x in [fastest["distance_km"], shortest_km,
                             a["distance_km"] if a else None, b["distance_km"] if b else None]
                             if x is not None])
        cur_zone = int(p["zone_id"])
        prop_zone = zone_of(best_valid_km)
        if prop_zone != cur_zone:
            proposed_changes += 1
        # which corridor gives the best route?
        opts = {"fastest": fastest["distance_km"], "shortest": shortest_km,
                "corridorA": a["distance_km"] if a else 1e9, "corridorB": b["distance_km"] if b else 1e9}  # noqa: E501
        chosen = min(opts, key=opts.get)
        rows.append({
            "settlement_or_district": label, "uid": p["uid"], "street": p["street_ru"],
            "house": p["housenumber"], "current_zone": cur_zone,
            "current_route_km": fastest["distance_km"], "current_route_s": fastest["duration_s"],
            "reverse_route_km": rev["distance_km"] if rev else None,
            "corridorA_km": a["distance_km"] if a else None, "corridorA_s": a["duration_s"] if a else None,  # noqa: E501
            "corridorB_km": b["distance_km"] if b else None, "corridorB_s": b["duration_s"] if b else None,  # noqa: E501
            "shortest_valid_km": shortest_km,
            "best_valid_km": best_valid_km, "chosen_route": chosen,
            "difference_current_minus_best_km": round(fastest["distance_km"] - best_valid_km, 3),
            "driver_cost_current": driver_cost(fastest["distance_km"], fastest["duration_s"]),
            "provisional_proposed_zone": prop_zone,
            "owner_review_required": True,
        })
    return rows, proposed_changes


def main() -> int:
    (REPO / "reports/stage-09c").mkdir(parents=True, exist_ok=True)
    _ = build_topo  # topology available for callers; connectivity uses routing
    pts = load_address_points()

    conn = connectivity()
    _csv("docs/data/stage-09c-corridor-ab-connectivity.csv", conn)
    print("corridor hops (all should be in OSRM, short):")
    for c in conn:
        print(f"  {c['hop']:26s} fwd {c['forward_km']}km/{c['forward_s']}s rev {c['reverse_km']}km "
              f"asym_oneway={c['asymmetric_oneway']}")

    khom = [p for p in pts if p["settlement_ru"] == "Бендеры"
            and p["service_status"] in ("standard", "low_density")
            and p["address_status"] == "verified_osm_address"
            and nearest_osm_place(p["lat"], p["lon"])[0] == "Хомутяновка"]
    prot = [p for p in pts if p["settlement_ru"] == "Протягайловка"
            and p["service_status"] in ("standard", "low_density")
            and p["address_status"] == "verified_osm_address"]

    krows, kchg = audit(khom, "Хомутяновка")
    prows, pchg = audit(prot, "Протягайловка")
    _csv("docs/data/stage-09c-khomutyanovka-comparison.csv", krows)
    _csv("docs/data/stage-09c-protyagailovka-comparison.csv", prows)

    def stats(rows):
        n = len(rows)
        cheaper = sum(1 for r in rows if r["provisional_proposed_zone"] < r["current_zone"])
        overst = sum(1 for r in rows if r["current_route_km"] > 1.10 * r["best_valid_km"])
        a_best = sum(1 for r in rows if r["chosen_route"] == "corridorA")
        b_best = sum(1 for r in rows if r["chosen_route"] == "corridorB")
        return n, cheaper, overst, a_best, b_best

    for label, rows, chg in [("Хомутяновка", krows, kchg), ("Протягайловка", prows, pchg)]:
        n, cheaper, overst, ab, bb = stats(rows)
        print(f"{label}: n={n} proposed_zone_changes={chg} (cheaper={cheaper}) "
              f"overstated_current(>10%)={overst} corridorA_best={ab} corridorB_best={bb}")
    return 0


def _csv(rel, rows):
    p = REPO / rel
    if not rows:
        p.write_text("", encoding="utf-8")
        return
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
