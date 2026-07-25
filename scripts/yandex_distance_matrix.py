#!/usr/bin/env python
"""Yandex-first routing audit — Distance Matrix client, license gate and pilot.

Distance and duration from ONE fixed central origin to each exact verified
address, using ONLY the official Yandex Distance Matrix API. The yandex.ru/maps
web interface is never scraped.

FAIL-CLOSED PREREQUISITES. Results are stored and used to build delivery zones,
so a licence that PERMITS STORING results is required. Both of these must be
present or nothing is requested:

  * `YANDEX_API_KEY`
  * a storage-licence attestation: `YANDEX_LICENSE_ALLOWS_STORAGE=true` plus
    `YANDEX_LICENSE_REF=<contract / tariff reference>`, or the same two fields in
    `config/yandex-license.json`.

The free/basic Yandex Maps API tariff forbids storing or caching results, so it
cannot be used for zoning. Only the owner can confirm the contract — this script
never assumes it.

Other guarantees: no fabricated values ever; a Yandex error is NEVER silently
replaced by OSRM; `unreachable` becomes OWNER_REVIEW and never an automatic Zone
4; Yandex vs OSRM divergence above 10 % is ROUTER_DISAGREEMENT_OWNER_REVIEW. No
release, zone, Direct or price is changed.
"""

from __future__ import annotations

import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage09_engine import nearest_osm_place  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
D = REPO / "docs/data"
RPT = REPO / "reports/yandex-routing"
REGISTRY = REPO / "releases/bender-zones-v1.1/address-registry.json"
POINTS = REPO / "docs/data/final-address-zone-points.geojson"
LICENSE_FILE = REPO / "config/yandex-license.json"

ENDPOINT = "https://api.routing.yandex.net/v2/distancematrix"
ORIGIN_LAT, ORIGIN_LON = 46.82388, 29.48313        # fixed central origin
MAX_ELEMENTS_PER_REQUEST = 100                      # 1 origin x <=100 destinations
OSRM = "http://127.0.0.1:5000"
DISAGREE_PCT = 10.0

PILOT_QUOTA = {"Борисовка": 20, "Хомутяновка": 20, "Протягайловка": 20,
               "Парканы": 20, "Гиска": 20}

REQUIRED_PRODUCT = (
    "Yandex Maps API — Distance Matrix API, on a COMMERCIAL tariff whose terms "
    "explicitly permit storing/caching results (the free tier forbids storage). "
    "Confirm the exact SKU and the data-retention clause with Yandex before use."
)


# --------------------------------------------------------------------------- #
# prerequisites
# --------------------------------------------------------------------------- #
def license_state() -> dict:
    key = os.environ.get("YANDEX_API_KEY") or None
    allows = os.environ.get("YANDEX_LICENSE_ALLOWS_STORAGE", "").lower() in ("1", "true", "yes")
    ref = os.environ.get("YANDEX_LICENSE_REF") or None
    if LICENSE_FILE.exists():
        try:
            j = json.loads(LICENSE_FILE.read_text("utf-8"))
            allows = allows or bool(j.get("allows_storage"))
            ref = ref or j.get("license_ref")
        except (OSError, json.JSONDecodeError):
            pass
    blockers = []
    if not key:
        blockers.append("YANDEX_API_KEY is not set")
    if not allows:
        blockers.append("storage-permitting licence not attested "
                        "(YANDEX_LICENSE_ALLOWS_STORAGE / config/yandex-license.json)")
    if allows and not ref:
        blockers.append("licence attested but YANDEX_LICENSE_REF (contract/tariff) missing")
    return {"api_key_present": bool(key), "storage_licence_attested": allows,
            "licence_ref": ref, "blockers": blockers, "may_call_api": not blockers,
            "required_product": REQUIRED_PRODUCT}


# --------------------------------------------------------------------------- #
# addresses
# --------------------------------------------------------------------------- #
def load_registry_addresses() -> list[dict]:
    """The 9 216 exact verified addresses, joined to their exact coordinates."""
    reg = json.loads(REGISTRY.read_text("utf-8"))["addresses"]
    pts = {f["properties"]["uid"]: f["geometry"]["coordinates"]
           for f in json.loads(POINTS.read_text("utf-8"))["features"]}
    out = []
    for a in reg:
        c = pts.get(a["uid"])
        if not c:
            continue
        out.append({**a, "lon": c[0], "lat": c[1], "in_verified_registry": True})
    return out


def load_severny() -> list[dict]:
    """Северный addressed points — owner-review, NOT in the verified registry."""
    out = []
    for f in json.loads(POINTS.read_text("utf-8"))["features"]:
        p = f["properties"]
        if p.get("district_ru") == "Северный" and p.get("housenumber"):
            out.append({"uid": p["uid"], "settlement_ru": p["settlement_ru"],
                        "district_ru": "Северный", "street_ru": p["street_ru"],
                        "housenumber": p["housenumber"], "zone_id": p.get("zone_id"),
                        "lon": f["geometry"]["coordinates"][0],
                        "lat": f["geometry"]["coordinates"][1],
                        "in_verified_registry": False})
    return out


def district_of(a: dict) -> str:
    if a.get("district_ru") == "Северный":
        return "Северный"
    if a["settlement_ru"] == "Бендеры":
        return nearest_osm_place(a["lat"], a["lon"])[0]
    return a["settlement_ru"]


def pilot_selection() -> list[dict]:
    addrs = load_registry_addresses()
    for a in addrs:
        a["_district"] = district_of(a)
    picked, seen = [], set()
    for d, n in PILOT_QUOTA.items():
        sub = [a for a in addrs if a["_district"] == d]
        step = max(1, len(sub) // n) if sub else 1
        for a in sub[::step][:n]:
            if a["uid"] not in seen:
                seen.add(a["uid"])
                picked.append(a)
    for s in load_severny():
        s["_district"] = "Северный"
        picked.append(s)
    return picked


# --------------------------------------------------------------------------- #
# Yandex client
# --------------------------------------------------------------------------- #
def batches(dests: list[dict], size: int = MAX_ELEMENTS_PER_REQUEST):
    for i in range(0, len(dests), size):
        yield i // size, dests[i:i + size]


def build_request(dests: list[dict], avoid_tolls: bool = True) -> dict:
    """Exact query we send: one origin, <=100 destinations, driving, no traffic."""
    if len(dests) > MAX_ELEMENTS_PER_REQUEST:
        raise ValueError("more than 100 matrix elements in one synchronous request")
    params = {
        "origins": f"{ORIGIN_LAT},{ORIGIN_LON}",
        "destinations": "|".join(f"{d['lat']},{d['lon']}" for d in dests),
        "mode": "driving",
        # no departure_time -> neutral/static traffic, stable for zoning
        "avoid_tolls": "true" if avoid_tolls else "false",
    }
    return {"url": ENDPOINT, "params": params, "elements": len(dests)}


def call_matrix(dests: list[dict]) -> dict:
    st = license_state()
    req = build_request(dests)
    if not st["may_call_api"]:
        return {"status": "PREREQUISITE_NOT_MET", "blockers": st["blockers"], "request": req}
    q = dict(req["params"], apikey=os.environ["YANDEX_API_KEY"])
    url = f"{ENDPOINT}?{urllib.parse.urlencode(q)}"
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return {"status": "OK", "body": json.loads(r.read().decode("utf-8"))}
    except urllib.error.HTTPError as e:
        return {"status": f"HTTP_{e.code}", "error": e.read().decode("utf-8")[:300]}
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        return {"status": "REQUEST_FAILED", "error": str(e)[:200]}


def osrm_km(lat: float, lon: float) -> float | None:
    url = (f"{OSRM}/route/v1/driving/{ORIGIN_LON:.6f},{ORIGIN_LAT:.6f};"
           f"{lon:.6f},{lat:.6f}?overview=false")
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None
    if d.get("code") != "Ok" or not d.get("routes"):
        return None
    return round(d["routes"][0]["distance"] / 1000, 4)


def verdict(y_km, o_km, y_status: str) -> str:
    if y_status.startswith("PREREQUISITE"):
        return "PENDING_YANDEX_PREREQUISITE"
    if y_status != "OK":
        return "YANDEX_ERROR_OWNER_REVIEW"          # never silently fall back to OSRM
    if y_km is None:
        return "UNREACHABLE_OWNER_REVIEW"           # never an automatic Zone 4
    if o_km is None:
        return "OSRM_MISSING_OWNER_REVIEW"
    pct = abs(y_km - o_km) / y_km * 100.0
    return "ROUTER_DISAGREEMENT_OWNER_REVIEW" if pct > DISAGREE_PCT else "AGREEMENT_WITHIN_10PCT"


COLUMNS = [
    "uid", "settlement", "district", "street", "housenumber",
    "destination_lat", "destination_lon", "yandex_status",
    "distance_meters", "distance_km", "duration_seconds", "duration_minutes",
    "origin_lat", "origin_lon", "request_batch_id", "requested_at",
    "yandex_api_response_status", "unreachable_reason", "current_zone",
    "current_osrm_km", "yandex_minus_osrm_km", "yandex_osrm_ratio",
    "in_verified_registry", "status", "owner_review_required",
]


def run(dests: list[dict], out_csv: str, with_osrm: bool = True) -> list[dict]:
    rows = []
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    for bid, chunk in batches(dests):
        res = call_matrix(chunk)
        body = res.get("body") or {}
        elements = (body.get("rows") or [{}])[0].get("elements") if body else None
        for i, a in enumerate(chunk):
            el = (elements[i] if elements and i < len(elements) else None)
            y_status = res["status"]
            api_status = (el or {}).get("status") if el else ""
            dist_m = ((el or {}).get("distance") or {}).get("value") if el else None
            dur_s = ((el or {}).get("duration") or {}).get("value") if el else None
            y_km = round(dist_m / 1000, 4) if dist_m else None
            o_km = osrm_km(a["lat"], a["lon"]) if with_osrm else None
            rows.append({
                "uid": a["uid"], "settlement": a["settlement_ru"],
                "district": a.get("_district") or district_of(a),
                "street": a["street_ru"], "housenumber": a["housenumber"],
                "destination_lat": a["lat"], "destination_lon": a["lon"],
                "yandex_status": y_status,
                "distance_meters": dist_m, "distance_km": y_km,
                "duration_seconds": dur_s,
                "duration_minutes": round(dur_s / 60, 2) if dur_s else None,
                "origin_lat": ORIGIN_LAT, "origin_lon": ORIGIN_LON,
                "request_batch_id": f"b{bid:03d}", "requested_at": now,
                "yandex_api_response_status": api_status,
                "unreachable_reason": ("" if dist_m else
                                       (api_status or "not requested — prerequisite not met")),
                "current_zone": a.get("zone_id"),
                "current_osrm_km": o_km,
                "yandex_minus_osrm_km": round(y_km - o_km, 4) if (y_km and o_km) else None,
                "yandex_osrm_ratio": round(y_km / o_km, 4) if (y_km and o_km) else None,
                "in_verified_registry": a.get("in_verified_registry", True),
                "status": verdict(y_km, o_km, y_status),
                "owner_review_required": True,
            })
    _csv(out_csv, rows)
    return rows


def _csv(name: str, rows: list[dict], columns=None):
    p = D / name
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns or COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    RPT.mkdir(parents=True, exist_ok=True)
    st = license_state()
    registry = load_registry_addresses()
    pilot = pilot_selection()
    full_batches = (len(registry) + MAX_ELEMENTS_PER_REQUEST - 1) // MAX_ELEMENTS_PER_REQUEST

    plan = {
        "api": "Yandex Distance Matrix API (official) — the web map is never scraped",
        "endpoint": ENDPOINT,
        "origin": {"lat": ORIGIN_LAT, "lon": ORIGIN_LON, "fixed": True},
        "settings": {"mode": "driving", "coordinate_format": "latitude,longitude",
                     "traffic": "neutral/static (no departure_time) for stable zoning",
                     "avoid_tolls": True,
                     "unpaved_or_poor_roads": "NOT excluded — awaiting a separate owner rule"},
        "volume": {"exact_verified_addresses": len(registry), "origins": 1,
                   "destinations": len(registry), "matrix_elements": len(registry),
                   "max_elements_per_sync_request": MAX_ELEMENTS_PER_REQUEST,
                   "full_run_http_requests": full_batches,
                   "pilot_addresses": len(pilot),
                   "pilot_http_requests": (len(pilot) + 99) // 100},
        "prerequisites": st,
        "may_start_pilot": st["may_call_api"],
        "fail_closed": {
            "fabricated_values": "never",
            "yandex_error_falls_back_to_osrm": False,
            "unreachable": "OWNER_REVIEW, never an automatic Zone 4",
            "divergence_gt_10pct": "ROUTER_DISAGREEMENT_OWNER_REVIEW",
        },
        "zones_release_direct_prices_changed": False,
        "owner_review_required": True,
    }
    (D / "yandex-prerequisites.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    # Prepare pilot rows. Without the licence NO Yandex call is made; OSRM
    # baselines are still recorded so the owner sees the comparison skeleton.
    rows = run(pilot, "yandex-pilot-distance-matrix.csv", with_osrm=True)
    _csv("yandex-vs-osrm.csv", rows)
    if not (D / "yandex-full-distance-matrix.csv").exists():
        _csv("yandex-full-distance-matrix.csv", [])

    print(f"YANDEX_API_KEY present:        {st['api_key_present']}")
    print(f"storage licence attested:     {st['storage_licence_attested']}")
    print(f"may call API:                 {st['may_call_api']}")
    print(f"blockers:                     {st['blockers']}")
    print(f"exact verified addresses:     {len(registry)}")
    print(f"full run: {len(registry)} elements -> {full_batches} HTTP requests "
          f"(1 origin x <= {MAX_ELEMENTS_PER_REQUEST} destinations)")
    print(f"pilot: {len(pilot)} addresses -> {(len(pilot) + 99) // 100} requests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
