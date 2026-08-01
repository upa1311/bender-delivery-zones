"""30-address routing pilot — CENTRAL_ORIGIN_ALTERNATIVE_PROVIDER_COMPARISON.

ANALYSIS ONLY. This is NOT a restaurant-specific production pilot.

Canonical route_km was produced by a LOCAL OSRM v26.7.3 engine (car.lua +
endpoint-aware-delivery access profile) over the Moldova PBF (sha256 09ba0c058e89…),
routed from a single CENTRAL REPRESENTATIVE restaurant-cluster origin
29.48313,46.82388 (docs/data/restaurant-origins.geojson, weight 0.85, poi_count 28).
That engine is not runnable here (no PBF, no OSRM binary).

This pilot runs a clearly-labelled comparison: real HTTP requests to the public OSRM
demo (router.project-osrm.org, full-planet car profile) FROM THE SAME central
representative origin to 30 unique canonical external destinations. It does NOT prove
a production delivery price, because production routing must be computed per ORDERING
restaurant (restaurant -> client), and no restaurant registry with coordinates exists
yet (see restaurant-origins-plan-v1.md -> RESTAURANT_ORIGINS_UNAVAILABLE).

Two explicit modes:
  * `--capture`  : NETWORK. Makes the 30 requests, records raw responses + a
                   timestamped attempt log (request_timestamp_utc, attempt number,
                   retries, HTTP status, exact URL).
  * (default)    : OFFLINE REPLAY. No network. Rebuilds every artifact deterministically
                   from committed raw responses + the committed attempt log.
No mass batch is ever run.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FEES = ROOT / "data/interim/outside-city-distance-v1.csv"
ORIGINS = ROOT / "docs/data/restaurant-origins.geojson"
OUT = ROOT / "data/interim/route-pilot"
RAW = OUT / "raw"
RESULTS_CSV = OUT / "route-pilot-results-v1.csv"
ATTEMPTS_CSV = OUT / "route-pilot-attempts-v1.csv"
SUMMARY_JSON = OUT / "route-pilot-summary-v1.json"
REPORT_MD = ROOT / "reports/zone-model-audit/route-generation-pilot-v1.md"

# Exact reproducible request template and parameters (OSRM demo).
URL_TEMPLATE = ("https://router.project-osrm.org/route/v1/driving/"
                "{o_lon},{o_lat};{d_lon},{d_lat}?overview=full&geometries=geojson")
REQUEST_PARAMS = {"overview": "full", "geometries": "geojson", "profile": "driving"}
N_PILOT = 30
CLASSIFICATION = "CENTRAL_ORIGIN_ALTERNATIVE_PROVIDER_COMPARISON"


def _now_utc():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def central_origin():
    data = json.loads(ORIGINS.read_text(encoding="utf-8"))
    for f in data["features"]:
        if f["properties"].get("role") == "central":
            lon, lat = f["geometry"]["coordinates"]
            return lon, lat, f["properties"].get("key")
    raise RuntimeError("central origin not found")


def select(rows):
    """Deterministic 30 unique canonical external addresses spanning the three
    territories, route_km extremes, and both routed and never-routed addresses."""
    routed = [r for r in rows if r.get("route_geometry_source")]
    pool = sorted((r for r in rows if not r.get("route_geometry_source")),
                  key=lambda r: (float(r["route_km"]), r["canonical_address_id"]))
    chosen = {r["canonical_address_id"]: r for r in routed}

    def add(r):
        chosen.setdefault(r["canonical_address_id"], r)
    for r in pool[:4]:
        add(r)
    for r in pool[-4:]:
        add(r)
    for terr in ("Парканы", "Гиска", "Протягайловка"):
        trows = [r for r in pool if r["territory"] == terr]
        step = max(1, len(trows) // 4) if trows else 1
        for r in trows[::step]:
            if len(chosen) >= N_PILOT:
                break
            add(r)
    for r in pool:
        if len(chosen) >= N_PILOT:
            break
        add(r)
    return list(chosen.values())[:N_PILOT]


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _url(origin, dest):
    return URL_TEMPLATE.format(o_lon=f"{origin[0]:.6f}", o_lat=f"{origin[1]:.6f}",
                               d_lon=f"{dest[0]:.6f}", d_lat=f"{dest[1]:.6f}")


def capture_one(origin, dest, aid):
    """NETWORK: request with retries; return (raw_bytes, attempt_records)."""
    url = _url(origin, dest)
    attempts = []
    for attempt in range(1, 5):
        ts = _now_utc()
        try:
            b = urllib.request.urlopen(  # noqa: S310
                urllib.request.Request(url, headers={"User-Agent": "bdz-pilot"}),
                timeout=40).read()
            obj = json.loads(b)
            pretty = json.dumps(obj, ensure_ascii=False, indent=2,
                                sort_keys=True).encode("utf-8")
            RAW.mkdir(parents=True, exist_ok=True)
            (RAW / f"{aid}.osrm.json").write_bytes(pretty)
            attempts.append({"canonical_address_id": aid, "request_timestamp_utc": ts,
                             "attempt_number": attempt, "mode": "network_capture",
                             "http_status": obj.get("code", "Ok"), "url": url})
            return pretty, attempts
        except Exception as e:  # noqa: BLE001
            attempts.append({"canonical_address_id": aid, "request_timestamp_utc": ts,
                             "attempt_number": attempt, "mode": "network_capture",
                             "http_status": f"error:{type(e).__name__}", "url": url})
            time.sleep(8 * attempt)
    return None, attempts


def load_attempt_log():
    if not ATTEMPTS_CSV.exists():
        return {}
    log = {}
    for r in csv.DictReader(ATTEMPTS_CSV.open(encoding="utf-8-sig")):
        log.setdefault(r["canonical_address_id"], []).append(r)
    return log


def main():
    capture = "--capture" in sys.argv
    rows = [r for r in csv.DictReader(FEES.open(encoding="utf-8-sig")) if r["latitude"]]
    olon, olat, okey = central_origin()
    picks = select(rows)
    assert len({r["canonical_address_id"] for r in picks}) == N_PILOT, "need 30 unique"

    prior_log = load_attempt_log()
    all_attempts, results, ok, fail = [], [], 0, 0
    for r in picks:
        aid = r["canonical_address_id"]
        dest = (float(r["longitude"]), float(r["latitude"]))
        url = _url((olon, olat), dest)
        raw_path = RAW / f"{aid}.osrm.json"
        if capture:
            raw, attempts = capture_one((olon, olat), dest, aid)
            all_attempts.extend(attempts)
            mode = "network_capture"
            att_meta = attempts[-1] if attempts else {}
            ts = att_meta.get("request_timestamp_utc", "")
            attempt_no = att_meta.get("attempt_number", len(attempts))
            retry_count = max(0, len(attempts) - 1)
        else:  # offline replay
            raw = raw_path.read_bytes() if raw_path.exists() else None
            logged = prior_log.get(aid, [])
            all_attempts.extend(logged)
            mode = "cache_replay"
            last = logged[-1] if logged else {}
            ts = last.get("request_timestamp_utc", "")
            attempt_no = last.get("attempt_number", "")
            retry_count = max(0, len(logged) - 1)
        rec = {
            "canonical_address_id": aid, "route_id": f"route_{aid}",
            "address": r.get("address", ""), "territory": r["territory"],
            "origin_key": okey, "origin_lon": olon, "origin_lat": olat,
            "dest_lon": dest[0], "dest_lat": dest[1],
            "provider": "OSRM demo router.project-osrm.org (ALTERNATIVE_PROVIDER)",
            "profile": "driving (full-planet OSM car) — NOT canonical car.lua",
            "request_url": url, "request_params": json.dumps(REQUEST_PARAMS),
            "request_timestamp_utc": ts, "attempt_number": attempt_no,
            "retry_count": retry_count, "mode": mode,
            "canonical_route_km": float(r["route_km"]),
            "had_prior_polyline": bool(r.get("route_geometry_source")),
            "raw_response_path": raw_path.relative_to(ROOT).as_posix(),
        }
        if raw is not None:
            obj = json.loads(raw)
            if obj.get("code") == "Ok" and obj.get("routes"):
                rt = obj["routes"][0]
                length_km = rt["distance"] / 1000.0
                geom = json.dumps(rt["geometry"], sort_keys=True).encode("utf-8")
                diff = length_km - rec["canonical_route_km"]
                rec.update({
                    "http_result": "Ok", "raw_sha256": _sha(raw),
                    "geometry_sha256": _sha(geom),
                    "alt_provider_length_km": round(length_km, 4),
                    "abs_diff_km": round(abs(diff), 4),
                    "pct_diff": round(100 * diff / rec["canonical_route_km"], 2),
                    "validation_status": "ALT_PROVIDER_COMPARISON_ONLY"})
                ok += 1
            else:
                rec.update({"http_result": obj.get("code", "NoRoute"),
                            "raw_sha256": _sha(raw), "validation_status": "NO_ROUTE"})
                fail += 1
        else:
            rec.update({"http_result": "no_raw_response",
                        "validation_status": "RAW_UNAVAILABLE"})
            fail += 1
        results.append(rec)

    # attempt log: written on capture; on replay it must already exist (never faked)
    if capture:
        ah = sorted({k for a in all_attempts for k in a})
        with ATTEMPTS_CSV.open("w", encoding="utf-8", newline="") as h:
            w = csv.DictWriter(h, fieldnames=ah, lineterminator="\n")
            w.writeheader()
            w.writerows(all_attempts)

    header = sorted({k for r in results for k in r})
    with RESULTS_CSV.open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=header, lineterminator="\n")
        w.writeheader()
        w.writerows(results)

    diffs = [r["abs_diff_km"] for r in results if "abs_diff_km" in r]
    have_ts = sum(1 for r in results if r["request_timestamp_utc"])
    summary = {
        "classification": CLASSIFICATION,
        "restaurant_specific_production_pilot": False,
        "provider_label": "ALTERNATIVE_PROVIDER_COMPARISON",
        "url_template": URL_TEMPLATE, "request_params": REQUEST_PARAMS,
        "canonical_provider": "local OSRM v26.7.3 car.lua + moldova PBF "
                              "09ba0c058e89… (NOT reproducible in this checkout)",
        "canonical_origin": {"key": okey, "lon": olon, "lat": olat,
                             "note": "single CENTRAL REPRESENTATIVE restaurant-cluster "
                                     "origin (weight 0.85, poi_count 28) — NOT a "
                                     "specific ordering restaurant"},
        "attempted": len(results), "succeeded": ok, "failed": fail,
        "unique_addresses": len({r["canonical_address_id"] for r in results}),
        "had_prior_polyline": sum(1 for r in results if r["had_prior_polyline"]),
        "never_routed_before": sum(1 for r in results if not r["had_prior_polyline"]),
        "abs_diff_km_min": min(diffs) if diffs else None,
        "abs_diff_km_max": max(diffs) if diffs else None,
        "abs_diff_km_mean": round(sum(diffs) / len(diffs), 4) if diffs else None,
        "attempt_metadata_available": have_ts == len(results),
        "attempt_metadata_note": ("timestamps + attempt history captured over the "
                                  "network and committed to route-pilot-attempts-v1.csv"
                                  if have_ts == len(results)
                                  else "HISTORICAL_ATTEMPT_METADATA_UNAVAILABLE — run "
                                       "with --capture to record it"),
        "mode": "network_capture" if capture else "cache_replay",
        "pilot_ids": [r["canonical_address_id"] for r in results],
    }
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                            encoding="utf-8", newline="\n")
    _write_report(summary)
    print(json.dumps({k: summary[k] for k in
                      ("classification", "attempted", "succeeded", "failed",
                       "never_routed_before", "abs_diff_km_mean",
                       "attempt_metadata_available", "mode")}, ensure_ascii=False))


def _write_report(s):
    dest = 4350  # canonical external destinations
    lines = [
        f"# Route generation pilot v1 — {s['classification']}", "",
        "**This is NOT a restaurant-specific production pilot.**", "",
        "## Canonical provider (proven from repo, NOT reproducible here)", "",
        "- Engine: **local OSRM v26.7.3**, car.lua + `endpoint-aware-delivery` access "
        "profile (docs/data/stage10c-osrm-build-manifest.json).",
        "- Graph: **moldova-latest.osm.pbf** sha256 `09ba0c058e89…` "
        "(reports/stage-01/source-audit.md).",
        f"- Origin: **{s['canonical_origin']['key']}** "
        f"{s['canonical_origin']['lon']},{s['canonical_origin']['lat']} — "
        f"{s['canonical_origin']['note']}.",
        "- The PBF (100 MB, gitignored) and the OSRM binary are absent here, so the "
        "canonical engine cannot be run.", "",
        "## Central-origin limitation (critical)", "",
        "Canonical route_km and this pilot both route from ONE central representative "
        "origin. That is fine for testing the routing engine and reproducibility, but "
        "it does **NOT** prove a production delivery price. A real order's price must "
        "be routed **ordering restaurant → client address**. Restaurant coordinates "
        "are not yet provided/confirmed (see `restaurant-origins-plan-v1.md` → "
        "`RESTAURANT_ORIGINS_UNAVAILABLE`). Mass route generation is blocked until a "
        "restaurant registry and an owner decision exist.", "",
        "## What this pilot actually did", "",
        "- Provider: OSRM demo (router.project-osrm.org), full-planet car profile.",
        f"- URL template: `{s['url_template']}`; params: `{json.dumps(s['request_params'])}`.",
        f"- Mode of this run: **{s['mode']}** (network_capture records timestamps; "
        "cache_replay rebuilds offline from committed raw + attempt log).",
        f"- **{s['attempted']} requests**, **{s['succeeded']}** OK, **{s['failed']}** "
        f"failed, over **{s['unique_addresses']} unique** destinations "
        f"({s['never_routed_before']} never routed before).",
        f"- Attempt metadata (timestamp/attempt/retries/URL) per request: "
        f"`{s['attempt_metadata_note']}`.",
        "- Raw responses + sha256 under `data/interim/route-pilot/raw/`; attempt log "
        "in `route-pilot-attempts-v1.csv`; per-request provenance in "
        "`route-pilot-results-v1.csv`.", "",
        "## Alt-provider length vs canonical route_km", "",
        f"- |diff| km: min **{s['abs_diff_km_min']}**, mean **{s['abs_diff_km_mean']}**, "
        f"max **{s['abs_diff_km_max']}**. Differences are expected (different "
        "graph/profile/snapshot); they are NOT production distances and must not "
        "replace canonical route_km. Silent provider substitution is forbidden.", "",
        "## Full-batch scope (correct formula)", "",
        "Production routing is per ordering restaurant, so the batch size is:", "",
        "```",
        "total_routes = active_restaurant_origins × canonical_delivery_destinations",
        "```", "",
        f"With {dest} canonical external destinations (city addresses add more):", "",
        "| restaurants | routes | local OSRM time* | storage** |",
        "|---:|---:|---|---|",
        f"| 1 | {dest:,} | seconds–1 min | ~tens of MB |",
        f"| 5 | {5*dest:,} | ~minutes | ~hundreds of MB |",
        f"| 10 | {10*dest:,} | ~minutes | ~hundreds of MB |",
        "",
        "*Local OSRM `/route`: free, no API cost, no rate limit; time dominated by "
        "engine setup, not per-request. **Raw + geometry per route, gzip-friendly. "
        "Actual restaurant count is UNKNOWN — no registry (see plan). Caching key: "
        "`(restaurant_id, canonical_address_id, graph_version)`; resumable by skipping "
        "existing cache entries. Expected failures/retries: near-zero locally.", "",
        "**No full batch was run.** It is blocked until a restaurant registry and "
        "owner permission exist.", "",
        "## Pilot address ids", "", "`" + ", ".join(s["pilot_ids"]) + "`", "",
    ]
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
