"""Real 30-address routing pilot — ALTERNATIVE_PROVIDER_COMPARISON, ANALYSIS ONLY.

The CANONICAL route_km was produced by a LOCAL OSRM v26.7.3 engine (car.lua +
endpoint-aware-delivery access profile) over the Moldova PBF
(sha256 09ba0c058e89…), routed from the confirmed CENTRAL restaurant origin
29.48313,46.82388 (docs/data/restaurant-origins.geojson, weight 0.85). That engine
is NOT runnable in this checkout (no PBF, no OSRM binary), so the canonical provider
cannot be reproduced here.

This pilot therefore runs a clearly-labelled ALTERNATIVE_PROVIDER_COMPARISON: 30
real HTTP requests to the public OSRM demo (router.project-osrm.org, full-planet
car profile) FROM THE SAME PROVEN CENTRAL ORIGIN to 30 unique canonical external
destinations. It saves every raw response + sha256, extracts the geometry + length,
and compares to canonical route_km. Because the demo uses a different graph/profile/
snapshot, its lengths CANNOT be accepted into production — they only bound how far a
generic car route sits from the canonical delivery route. No mass batch is run.

Reproducible & resumable: raw responses cache under data/interim/route-pilot/raw and
are reused without network. Rate-limited with in-process backoff.
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
SUMMARY_CSV = OUT / "route-pilot-results-v1.csv"
SUMMARY_JSON = OUT / "route-pilot-summary-v1.json"
REPORT_MD = ROOT / "reports/zone-model-audit/route-generation-pilot-v1.md"

OSRM_DEMO = "https://router.project-osrm.org/route/v1/driving/{o};{d}?overview=full&geometries=geojson"
N_PILOT = 30


def central_origin():
    data = json.loads(ORIGINS.read_text(encoding="utf-8"))
    for f in data["features"]:
        if f["properties"].get("role") == "central":
            lon, lat = f["geometry"]["coordinates"]
            return lon, lat, f["properties"].get("key")
    raise RuntimeError("central origin not found")


def select(rows):
    """Deterministically pick 30 unique canonical external addresses spanning the
    three territories, route_km extremes, and both routed (stage-09a/09b) and
    never-before-routed addresses. No randomness (sorted keys only)."""
    routed = [r for r in rows if r.get("route_geometry_source")]  # the 12 with polylines
    pool = sorted((r for r in rows if not r.get("route_geometry_source")),
                  key=lambda r: (float(r["route_km"]), r["canonical_address_id"]))
    chosen = {r["canonical_address_id"]: r for r in routed}  # start with all 12

    def add(r):
        chosen.setdefault(r["canonical_address_id"], r)
    for r in pool[:4]:
        add(r)                      # 4 shortest (near-boundary / near-city)
    for r in pool[-4:]:
        add(r)                      # 4 longest (far anomalies)
    # a few never-routed from EACH territory so all three are represented
    for terr in ("Парканы", "Гиска", "Протягайловка"):
        trows = [r for r in pool if r["territory"] == terr]
        if not trows:
            continue
        step = max(1, len(trows) // 4)
        for r in trows[::step]:
            if len(chosen) >= N_PILOT:
                break
            add(r)
    # top up deterministically if still short
    for r in pool:
        if len(chosen) >= N_PILOT:
            break
        add(r)
    picks = list(chosen.values())[:N_PILOT]
    return picks


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def route_one(origin, dest, aid, refresh):
    raw_path = RAW / f"{aid}.osrm.json"
    if raw_path.exists() and not refresh:
        return raw_path.read_bytes(), "cache"
    url = OSRM_DEMO.format(o=f"{origin[0]:.6f},{origin[1]:.6f}",
                           d=f"{dest[0]:.6f},{dest[1]:.6f}")
    last = None
    for attempt in range(4):
        try:
            b = urllib.request.urlopen(  # noqa: S310
                urllib.request.Request(url, headers={"User-Agent": "bdz-pilot"}),
                timeout=40).read()
            RAW.mkdir(parents=True, exist_ok=True)
            obj = json.loads(b)
            pretty = json.dumps(obj, ensure_ascii=False, indent=2,
                                sort_keys=True).encode("utf-8")
            raw_path.write_bytes(pretty)
            return pretty, "network"
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(8 * (attempt + 1))
    return None, f"error:{type(last).__name__}:{str(last)[:60]}"


def main():
    refresh = "--refresh" in sys.argv
    rows = [r for r in csv.DictReader(FEES.open(encoding="utf-8-sig")) if r["latitude"]]
    olon, olat, okey = central_origin()
    picks = select(rows)
    assert len({r["canonical_address_id"] for r in picks}) == N_PILOT, "need 30 unique"

    results, ok, fail = [], 0, 0
    for r in picks:
        aid = r["canonical_address_id"]
        dest = (float(r["longitude"]), float(r["latitude"]))
        raw, status = route_one((olon, olat), dest, aid, refresh)
        rec = {
            "canonical_address_id": aid, "address": r.get("address", ""),
            "territory": r["territory"],
            "origin_key": okey, "origin_lon": olon, "origin_lat": olat,
            "dest_lon": dest[0], "dest_lat": dest[1],
            "provider": "OSRM demo router.project-osrm.org (ALTERNATIVE_PROVIDER)",
            "profile": "driving (full-planet OSM car) — NOT canonical car.lua",
            "canonical_route_km": float(r["route_km"]),
            "had_prior_polyline": bool(r.get("route_geometry_source")),
            "fetch_status": status,
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
                    "validation_status": "ALT_PROVIDER_COMPARISON_ONLY",
                })
                ok += 1
            else:
                rec.update({"http_result": obj.get("code", "NoRoute"),
                            "raw_sha256": _sha(raw),
                            "validation_status": "NO_ROUTE"})
                fail += 1
        else:
            rec.update({"http_result": status, "validation_status": "REQUEST_FAILED"})
            fail += 1
        results.append(rec)

    header = sorted({k for r in results for k in r})
    with SUMMARY_CSV.open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=header, lineterminator="\n")
        w.writeheader()
        w.writerows(results)

    diffs = [r["abs_diff_km"] for r in results if "abs_diff_km" in r]
    summary = {
        "provider_label": "ALTERNATIVE_PROVIDER_COMPARISON",
        "canonical_provider": "local OSRM v26.7.3 car.lua + moldova PBF "
                              "09ba0c058e89… (NOT reproducible in this checkout)",
        "canonical_origin": {"key": okey, "lon": olon, "lat": olat,
                             "note": "single central restaurant origin, weight 0.85"},
        "attempted": len(results), "succeeded": ok, "failed": fail,
        "unique_addresses": len({r["canonical_address_id"] for r in results}),
        "had_prior_polyline": sum(1 for r in results if r["had_prior_polyline"]),
        "never_routed_before": sum(1 for r in results if not r["had_prior_polyline"]),
        "abs_diff_km_min": min(diffs) if diffs else None,
        "abs_diff_km_max": max(diffs) if diffs else None,
        "abs_diff_km_mean": round(sum(diffs) / len(diffs), 4) if diffs else None,
        "cached": sum(1 for r in results if r["fetch_status"] == "cache"),
        "pilot_ids": [r["canonical_address_id"] for r in results],
    }
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                            encoding="utf-8", newline="\n")
    _write_report(summary, results)
    print(json.dumps({k: summary[k] for k in
                      ("attempted", "succeeded", "failed", "unique_addresses",
                       "never_routed_before", "abs_diff_km_mean")},
                     ensure_ascii=False))


def _write_report(s, results):
    est_full = 4350 - 12  # remaining external without canonical polyline
    lines = [
        "# Route generation pilot v1 — REAL run (ALTERNATIVE_PROVIDER_COMPARISON)", "",
        "## Canonical provider (proven from repo, NOT reproducible here)", "",
        "- Engine: **local OSRM v26.7.3**, car.lua + `endpoint-aware-delivery` access "
        "profile (docs/data/stage10c-osrm-build-manifest.json).",
        "- Graph: **moldova-latest.osm.pbf** sha256 `09ba0c058e89…` "
        "(reports/stage-01/source-audit.md).",
        f"- Origin: **{s['canonical_origin']['key']}** "
        f"{s['canonical_origin']['lon']},{s['canonical_origin']['lat']} — a single "
        "central restaurant origin (weight 0.85), NOT per-restaurant.",
        "- The PBF (100 MB, gitignored) and the OSRM binary are absent in this "
        "checkout, so the canonical engine cannot be run here.", "",
        "## What this pilot actually did", "",
        f"- Provider: **{s['provider_label']}** — public OSRM demo "
        "(router.project-osrm.org), full-planet OSM car profile.",
        f"- **{s['attempted']} real HTTP requests** from the SAME proven central "
        f"origin to **{s['unique_addresses']} unique** canonical external "
        "destinations.",
        f"- Succeeded: **{s['succeeded']}**, failed: **{s['failed']}**, "
        f"served-from-cache on rerun: **{s['cached']}**.",
        f"- Of the 30, **{s['had_prior_polyline']}** had a prior canonical polyline "
        f"and **{s['never_routed_before']}** had never been routed before.",
        "- Raw responses + sha256 saved per address under "
        "`data/interim/route-pilot/raw/` (deterministic, resumable, cached).", "",
        "## Alt-provider length vs canonical route_km", "",
        f"- abs diff km: min **{s['abs_diff_km_min']}**, mean "
        f"**{s['abs_diff_km_mean']}**, max **{s['abs_diff_km_max']}**.",
        "- These differences are EXPECTED: the demo uses a different graph, profile "
        "and snapshot. They bound how far a generic car route sits from the canonical "
        "delivery route; they are **not** production distances and must not replace "
        "canonical route_km.", "",
        "## Why the alt provider CANNOT be accepted into production", "",
        "- Different routing graph (full-planet vs pinned Moldova PBF snapshot).",
        "- Different profile (generic car vs car.lua + delivery access/turn "
        "restrictions).",
        "- No control over engine version or determinism on a shared public server.",
        "- Silently substituting it for the canonical provider is forbidden.", "",
        "## Estimate for the full remaining batch", "",
        f"- Remaining external addresses without a canonical polyline: **~{est_full}**.",
        "- With the CANONICAL local OSRM: free, no API cost, no rate limit; a "
        f"~{est_full}-request `/route` batch completes in seconds–minutes locally.",
        "- Unblocker: stand up OSRM v26.7.3 + the recorded PBF + car.lua/access "
        "profiles, then route from the required restaurant origin(s).",
        "- **Not run here**: the full batch requires owner permission and the "
        "canonical engine; this pilot only proves the mechanism on 30 addresses.", "",
        "## Pilot address ids", "",
        "`" + ", ".join(s["pilot_ids"]) + "`", "",
    ]
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
