# Route generation pilot v1

**Status: BLOCKED_IN_THIS_ENV (no live OSRM engine / PBF here).** No live or paid batch was run; nothing invented.

## Reproducible pilot plan (analysis-only, ≥30 addresses)

1. Stand up OSRM v26.7.3 with the recorded moldova PBF + car.lua (`scripts/build_osrm_with_manifest.sh`).
2. Select ≥30 external addresses spanning Парканы/Гиска/Протягайловка, near-boundary, min-route, max-route and anomalies (deterministic from the canonical set).
3. Request the **full route polyline** per address from the central origin (and, for production, from each restaurant origin).
4. Compare polyline length vs canonical `route_km`; store raw responses + sha256 + provenance; assert deterministic, resumable, cached output.

## Estimate for the full 4,338-route batch

- Engine: **local OSRM** — free, no API cost, no rate limit.
- Time: a local OSRM `/route` batch of ~4,338 requests completes in seconds to a few minutes on commodity hardware.
- The real cost is standing up the engine + 100 MB PBF, not per-request.
- Do NOT switch to a different provider without a comparison analysis; a different engine/profile would change route_km and cannot be silently substituted for the canonical provider.

**Owner permission is required before running the full batch.** This step only documents the plan; it does not run it.
