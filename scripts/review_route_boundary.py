"""Prepare the /review/ real-route + PROVISIONAL tariff-boundary data — DESIGN ONLY.

Single fixed GIS origin (architecture kept multi-restaurant-ready):
    origin = 46.82388, 29.48313   (the one confirmed central point; no 14 restaurants)

Builds a REAL driving route origin -> Парканы, ул. Котовского and derives PROVISIONAL
tariff-boundary candidates from where that route crosses each real city boundary
(OSM relations 12463379 / 9581354 / 944727, already extracted). No ГАИ-office address
is used and none of the conflicting post coordinates is treated as authoritative — the
admin will drag the boundary on /review/ to the actual exit ("ул. Котовского — пост
МС РФ"); this file only provides honest, data-derived starting candidates.

external part starts only AFTER the (admin-set) boundary; external_km = route length
beyond it; external_surcharge = max(5, external_km*2); base = 14 (<=3km) else
14+(km-3)*4; reference_price = base + external_surcharge. Nothing is published as a
final price.

Route provider: OSRM demo (router.project-osrm.org) — ALTERNATIVE_PROVIDER_COMPARISON,
consistent with Yandex on the control leg (origin -> Парканы Котовского ≈ 4.72 km).
Raw response cached; re-run offline uses the cache.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import urllib.request
from pathlib import Path

from shapely.geometry import LineString, shape

ROOT = Path(__file__).resolve().parents[1]
OC_SPEC = importlib.util.spec_from_file_location(
    "outside_city_distance", ROOT / "scripts/outside_city_distance.py")
OC = importlib.util.module_from_spec(OC_SPEC)
OC_SPEC.loader.exec_module(OC)

BND = ROOT / "data/interim/osm-boundaries"
RAW = ROOT / "data/interim/review-route/raw"
OUT_JSON = ROOT / "docs/review/data/parkany-route-boundary.json"
ORIGIN = (29.48313, 46.82388)  # lon, lat — the single fixed origin
OSRM = ("https://router.project-osrm.org/route/v1/driving/"
        "{o_lon},{o_lat};{d_lon},{d_lat}?overview=full&geometries=geojson")


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _haversine_km(a, b):
    R = 6371.0088
    dlat = math.radians(b[1] - a[1])
    dlon = math.radians(b[0] - a[0])
    la1, la2 = math.radians(a[1]), math.radians(b[1])
    h = math.sin(dlat / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def cumulative_km(coords):
    out = [0.0]
    for i in range(1, len(coords)):
        out.append(out[-1] + _haversine_km(coords[i - 1], coords[i]))
    return out


def fetch_route(dest, aid):
    RAW.mkdir(parents=True, exist_ok=True)
    raw_path = RAW / f"{aid}.osrm.json"
    if raw_path.exists():
        return json.loads(raw_path.read_bytes())
    url = OSRM.format(o_lon=f"{ORIGIN[0]:.6f}", o_lat=f"{ORIGIN[1]:.6f}",
                      d_lon=f"{dest[0]:.6f}", d_lat=f"{dest[1]:.6f}")
    b = urllib.request.urlopen(  # noqa: S310
        urllib.request.Request(url, headers={"User-Agent": "bdz-review"}), timeout=40).read()
    obj = json.loads(b)
    raw_path.write_bytes(json.dumps(obj, ensure_ascii=False, indent=2,
                                    sort_keys=True).encode("utf-8"))
    return obj


def pick_destination():
    """Парканы, ул. Котовского address whose canonical route_km is closest to the
    Yandex control leg (~4.72 km)."""
    addrs = OC.ZE.ZM.load_addresses()
    kot = [r for r in addrs if r["settlement"] == "Парканы"
           and "отовск" in (r.get("street") or "")]
    kot.sort(key=lambda r: abs(r["route_km"] - 4.72))
    r = kot[0]
    return r, (r["lon"], r["lat"])


def boundary_crossings(route_line, coords, cum):
    """For each real city boundary, the along-route distance (km from origin) at which
    the route first LEAVES the boundary (a data-derived PROVISIONAL candidate)."""
    cands = []
    for rid in ("12463379", "9581354", "944727"):
        geom = shape(json.loads((BND / f"relation-{rid}.geojson").read_text("utf-8"))
                     ["geometry"])
        bnd = geom if geom.is_valid else geom.buffer(0)
        # first vertex that is outside the boundary => approximate exit point
        exit_idx = None
        from shapely.geometry import Point
        for i, c in enumerate(coords):
            if not bnd.contains(Point(c[0], c[1])):
                exit_idx = i
                break
        if exit_idx is None:
            cands.append({"relation_id": rid, "crosses": False})
            continue
        cands.append({
            "relation_id": rid, "crosses": True,
            "exit_index": exit_idx,
            "exit_lonlat": [round(coords[exit_idx][0], 6), round(coords[exit_idx][1], 6)],
            "km_from_origin": round(cum[exit_idx], 4),
            "external_km_beyond": round(cum[-1] - cum[exit_idx], 4),
        })
    return cands


def main():
    rec, dest = pick_destination()
    aid = f"review-parkany-{rec['uid']}"
    obj = fetch_route(dest, aid)
    rt = obj["routes"][0]
    coords = rt["geometry"]["coordinates"]  # [lon,lat]
    osrm_km = rt["distance"] / 1000.0
    cum = cumulative_km(coords)
    route_line = LineString(coords)
    cands = boundary_crossings(route_line, coords, cum)
    # provisional default = first city boundary (relation 12463379) crossing if any,
    # else midpoint of the route (admin will drag it to the real пост).
    default = next((c for c in cands if c.get("crosses")), None)
    default_km = default["km_from_origin"] if default else round(cum[-1] * 0.6, 4)

    payload = {
        "note": "DESIGN / PROVISIONAL — not an approved price or final boundary",
        "origin": {"lat": ORIGIN[1], "lon": ORIGIN[0],
                   "label": "Фиксированная точка отправления (GIS)"},
        "destination": {"lat": rec["lat"], "lon": rec["lon"],
                        "address": f"Парканы, {rec['street']} {rec['house']}",
                        "canonical_route_km": rec["route_km"]},
        "provider": "OSRM demo (ALTERNATIVE_PROVIDER_COMPARISON)",
        "yandex_control_km": 4.72,
        "osrm_total_km": round(osrm_km, 3),
        "route_lonlat": [[round(x, 6), round(y, 6)] for x, y in coords],
        "route_cum_km": [round(v, 4) for v in cum],
        "boundary_candidates": cands,
        "provisional_boundary_km_from_origin": default_km,
        "raw_sha256": _sha((RAW / f"{aid}.osrm.json").read_bytes()),
        "formula": {"base": "14 if km<=3 else 14+(km-3)*4",
                    "external_surcharge": "max(5, external_km*2)",
                    "reference_price": "base + external_surcharge"},
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8", newline="\n")
    print(json.dumps({"dest": payload["destination"]["address"],
                      "osrm_total_km": payload["osrm_total_km"],
                      "yandex_control_km": 4.72,
                      "candidates": [(c["relation_id"], c.get("km_from_origin"),
                                      c.get("external_km_beyond")) for c in cands],
                      "provisional_km": default_km}, ensure_ascii=False))


if __name__ == "__main__":
    main()
