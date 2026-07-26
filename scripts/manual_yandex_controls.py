#!/usr/bin/env python
"""Manual Yandex route controls — selection, template and calibration.

The free Yandex Maps web interface is used ONLY as a MANUAL control source. This
script never opens, scrapes or automates yandex.ru/maps: it selects WHICH routes a
human should check, emits a fill-in template, and — once the measurements are
typed in — calibrates our own engine against them.

Nothing from Yandex except the numbers and road names a human typed in is stored:
no polylines, no tiles, no map images, no HTML.

Modes:
  prepare    (default) choose control points, pre-fill everything we can compute
  calibrate            read the filled template, compare against OSRM/our engine,
                       build the confirmed-entry catalogue and flag disagreements

No zone, release, Direct or price is changed.
"""

from __future__ import annotations

import csv
import json
import math
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage09_engine import nearest_osm_place  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
D = REPO / "docs/data"
RPT = REPO / "reports/manual-yandex-routing"
TEMPLATE = D / "manual-yandex-route-controls.csv"
POINTS = D / "final-address-zone-points.geojson"
ENTRIES = D / "stage-09b-district-entries.csv"

ORIGIN_LAT, ORIGIN_LON = 46.82388, 29.48313
OSRM = "http://127.0.0.1:5000"
ZONE_EDGES = {"Zone2/3": 4.076, "Zone3/4": 5.577}
DISAGREE_PCT = 10.0

# Owner-named landmarks, coordinates resolved from the local OSM extract.
LANDMARKS = {
    "Хомутяновка": [
        ("Пивзавод", 46.80124, 29.47681),
        ("Молдплодовощ", 46.80370, 29.48024),
        ("Роддом", 46.81270, 29.45875),
        ("Городская больница", 46.81597, 29.45932),
    ],
}
# Owner-named streets that MUST appear as controls per district.
REQUIRED_STREETS = {
    "Хомутяновка": ["улица Ечина", "улица Бориса Главана", "улица Старого",
                    "Московская улица", "Первомайская улица", "улица Некрасова"],
    "Протягайловка": ["улица Старого", "улица Мира"],
    "Гиска": [],
    "Парканы": [],
    "Северный": [],
}
DISTRICTS = ["Хомутяновка", "Протягайловка", "Гиска", "Парканы", "Северный"]

COLUMNS = [
    # identity — pre-filled
    "control_id", "uid", "district", "target_district", "street", "housenumber",
    "destination_lat", "destination_lon", "control_reason",
    # what a human types in from the Yandex web interface
    "checked_date", "yandex_fastest_distance_km", "yandex_fastest_duration_min",
    "yandex_alternative_distance_km", "yandex_alternative_duration_min",
    "yandex_main_streets", "yandex_district_entry", "yandex_rail_crossing_or_bridge",
    "matches_owner_corridor",
    # our side — pre-filled
    "current_zone", "current_osrm_km", "our_engine_km", "expected_entry_our_engine",
    # computed on calibrate
    "yandex_minus_osrm_km", "yandex_osrm_ratio", "calibration_status",
    "owner_review_required",
]

YANDEX_INPUT_COLUMNS = [
    "checked_date", "yandex_fastest_distance_km", "yandex_fastest_duration_min",
    "yandex_alternative_distance_km", "yandex_alternative_duration_min",
    "yandex_main_streets", "yandex_district_entry", "yandex_rail_crossing_or_bridge",
    "matches_owner_corridor",
]


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def osrm_km(lat, lon):
    url = (f"{OSRM}/route/v1/driving/{ORIGIN_LON:.6f},{ORIGIN_LAT:.6f};"
           f"{lon:.6f},{lat:.6f}?overview=false")
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    if d.get("code") != "Ok" or not d.get("routes"):
        return None
    return round(d["routes"][0]["distance"] / 1000, 4)


def verified_points() -> list[dict]:
    out = []
    for f in json.loads(POINTS.read_text("utf-8"))["features"]:
        p = f["properties"]
        if p.get("address_status") != "verified_osm_address":
            continue
        if p.get("service_status") not in ("standard", "low_density"):
            continue
        if not p.get("housenumber"):
            continue
        lon, lat = f["geometry"]["coordinates"]
        d = ("Северный" if p.get("district_ru") == "Северный"
             else (nearest_osm_place(lat, lon)[0] if p["settlement_ru"] == "Бендеры"
                   else p["settlement_ru"]))
        out.append({"uid": p["uid"], "district": d, "street": p.get("street_ru") or "",
                    "house": p["housenumber"], "lat": lat, "lon": lon,
                    "zone": p.get("zone_id"), "expected_km": p.get("expected_km")})
    return out


def district_entries() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    if not ENTRIES.exists():
        return out
    for r in csv.DictReader(ENTRIES.open(encoding="utf-8")):
        if r.get("connected_to_city_graph") != "True" or not r.get("entry_lon"):
            continue
        out.setdefault(r["district_or_settlement"], []).append(r)
    return out


def street_midpoint(name: str):
    """Midpoint of an OSM street, for a mandatory control street that carries no
    verified addressed house. Read from the cached Stage 10D graph."""
    try:
        from stage10d_graph import Graph
        g = Graph.load()
    except Exception:
        return None
    seg = [i for i, ph in enumerate(g.phys)
           if (g.way_tags.get(ph[3], {}).get("name") or "") == name]
    if not seg:
        return None
    u = g.phys[seg[len(seg) // 2]][0]
    return g.coords[u]


def nearest_point(pts, lat, lon, max_km=0.6):
    best, bd = None, max_km
    for p in pts:
        d = haversine_km(lat, lon, p["lat"], p["lon"])
        if d < bd:
            best, bd = p, d
    return best


def select_controls() -> list[dict]:
    pts = verified_points()
    entries = district_entries()
    picked: dict[str, dict] = {}

    def add(p, reason, target=None):
        """`target` is the district the control BELONGS TO for the owner, which can
        differ from the district our labeller computed (an owner-named approach
        street may sit in a neighbouring place)."""
        if not p:
            return
        key = p["uid"]
        if key in picked:
            if reason not in picked[key]["control_reason"]:
                picked[key]["control_reason"] += f"; {reason}"
            return
        picked[key] = {**p, "control_reason": reason,
                       "target_district": target or p["district"]}

    for d in DISTRICTS:
        sub = [p for p in pts if p["district"] == d]
        if not sub:
            continue
        if d == "Северный":
            for p in sub:                     # all 7 exact addresses
                add(p, "Северный: все известные точные адреса")
            continue
        sub.sort(key=lambda p: p.get("expected_km") or haversine_km(
            ORIGIN_LAT, ORIGIN_LON, p["lat"], p["lon"]))
        for p in sub[:3]:
            add(p, "3 ближайших к центру")
        mid = len(sub) // 2
        for p in sub[max(0, mid - 1):mid + 2]:
            add(p, "3 средних")
        for p in sub[-3:]:
            add(p, "3 самых дальних")
        # near every known entry
        for e in entries.get(d, [])[:8]:
            np_ = nearest_point(sub, float(e["entry_lat"]), float(e["entry_lon"]))
            add(np_, f"дом у въезда {e['entry_id']} ({e.get('road_name') or 'без имени'})")
        # near the current Zone 2/3 and Zone 3/4 boundaries
        for label, edge in ZONE_EDGES.items():
            near = sorted((p for p in sub if p.get("expected_km")),
                          key=lambda p: abs(p["expected_km"] - edge))[:2]
            for p in near:
                add(p, f"граница {label}")
        # owner-named streets
        for st in REQUIRED_STREETS.get(d, []):
            on = [p for p in sub if p["street"] == st]
            for p in on[:2]:
                add(p, f"owner-улица {st}", target=d)
            if not on:
                any_street = [p for p in pts if p["street"] == st]
                for p in any_street[:1]:
                    add(p, f"owner-улица {st} (наш районный ярлык иной)", target=d)
                if not any_street:
                    # A mandatory street with NO verified addressed house (e.g. улица
                    # Ечина is a through-road). It must not be silently dropped: emit a
                    # coordinate-only control on the street itself — the spec allows a
                    # control_id without a uid.
                    mid = street_midpoint(st)
                    if mid:
                        picked[f"street:{st}"] = {
                            "uid": "", "district": d, "street": st, "house": "",
                            "lat": mid[1], "lon": mid[0], "zone": "", "expected_km": None,
                            "control_reason": f"owner-улица {st} (нет подтверждённых домов — "
                                              f"контроль по середине улицы)",
                            "target_district": d}
        # owner landmarks -> nearest verified house
        for name, lat, lon in LANDMARKS.get(d, []):
            add(nearest_point(sub, lat, lon, max_km=1.2) or nearest_point(pts, lat, lon, 1.2),
                f"ориентир {name}", target=d)

    # Borisovka: carry over the control homes already checked in Stage 09C so the
    # manual Yandex pass covers them too (our engine measured them; Yandex has not).
    bori = [p for p in pts if p["district"] == "Борисовка"]
    bori.sort(key=lambda p: p.get("expected_km") or haversine_km(
        ORIGIN_LAT, ORIGIN_LON, p["lat"], p["lon"]))
    if bori:
        for p in (bori[0], bori[len(bori) // 2], bori[-1]):
            add(p, "ранее проверенный контроль Борисовки (Stage 09C)", target="Борисовка")
        kish = [p for p in bori if p["street"] == "Кишинёвская улица" and p["house"] == "1"]
        for p in kish[:1]:
            add(p, "ранее проверенный контроль Борисовки: путепровод", target="Борисовка")
    return list(picked.values())


def prepare() -> int:
    controls = select_controls()
    our = {}
    p10d = D / "stage10d-by-address.csv"
    if p10d.exists():
        for r in csv.DictReader(p10d.open(encoding="utf-8")):
            if r.get("km_10d"):
                our[r["uid"]] = r["km_10d"]
    entries = district_entries()
    rows = []
    for i, c in enumerate(sorted(controls, key=lambda x: (x.get("target_district", x["district"]), x["street"], x["house"])), 1):  # noqa: E501
        ent = entries.get(c["district"], [])
        near_entry = min(ent, key=lambda e: haversine_km(
            c["lat"], c["lon"], float(e["entry_lat"]), float(e["entry_lon"]))) if ent else None
        rows.append({
            "control_id": f"MY-{i:03d}", "uid": c["uid"], "district": c["district"],
            "target_district": c.get("target_district", c["district"]),
            "street": c["street"], "housenumber": c["house"],
            "destination_lat": c["lat"], "destination_lon": c["lon"],
            "control_reason": c["control_reason"],
            **{k: "" for k in YANDEX_INPUT_COLUMNS},
            "current_zone": c["zone"], "current_osrm_km": osrm_km(c["lat"], c["lon"]),
            "our_engine_km": our.get(c["uid"], ""),
            "expected_entry_our_engine": (f"{near_entry['entry_id']} "
                                          f"{near_entry.get('road_name') or ''}".strip()
                                          if near_entry else ""),
            "yandex_minus_osrm_km": "", "yandex_osrm_ratio": "",
            "calibration_status": "AWAITING_MANUAL_YANDEX_MEASUREMENT",
            "owner_review_required": True,
        })
    _write(rows)
    from collections import Counter
    print(f"control routes prepared: {len(rows)}")
    for k, v in sorted(Counter(r["district"] for r in rows).items()):
        print(f"  {k:16s} {v}")
    return 0


def calibrate() -> int:
    if not TEMPLATE.exists():
        print("template missing — run prepare first")
        return 1
    rows = list(csv.DictReader(TEMPLATE.open(encoding="utf-8")))
    filled = 0
    confirmed_entries: dict[tuple, int] = {}
    for r in rows:
        y = _f(r.get("yandex_fastest_distance_km"))
        o = _f(r.get("current_osrm_km"))
        if y is None:
            r["calibration_status"] = "AWAITING_MANUAL_YANDEX_MEASUREMENT"
            continue
        filled += 1
        if o:
            r["yandex_minus_osrm_km"] = round(y - o, 4)
            r["yandex_osrm_ratio"] = round(y / o, 4)
            pct = abs(y - o) / y * 100.0
            r["calibration_status"] = ("ENGINE_DISAGREES_WITH_MANUAL_CONTROL"
                                       if pct > DISAGREE_PCT else "ENGINE_MATCHES_MANUAL_CONTROL")
        else:
            r["calibration_status"] = "OSRM_MISSING_OWNER_REVIEW"
        ent = (r.get("yandex_district_entry") or "").strip()
        if ent:
            key = (r["district"], ent)
            confirmed_entries[key] = confirmed_entries.get(key, 0) + 1
    _write(rows)
    cat = [{"district": d, "confirmed_entry": e, "observed_in_controls": n,
            "source": "manual Yandex web control (human-entered road name)",
            "owner_review_required": True}
           for (d, e), n in sorted(confirmed_entries.items())]
    with (D / "manual-yandex-confirmed-entries.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["district", "confirmed_entry",
                                           "observed_in_controls", "source",
                                           "owner_review_required"])
        w.writeheader()
        w.writerows(cat)
    from collections import Counter
    print(f"measurements filled in: {filled}/{len(rows)}")
    print("status:", dict(Counter(r["calibration_status"] for r in rows)))
    print(f"confirmed entries catalogued: {len(cat)}")
    return 0


def _f(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _write(rows):
    with TEMPLATE.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    RPT.mkdir(parents=True, exist_ok=True)
    mode = sys.argv[1] if len(sys.argv) > 1 else "prepare"
    return calibrate() if mode == "calibrate" else prepare()


if __name__ == "__main__":
    raise SystemExit(main())
