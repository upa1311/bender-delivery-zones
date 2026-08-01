# Route provider investigation v1

Canonical `route_km` provenance (from the repo, reproducible):

- Provider: **OSRM v26.7.3**, local server `http://127.0.0.1:5000` (scripts/stage09_engine.py).
- Profile: **car.lua** + custom `endpoint-aware-delivery.1` access profile and ordered turn-restriction parser (docs/data/stage10c-osrm-build-manifest.json, stage10d-graph-provenance.json).
- Source graph: **moldova-latest.osm.pbf** sha256 09ba0c058e89… (matches registry source_dataset_version `moldova-pbf:09ba0c058e89`).
- Origins: **central 46.82388,29.48313** (weight 0.85) + bam + outer; `central_km` is the fixed-origin route, `expected_km` a blend.

## Critical limitation

Canonical `route_km` is measured **from a single central point**, not from each restaurant. A real order's price must be routed from the ORDERING restaurant to the client. **The current canonical route_km is therefore a proxy and is NOT suitable as a universal production price for all restaurants** — per-restaurant routing (per restaurant origin) is required for a production tariff.

## Reproducibility

Routes are reproducible with: the recorded moldova PBF (sha256 above), OSRM v26.7.3, the car.lua profile (sha256 in the manifest), and the delivery access/restriction profile versions. Free, local, no rate limit, no API cost. The OSRM engine is not running in this analysis environment and the 100 MB PBF is not in the clone (gitignored), so no live routing runs here.
