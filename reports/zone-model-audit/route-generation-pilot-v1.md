# Route generation pilot v1 — CENTRAL_ORIGIN_ALTERNATIVE_PROVIDER_COMPARISON

**This is NOT a restaurant-specific production pilot.**

## Canonical provider (proven from repo, NOT reproducible here)

- Engine: **local OSRM v26.7.3**, car.lua + `endpoint-aware-delivery` access profile (docs/data/stage10c-osrm-build-manifest.json).
- Graph: **moldova-latest.osm.pbf** sha256 `09ba0c058e89…` (reports/stage-01/source-audit.md).
- Origin: **central_bender_origin** 29.48313,46.82388 — single CENTRAL REPRESENTATIVE restaurant-cluster origin (weight 0.85, poi_count 28) — NOT a specific ordering restaurant.
- The PBF (100 MB, gitignored) and the OSRM binary are absent here, so the canonical engine cannot be run.

## Central-origin limitation (critical)

Canonical route_km and this pilot both route from ONE central representative origin. That is fine for testing the routing engine and reproducibility, but it does **NOT** prove a production delivery price. A real order's price must be routed **ordering restaurant → client address**. Restaurant coordinates are not yet provided/confirmed (see `restaurant-origins-plan-v1.md` → `RESTAURANT_ORIGINS_UNAVAILABLE`). Mass route generation is blocked until a restaurant registry and an owner decision exist.

## What this pilot actually did

- Provider: OSRM demo (router.project-osrm.org), full-planet car profile.
- URL template: `https://router.project-osrm.org/route/v1/driving/{o_lon},{o_lat};{d_lon},{d_lat}?overview=full&geometries=geojson`; params: `{"overview": "full", "geometries": "geojson", "profile": "driving"}`.
- Mode of this run: **cache_replay** (network_capture records timestamps; cache_replay rebuilds offline from committed raw + attempt log).
- **30 requests**, **30** OK, **0** failed, over **30 unique** destinations (18 never routed before).
- Attempt metadata (timestamp/attempt/retries/URL) per request: `timestamps + attempt history captured over the network and committed to route-pilot-attempts-v1.csv`.
- Raw responses + sha256 under `data/interim/route-pilot/raw/`; attempt log in `route-pilot-attempts-v1.csv`; per-request provenance in `route-pilot-results-v1.csv`.

## Alt-provider length vs canonical route_km

- |diff| km: min **0.0001**, mean **0.0091**, max **0.2071**. Differences are expected (different graph/profile/snapshot); they are NOT production distances and must not replace canonical route_km. Silent provider substitution is forbidden.

## Full-batch scope (correct formula)

Production routing is per ordering restaurant, so the batch size is:

```
total_routes = active_restaurant_origins × canonical_delivery_destinations
```

With 4350 canonical external destinations (city addresses add more):

| restaurants | routes | local OSRM time* | storage** |
|---:|---:|---|---|
| 1 | 4,350 | seconds–1 min | ~tens of MB |
| 5 | 21,750 | ~minutes | ~hundreds of MB |
| 10 | 43,500 | ~minutes | ~hundreds of MB |

*Local OSRM `/route`: free, no API cost, no rate limit; time dominated by engine setup, not per-request. **Raw + geometry per route, gzip-friendly. Actual restaurant count is UNKNOWN — no registry (see plan). Caching key: `(restaurant_id, canonical_address_id, graph_version)`; resumable by skipping existing cache entries. Expected failures/retries: near-zero locally.

**No full batch was run.** It is blocked until a restaurant registry and owner permission exist.

## Pilot address ids

`n2321749482, n2323343711, n2457586634, n2457586635, n2457586636, n2457586637, n4418837238, w353259234, w353619672, w353817270, w353817271, w353817272, n2457586661, n2457586638, n2457586639, n2457586662, w316846224, n2341956745, n2341956746, n2341956747, n2452549463, n2454873384, n2450951755, w353818413, w410936927, n2321749461, w225418020, w353044310, w352285814, w352339715`
