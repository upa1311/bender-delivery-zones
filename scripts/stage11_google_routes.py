#!/usr/bin/env python
"""Stage 11 — Google Routes API as the PRIMARY routing oracle (OSRM = QA/fallback).

Google Routes v2 `computeRoutes` becomes the authority for distance/duration;
the local OSRM graph and our own edge-valid graph are demoted to QA and fallback.

Per request we ask for and record:
  DEFAULT_ROUTE and the SHORTER_DISTANCE reference route, distanceMeters,
  duration, staticDuration, the encoded polyline, routeLabels, warnings and
  fallbackInfo.

Routing preference:
  * zone computation  -> TRAFFIC_UNAWARE
  * a real live order -> TRAFFIC_AWARE_OPTIMAL
travelMode is DRIVE in both cases.

TERMS-OF-SERVICE GUARD. Google polylines are Google content: they are written
ONLY to a git-ignored cache (`data/interim/google-cache/`) and are NEVER placed in
`docs/` (the public map) or in any release. The published comparison carries
distances, durations, labels and warnings only. `assert_no_google_polyline_in_public()`
enforces this and is covered by a test.

Without GOOGLE_MAPS_API_KEY nothing is invented: the script emits the exact
prepared request payloads plus status `GOOGLE_API_KEY_MISSING`, and no distance,
duration or verdict is fabricated. Zones are NOT changed by this stage.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage09_engine import load_address_points, nearest_osm_place  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
D = REPO / "docs/data"
CACHE = REPO / "data/interim/google-cache"        # git-ignored: Google content
ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"
CENTRAL = (46.82388, 29.48313)                     # (lat, lon)
OSRM = "http://127.0.0.1:5000"
DISAGREEMENT_PCT = 10.0

FIELD_MASK = ",".join([
    "routes.distanceMeters", "routes.duration", "routes.staticDuration",
    "routes.polyline.encodedPolyline", "routes.routeLabels", "routes.warnings",
    "routes.description", "fallbackInfo",
])


def build_payload(origin_latlon, dest_latlon, routing_preference: str) -> dict:
    """Exactly what we send to Google — printed even when no key is configured."""
    return {
        "origin": {"location": {"latLng": {"latitude": origin_latlon[0],
                                           "longitude": origin_latlon[1]}}},
        "destination": {"location": {"latLng": {"latitude": dest_latlon[0],
                                                "longitude": dest_latlon[1]}}},
        "travelMode": "DRIVE",
        "routingPreference": routing_preference,
        "requestedReferenceRoutes": ["SHORTER_DISTANCE"],
        "computeAlternativeRoutes": False,
        "languageCode": "ru",
        "units": "METRIC",
    }


def api_key() -> str | None:
    return os.environ.get("GOOGLE_MAPS_API_KEY") or None


def _cache_path(payload: dict) -> Path:
    h = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]
    return CACHE / f"{h}.json"


def compute_routes(origin_latlon, dest_latlon,
                   routing_preference: str = "TRAFFIC_UNAWARE") -> dict:
    """Call Google Routes. Returns {'status': ..., ...}; never invents a result."""
    payload = build_payload(origin_latlon, dest_latlon, routing_preference)
    key = api_key()
    if not key:
        return {"status": "GOOGLE_API_KEY_MISSING", "payload": payload}
    CACHE.mkdir(parents=True, exist_ok=True)
    cp = _cache_path(payload)
    if cp.exists():
        return {"status": "OK_CACHED", **json.loads(cp.read_text("utf-8"))}
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Goog-Api-Key": key,
                 "X-Goog-FieldMask": FIELD_MASK}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"status": f"HTTP_{e.code}", "error": e.read().decode("utf-8")[:400],
                "payload": payload}
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        return {"status": "REQUEST_FAILED", "error": str(e)[:200], "payload": payload}
    cp.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8", newline="\n")
    return {"status": "OK", **body}


def parse_routes(body: dict) -> dict:
    """Split DEFAULT_ROUTE vs SHORTER_DISTANCE; keep the polyline OUT of public data."""
    out = {"default": None, "shorter_distance": None,
           "fallbackInfo": body.get("fallbackInfo"), "warnings": []}
    for r in body.get("routes", []):
        labels = r.get("routeLabels") or []
        rec = {
            "distance_m": r.get("distanceMeters"),
            "duration_s": _secs(r.get("duration")),
            "static_duration_s": _secs(r.get("staticDuration")),
            "route_labels": ",".join(labels),
            "_polyline": (r.get("polyline") or {}).get("encodedPolyline"),  # cache only
        }
        out["warnings"].extend(r.get("warnings") or [])
        if "SHORTER_DISTANCE" in labels:
            out["shorter_distance"] = rec
        else:
            out["default"] = out["default"] or rec
    return out


def _secs(v):
    if not v:
        return None
    try:
        return float(str(v).rstrip("s"))
    except ValueError:
        return None


def osrm_route(origin_latlon, dest_latlon):
    url = (f"{OSRM}/route/v1/driving/{origin_latlon[1]:.6f},{origin_latlon[0]:.6f};"
           f"{dest_latlon[1]:.6f},{dest_latlon[0]:.6f}?overview=false")
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            d = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None
    if d.get("code") != "Ok" or not d.get("routes"):
        return None
    return {"distance_m": d["routes"][0]["distance"], "duration_s": d["routes"][0]["duration"]}


def disagreement(google_m, osrm_m) -> tuple[float | None, str]:
    if not google_m or not osrm_m:
        return None, "PENDING_GOOGLE"
    pct = abs(google_m - osrm_m) / google_m * 100.0
    return round(pct, 2), ("ROUTER_DISAGREEMENT_OWNER_REVIEW" if pct > DISAGREEMENT_PCT
                           else "AGREEMENT_WITHIN_10PCT")


def assert_no_google_polyline_in_public() -> list[str]:
    """ToS guard: no Google polyline DATA may appear under docs/ or releases/.

    Naming the field in a request field mask is not Google content, so the
    field-mask token is stripped before the search; what is forbidden is an
    actual encoded-polyline value.
    """
    bad = []
    for root in (REPO / "docs", REPO / "releases"):
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.is_dir() or p.suffix.lower() not in (".json", ".csv", ".geojson", ".html"):
                continue
            try:
                txt = p.read_text("utf-8", errors="ignore")
            except OSError:
                continue
            txt = txt.replace("routes.polyline.encodedPolyline", "")   # field-mask token
            if re.search(r'encodedPolyline"?\s*[:=]\s*"[^"]+"', txt) or "google_polyline" in txt:
                bad.append(str(p.relative_to(REPO)))
    return bad


def control_addresses() -> list[dict]:
    pts = [p for p in load_address_points()
           if p["service_status"] in ("standard", "low_density")
           and p["address_status"] == "verified_osm_address"]
    for p in pts:
        p["_d"] = (nearest_osm_place(p["lat"], p["lon"])[0]
                   if p["settlement_ru"] == "Бендеры" else p["settlement_ru"])
        if p.get("district_ru") == "Северный":
            p["_d"] = "Северный"
    out = []
    for d in ("Борисовка", "Хомутяновка", "Протягайловка", "Гиска"):
        sub = [p for p in pts if p["_d"] == d]
        if sub:
            out.append({**sub[len(sub) // 2], "_slot": f"{d}"})
    sev = [p for p in pts if p["_d"] == "Северный"]
    if sev:
        out.append({**sev[0], "_slot": "Северный"})
    park = sorted([p for p in pts if p["settlement_ru"] == "Парканы"],
                  key=lambda p: p.get("expected_km") or 0)
    for slot, idx in (("Парканы:начало", 0), ("Парканы:середина", len(park) // 2),
                      ("Парканы:конец", len(park) - 1)):
        if park:
            out.append({**park[idx], "_slot": slot})
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    key_present = bool(api_key())
    controls = control_addresses()
    rows, payloads = [], []
    for a in controls:
        dest = (a["lat"], a["lon"])
        g = compute_routes(CENTRAL, dest, "TRAFFIC_UNAWARE")
        o = osrm_route(CENTRAL, dest)
        parsed = parse_routes(g) if g["status"].startswith("OK") else {
            "default": None, "shorter_distance": None, "fallbackInfo": None, "warnings": []}
        payloads.append({"slot": a["_slot"], "zone_request": build_payload(
            CENTRAL, dest, "TRAFFIC_UNAWARE"), "live_order_request": build_payload(
            CENTRAL, dest, "TRAFFIC_AWARE_OPTIMAL")})
        gd = (parsed["default"] or {}).get("distance_m")
        gs = (parsed["shorter_distance"] or {}).get("distance_m")
        pct, verdict = disagreement(gd, o["distance_m"] if o else None)
        rows.append({
            "slot": a["_slot"], "district": a["_d"], "street": a["street_ru"],
            "house": a["housenumber"], "lat": a["lat"], "lon": a["lon"],
            "google_status": g["status"],
            "google_default_distance_m": gd,
            "google_default_duration_s": (parsed["default"] or {}).get("duration_s"),
            "google_default_static_duration_s": (parsed["default"] or {}).get("static_duration_s"),
            "google_default_labels": (parsed["default"] or {}).get("route_labels"),
            "google_shorter_distance_m": gs,
            "google_shorter_duration_s": (parsed["shorter_distance"] or {}).get("duration_s"),
            "google_shorter_vs_default_m": (gd - gs) if (gd and gs) else None,
            "google_warnings": ";".join(str(w) for w in parsed["warnings"])[:200],
            "google_fallback_info": json.dumps(parsed["fallbackInfo"], ensure_ascii=False)
            if parsed["fallbackInfo"] else "",
            "osrm_distance_m": o["distance_m"] if o else None,
            "osrm_duration_s": o["duration_s"] if o else None,
            "distance_diff_pct": pct,
            "status": verdict,
            "routing_preference_zones": "TRAFFIC_UNAWARE",
            "routing_preference_live_order": "TRAFFIC_AWARE_OPTIMAL",
            "polyline_stored": "google-cache only (never in docs/ or releases/)",
            "owner_review_required": True,
        })

    _csv("stage11-google-vs-osrm-control-routes.csv", rows)
    leaks = assert_no_google_polyline_in_public()
    status = {
        "oracle": "Google Routes API v2 computeRoutes (PRIMARY)",
        "qa_fallback": "local OSRM + own edge-valid graph (Stage 10D)",
        "google_api_key_present": key_present,
        "run_status": "EXECUTED" if key_present else "NOT_RUN_GOOGLE_API_KEY_MISSING",
        "control_routes_prepared": len(rows),
        "field_mask": FIELD_MASK,
        "routing_preference": {"zone_computation": "TRAFFIC_UNAWARE",
                               "live_order": "TRAFFIC_AWARE_OPTIMAL"},
        "requested_reference_routes": ["SHORTER_DISTANCE"],
        "disagreement_rule": f">{DISAGREEMENT_PCT}% distance -> ROUTER_DISAGREEMENT_OWNER_REVIEW",
        "terms_of_service": {
            "polyline_storage": "git-ignored data/interim/google-cache only",
            "public_docs_or_release_polylines": leaks,
            "guard_ok": not leaks,
            "note": "Google polylines are NOT copied into the public release or any "
                    "non-Google map without a separate Google Maps Platform terms review",
        },
        "zones_changed": False,
        "owner_action_needed": None if key_present else
        "export GOOGLE_MAPS_API_KEY and re-run scripts/stage11_google_routes.py",
        "owner_review_required": True,
    }
    (D / "stage11-google-oracle-status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    (REPO / "data/interim/stage11-prepared-requests.json").write_text(
        json.dumps(payloads, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    print(f"google key present: {key_present} -> {status['run_status']}")
    print(f"control routes: {len(rows)}  (ToS guard ok: {not leaks})")
    for r in rows:
        print(f"  {r['slot']:18s} google={r['google_status']:24s} "
              f"osrm_m={r['osrm_distance_m']} status={r['status']}")
    return 0


def _csv(name, rows):
    p = D / name
    if not rows:
        p.write_text("", encoding="utf-8")
        return
    cols = sorted({k for r in rows for k in r})
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
