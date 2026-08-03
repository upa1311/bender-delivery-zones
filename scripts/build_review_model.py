"""Build the /review/ delivery-tariff design model — SELF-CONTAINED, no network,
no audit-branch deps, safe to run in CI. DESIGN only: not an approved public price;
the canonical release data is read-only and unchanged.

Committed inputs (all on main):
  releases/bender-zones-v1.1/address-registry.json     — 9,216 canonical addresses
  docs/data/final-address-zone-points.geojson          — coords + central_km + old K4
  docs/review/data/route-mindist-results.json          — OSRM shortest-DISTANCE route
      per uid (fixes the Кишинёвская duration-detour); origin 46.82388,29.48313
  docs/review/data/parkany-route-boundary.json         — real Парканы route + the
      provisional tariff-boundary corridor distance

Outputs (committed, consumed by docs/review/):
  docs/review/data/reference-tariff-v3-summary.json
  docs/review/data/zone-points.json
  docs/review/data/address-index.json
  docs/review/data/reference-tariff-v3.csv

Formula (no rounding; 18/6/10 rejected):
  base = 14 (route_km<=3) else 14 + (route_km-3)*4
  external_surcharge = 0 if external_km<=0 else max(5, external_km*2)
  reference_price = base + external_surcharge
external_km applies ONLY past the single Парканы tariff boundary
(external_km = max(0, route_km - boundary_corridor_km)); other directions keep 0.
Zones are natural breaks (Jenks) on reference_price — never quartiles/equal-km/K4.
"""

from __future__ import annotations

import csv
import json
import math
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "releases/bender-zones-v1.1/address-registry.json"
POINTS = ROOT / "docs/data/final-address-zone-points.geojson"
RD = ROOT / "docs/review/data"
ROUTING = RD / "route-mindist-results.json"
PARKANY = RD / "parkany-route-boundary.json"

ORIGIN = (29.48313, 46.82388)  # lon, lat
SUPPORTED = {"Бендеры", "Парканы", "Гиска", "Протягайловка"}
CITY = "Бендеры"


def base_price(km):
    return 14.0 if km <= 3.0 else 14.0 + (km - 3.0) * 4.0


def external_surcharge(km):
    return 0.0 if km <= 0 else max(5.0, km * 2.0)


def _norm(s):
    return unicodedata.normalize("NFKC", (s or "").strip().casefold())


def _haversine_km(a, b):
    R = 6371.0088
    dlat = math.radians(b[1] - a[1])
    dlon = math.radians(b[0] - a[0])
    h = (math.sin(dlat / 2) ** 2 + math.cos(math.radians(a[1]))
         * math.cos(math.radians(b[1])) * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


def jenks_breaks(values, k):
    data = sorted(values)
    n = len(data)
    if k >= n:
        return data[:]
    m1 = [[0] * (k + 1) for _ in range(n + 1)]
    m2 = [[0.0] * (k + 1) for _ in range(n + 1)]
    for j in range(1, k + 1):
        m1[1][j] = 1
        for i in range(2, n + 1):
            m2[i][j] = float("inf")
    for ln in range(2, n + 1):
        s1 = s2 = wt = 0.0
        for m in range(1, ln + 1):
            i3 = ln - m + 1
            val = data[i3 - 1]
            s2 += val * val
            s1 += val
            wt += 1
            var = s2 - (s1 * s1) / wt
            i4 = i3 - 1
            if i4 != 0:
                for j in range(2, k + 1):
                    if m2[ln][j] >= var + m2[i4][j - 1]:
                        m1[ln][j] = i3
                        m2[ln][j] = var + m2[i4][j - 1]
        m1[ln][1] = 1
        m2[ln][1] = s2 - (s1 * s1) / wt
    kc = [0.0] * k
    kc[k - 1] = data[n - 1]
    kk, idx = n, k
    while idx >= 2:
        kc[idx - 2] = data[m1[kk][idx] - 2]
        kk = m1[kk][idx] - 1
        idx -= 1
    return kc


def gvf(values, breaks):
    data = sorted(values)
    mean = sum(data) / len(data)
    sdam = sum((v - mean) ** 2 for v in data)
    classes = {}
    for v in data:
        ci = 0
        while ci < len(breaks) - 1 and v > breaks[ci]:
            ci += 1
        classes.setdefault(ci, []).append(v)
    sdcm = sum(sum((v - (sum(a) / len(a))) ** 2 for v in a) for a in classes.values())
    return 1.0 - sdcm / sdam if sdam else 1.0


def load_addresses():
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))["addresses"]
    pts = json.loads(POINTS.read_text(encoding="utf-8"))["features"]
    coords, props = {}, {}
    for f in pts:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"]
        coords[p["uid"]] = (lat, lon)
        props[p["uid"]] = p
    rows = []
    for e in registry:
        uid = e["uid"]
        lat, lon = coords.get(uid, (None, None))
        p = props.get(uid, {})
        ck = p.get("central_km")
        zid = str(e.get("zone_id", "")).strip()
        rows.append({"uid": uid, "settlement": e["settlement_ru"],
                     "street": e.get("street_ru") or "",
                     "house": e.get("housenumber") or "", "lat": lat, "lon": lon,
                     "canonical_route_km": float(ck) if ck is not None else None,
                     "old_k4_zone_id": int(zid) if zid.isdigit() else 0})
    rows.sort(key=lambda r: r["uid"])
    return rows


def main():
    addrs = load_addresses()
    routing = json.loads(ROUTING.read_text(encoding="utf-8"))["results"]
    pk = json.loads(PARKANY.read_text(encoding="utf-8"))
    boundary_km = pk["provisional_boundary_km_from_origin"]

    seen, out = {}, []
    for r in addrs:
        uid = r["uid"]
        has_coord = isinstance(r["lat"], (int, float)) and isinstance(r["lon"], (int, float))
        key = (_norm(r["settlement"]), _norm(r["street"]), _norm(r["house"]))
        mres = routing.get(uid)
        rk = mres[0] if mres else None
        dopt = mres[1] if mres else None
        straight = ""
        if not has_coord or not r["street"] or not r["house"]:
            status = "invalid_address"
        elif r["settlement"] not in SUPPORTED:
            status = "outside_supported_area"
        elif key in seen:
            status = "duplicate"
        elif rk is None:
            status = "unreachable"
        else:
            straight = _haversine_km(ORIGIN, (r["lon"], r["lat"]))
            # min-distance routing already fixed the real detour, so only flag
            # implausibly far routes for manual review (a short crow-flies distance
            # across the Днестр/railway is a valid route, not an anomaly).
            status = "manual_review" if rk > 12.0 else "routed"
            straight = round(straight, 3)
        if status not in ("invalid_address", "outside_supported_area", "duplicate"):
            seen.setdefault(key, uid)

        addr = ", ".join(x for x in (r["settlement"], r["street"], str(r["house"])) if x)
        rec = {"uid": uid, "address": addr,
               "territory": r["settlement"], "status": status,
               "canonical_route_km": r["canonical_route_km"],
               "route_km": rk if rk is not None else "",
               "route_km_duration_opt": dopt if dopt is not None else "",
               "straight_km": straight,
               "crosses_checkpoint": "", "external_km": "", "base_price": "",
               "external_surcharge": "", "reference_price": "", "internal_zone": "",
               "routing_status": status, "old_k4_zone_id": r["old_k4_zone_id"],
               "lat": r["lat"], "lon": r["lon"]}
        if status == "routed":
            base = base_price(rk)
            is_park = r["settlement"] == "Парканы"
            ext = max(0.0, rk - boundary_km) if is_park else 0.0
            sur = external_surcharge(ext) if is_park else 0.0
            rec.update({"crosses_checkpoint": bool(is_park and ext > 0),
                        "external_km": round(ext, 3), "base_price": round(base, 3),
                        "external_surcharge": round(sur, 3),
                        "reference_price": round(base + sur, 3)})
        out.append(rec)

    prices = [r["reference_price"] for r in out if r["status"] == "routed"]
    # Jenks on the DISTINCT price levels (rounded 0.1 ₽) keeps the natural-break shape
    # while staying fast; GVF is still measured against the full price distribution.
    levels = sorted({round(p, 1) for p in prices})
    k_eval = {}
    for k in range(3, 8):
        br = jenks_breaks(levels, k)
        k_eval[k] = {"breaks": [round(b, 3) for b in br], "gvf": round(gvf(prices, br), 4)}
    recommended = next((k for k in range(3, 8) if k_eval[k]["gvf"] >= 0.90), 4)
    rec_breaks = jenks_breaks(levels, recommended)

    def zone_of(p):
        ci = 0
        while ci < len(rec_breaks) - 1 and p > rec_breaks[ci]:
            ci += 1
        return ci + 1
    zstats = {}
    for r in out:
        if r["status"] == "routed":
            z = zone_of(r["reference_price"])
            r["internal_zone"] = z
            st = zstats.setdefault(z, {"n": 0, "pmin": 1e9, "pmax": -1e9, "kmin": 1e9,
                                       "kmax": -1e9, "external": 0, "streets": {}})
            st["n"] += 1
            st["pmin"] = min(st["pmin"], r["reference_price"])
            st["pmax"] = max(st["pmax"], r["reference_price"])
            st["kmin"] = min(st["kmin"], r["route_km"])
            st["kmax"] = max(st["kmax"], r["route_km"])
            if r["external_surcharge"] and r["external_surcharge"] > 0:
                st["external"] += 1
            street = rec_street(r)
            st["streets"][street] = st["streets"].get(street, 0) + 1
    for st in zstats.values():
        for kf in ("pmin", "pmax", "kmin", "kmax"):
            st[kf] = round(st[kf], 3)
        st["share_pct"] = round(100 * st["n"] / max(1, len(prices)), 1)
        st["examples"] = [s for s, _ in sorted(st["streets"].items(), key=lambda x: -x[1])[:4]]
        del st["streets"]

    status_counts = {}
    for r in out:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

    kish = [r for r in out if "Кишинёв" in r["address"]]
    kish_detail = [{"id": r["uid"], "address": r["address"], "old_km": r["canonical_route_km"],
                    "new_km": r["route_km"], "duration_opt_km": r["route_km_duration_opt"],
                    "status": r["status"],
                    "reason": ("shortest-distance route selected (was duration-optimal detour)"
                               if r["route_km"] != "" and r["route_km_duration_opt"] != ""
                               and r["route_km"] < r["route_km_duration_opt"] - 0.05
                               else "no shorter alternative — distance unchanged")}
                   for r in kish]

    _write_csv(out)
    _write_points(out, recommended, rec_breaks)
    _write_index(out)
    summary = {
        "model": "review delivery-tariff model (DESIGN, not approved price)",
        "origin": {"lat": ORIGIN[1], "lon": ORIGIN[0]},
        "distance_source": "OSRM shortest-DISTANCE route (fixes duration detour); "
                           "canonical release data unchanged",
        "formula": {"base": "14 if km<=3 else 14+(km-3)*4",
                    "external_surcharge": "max(5, external_km*2) past the Парканы boundary",
                    "rejected": "18 / 6 / 10"},
        "provisional_boundary_km": boundary_km,
        "catalog_total": len(out), "status_counts": status_counts,
        "status_sum": sum(status_counts.values()),
        "status_sum_equals_9216": sum(status_counts.values()) == 9216,
        "priced_addresses": len(prices),
        "zone_candidates_gvf": k_eval, "recommended_zone_count": recommended,
        "recommended_breaks_price": [round(b, 3) for b in rec_breaks],
        "zone_stats": {str(z): zstats[z] for z in sorted(zstats)},
        "kishinevskaya": kish_detail, "kishinevskaya_total": len(kish),
        "kishinevskaya_fixed_count": sum(1 for k in kish_detail if "shortest" in k["reason"]),
        "parkany_control_km": pk["osrm_total_km"],
        "status": "DESIGN — provisional tariff boundary; not a public price",
    }
    (RD / "reference-tariff-v3-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps({"catalog": len(out), "status_sum": summary["status_sum"],
                      "priced": len(prices), "zones": recommended,
                      "breaks": summary["recommended_breaks_price"],
                      "kish_fixed": summary["kishinevskaya_fixed_count"],
                      "kish_total": len(kish)}, ensure_ascii=False))


def rec_street(r):
    return (r["address"].split(",")[1].strip() if "," in r["address"] else r["address"])


def _write_csv(out):
    cols = ["uid", "address", "territory", "status", "canonical_route_km", "route_km",
            "route_km_duration_opt", "straight_km", "crosses_checkpoint", "external_km",
            "base_price", "external_surcharge", "reference_price", "internal_zone",
            "routing_status", "old_k4_zone_id"]
    with (RD / "reference-tariff-v3.csv").open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(out)


def _write_points(out, recommended, rec_breaks):
    scode = {"routed": 1, "duplicate": 2, "outside_supported_area": 4,
             "unreachable": 5, "manual_review": 6}
    pts = []
    for r in out:
        if not isinstance(r["lon"], (int, float)) or not isinstance(r["lat"], (int, float)):
            continue
        z = r["internal_zone"] if r["status"] == "routed" else 0
        pts.append([round(r["lon"], 5), round(r["lat"], 5), z, scode.get(r["status"], 0),
                    r["reference_price"] if r["status"] == "routed" else None,
                    r["old_k4_zone_id"]])
    (RD / "zone-points.json").write_text(
        json.dumps({"expected": len(out), "plotted": len(pts),
                    "recommended_zone_count": recommended,
                    "breaks": [round(b, 3) for b in rec_breaks], "points": pts},
                   ensure_ascii=False), encoding="utf-8", newline="\n")


def _write_index(out):
    idx = []
    for r in out:
        if not isinstance(r["lon"], (int, float)):
            continue
        idx.append([r["address"], round(r["lon"], 5), round(r["lat"], 5),
                    r["internal_zone"] if r["status"] == "routed" else 0,
                    r["reference_price"] if r["status"] == "routed" else None, r["status"]])
    (RD / "address-index.json").write_text(
        json.dumps({"addresses": idx}, ensure_ascii=False), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
