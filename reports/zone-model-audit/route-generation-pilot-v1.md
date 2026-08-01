# Route generation pilot v1 — REAL run (ALTERNATIVE_PROVIDER_COMPARISON)

## Canonical provider (proven from repo, NOT reproducible here)

- Engine: **local OSRM v26.7.3**, car.lua + `endpoint-aware-delivery` access profile (docs/data/stage10c-osrm-build-manifest.json).
- Graph: **moldova-latest.osm.pbf** sha256 `09ba0c058e89…` (reports/stage-01/source-audit.md).
- Origin: **central_bender_origin** 29.48313,46.82388 — a single central restaurant origin (weight 0.85), NOT per-restaurant.
- The PBF (100 MB, gitignored) and the OSRM binary are absent in this checkout, so the canonical engine cannot be run here.

## What this pilot actually did

- Provider: **ALTERNATIVE_PROVIDER_COMPARISON** — public OSRM demo (router.project-osrm.org), full-planet OSM car profile.
- **30 real HTTP requests** from the SAME proven central origin to **30 unique** canonical external destinations.
- Succeeded: **30**, failed: **0**, served-from-cache on rerun: **30**.
- Of the 30, **12** had a prior canonical polyline and **18** had never been routed before.
- Raw responses + sha256 saved per address under `data/interim/route-pilot/raw/` (deterministic, resumable, cached).

## Alt-provider length vs canonical route_km

- abs diff km: min **0.0001**, mean **0.0091**, max **0.2071**.
- These differences are EXPECTED: the demo uses a different graph, profile and snapshot. They bound how far a generic car route sits from the canonical delivery route; they are **not** production distances and must not replace canonical route_km.

## Why the alt provider CANNOT be accepted into production

- Different routing graph (full-planet vs pinned Moldova PBF snapshot).
- Different profile (generic car vs car.lua + delivery access/turn restrictions).
- No control over engine version or determinism on a shared public server.
- Silently substituting it for the canonical provider is forbidden.

## Estimate for the full remaining batch

- Remaining external addresses without a canonical polyline: **~4338**.
- With the CANONICAL local OSRM: free, no API cost, no rate limit; a ~4338-request `/route` batch completes in seconds–minutes locally.
- Unblocker: stand up OSRM v26.7.3 + the recorded PBF + car.lua/access profiles, then route from the required restaurant origin(s).
- **Not run here**: the full batch requires owner permission and the canonical engine; this pilot only proves the mechanism on 30 addresses.

## Pilot address ids

`n2321749482, n2323343711, n2457586634, n2457586635, n2457586636, n2457586637, n4418837238, w353259234, w353619672, w353817270, w353817271, w353817272, n2457586661, n2457586638, n2457586639, n2457586662, w316846224, n2341956745, n2341956746, n2341956747, n2452549463, n2454873384, n2450951755, w353818413, w410936927, n2321749461, w225418020, w353044310, w352285814, w352339715`
