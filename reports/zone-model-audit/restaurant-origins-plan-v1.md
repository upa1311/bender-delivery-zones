# Restaurant-specific routing plan v1

## Status: `RESTAURANT_ORIGINS_UNAVAILABLE`

The repository has **no per-restaurant registry** (no restaurant_id / name / canonical address / verified coordinates / active status). It contains only **3 REPRESENTATIVE cluster origins** (docs/data/restaurant-origins.geojson; config/demand.yml states POIs are clustered into representative origins, not treated as complete truth):

| key | role | poi_count | lon | lat |
|---|---|---:|---:|---:|
| central_bender_origin | central | 28 | 29.48313 | 46.82388 |
| bam_origin | bam | 6 | 29.47296 | 46.84167 |
| outer_origin_2 | outer_other | 3 | 29.48801 | 46.83396 |

These are cluster representatives for a demand model, NOT the coordinates of individual ordering restaurants. No restaurant coordinates are invented.

## Minimum required input schema (owner to provide)

```
restaurant_id           # stable id
restaurant_name         # display name
canonical_address       # settlement, street, house
latitude                # WGS84
longitude               # WGS84
coordinate_source       # e.g. OSM node, surveyed, owner-provided
verification_status     # verified | unverified
active_status           # active | inactive
delivery_eligibility    # eligible | not
```

## Full-batch scope (formula, not a fixed number)

```
total_routes = active_restaurant_origins × canonical_delivery_destinations
```
With 4,350 canonical external destinations (city addresses add more):

| restaurants | routes | local OSRM time* | storage** |
|---:|---:|---|---|
| 1 | 4,350 | seconds–1 min | ~tens of MB |
| 5 | 21,750 | ~minutes | ~hundreds of MB |
| 10 | 43,500 | ~minutes | ~hundreds of MB |
| N (actual, UNKNOWN) | N × 4,350 | — | — |

*Local canonical OSRM `/route`: free, no API cost, no rate limit; time dominated by engine setup. **Raw + geometry per route. Rate-limit assumptions: none locally. Expected failures/retries: near-zero locally. Caching key: `(restaurant_id, canonical_address_id, graph_version)`; resumable by skipping existing cache entries.

## Why the batch is not run

No restaurant registry exists, and the central-origin pilot does not prove per-restaurant production prices. Mass generation is blocked until the owner provides the registry and approves a boundary. **No batch was run.**
