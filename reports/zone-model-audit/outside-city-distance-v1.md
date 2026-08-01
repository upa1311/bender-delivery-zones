# Verified outside-city route distance — analysis v1

**Verdict: PARTIAL_COVERAGE_OWNER_REVIEW_REQUIRED**. Analysis/test layer only; production,
Direct, releases, routing graph, canonical addresses, fixed-origin routes,
GitHub Pages and live tariffs are untouched. Numbers generated from
`data/interim/outside-city-distance-v1.csv`.

## City boundary provenance

- File: `docs/data/source-boundaries.geojson` key `bender` — OSM relation 12463379, area 21.048 km²
- Note: Исходная административная граница OSM. Не изменялась.
- Input CRS EPSG:4326; working projection: local equirectangular at origin 46.82388,29.48313; <0.1% length error over the study area
- Manual edits: none; sha256 `d04979a6e2fe0525…`

## Route geometry provenance

- File: `docs/data/stage-09b-map-routes.geojson` kind `fastest_time`, OSRM (stage-09 engine)
- Length tolerance: max(0.05, 1% * route_km)
- only 3 external addresses have a stored canonical polyline; their polyline length matches route_km to < 2 m.

## Outside-city method

Project route + boundary to the metric CRS; `outside_city_km = length(route.difference(boundary)) / 1000`. Handles multiple crossings, fully inside (0), fully outside, edge-touching (0), multipolygon and holes; invalid geometry is repaired with buffer(0) or flagged. Guards: `0 ≤ outside_city_km ≤ route_km + tol`. Tariff: `base_city_fee + max(5, ceil(outside_city_km*2))`.

## Coverage per external territory

| Territory | Total | Valid polylines | Priced (geometry-verified) | Unavailable |
|---|---:|---:|---:|---:|
| Парканы | 3446 | 1 | 1 | 3445 |
| Гиска | 399 | 1 | 1 | 398 |
| Протягайловка | 505 | 1 | 1 | 504 |

### Status counts (all external)

- CALCULATED: 3
- ROUTE_GEOMETRY_UNAVAILABLE: 4347

## Северный

- In canonical 9,216: **False** (aliases checked: Северный, Severny, Severnyy, Nord, микрорайон Северный)
- Separate non-canonical source: 57 rows in `docs/data/severny-delivery-units.csv`
- Северный is NOT among the 9,216 canonical addresses (verified via settlement + alias scan). A separate non-canonical source (severny-delivery-units.csv) exists; promoting it into the canonical release is a PRODUCTION change and is out of scope here.

## Control addresses (from data)

| id | territory | route_km | polyline_km | outside_km | final_fee | status |
|---|---|---:|---:|---:|---:|---|
| n2321749482 | Гиска | 6.385 | 6.3859 | 2.8653 | 34 | CALCULATED |
| n4418837238 | Парканы | 7.075 | 7.0754 | 5.3671 | 42 | CALCULATED |
| w353259234 | Протягайловка | 6.91 | 6.9102 | 1.366 | 35 | CALCULATED |
| n2323343711 | Парканы | 3.167 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2457586634 | Парканы | 3.181 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2457586635 | Парканы | 3.199 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2457586636 | Парканы | 3.214 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2459682665 | Парканы | 5.177 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2459760249 | Парканы | 5.177 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2454873384 | Парканы | 5.178 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2460035286 | Парканы | 7.56 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2460035283 | Парканы | 7.574 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2460033782 | Парканы | 7.575 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| w353619672 | Гиска | 3.66 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| w353817270 | Гиска | 3.66 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| w353817271 | Гиска | 3.686 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| w353817272 | Гиска | 3.708 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2321749493 | Гиска | 5.878 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2321749461 | Гиска | 5.907 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2321749466 | Гиска | 5.909 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2341956745 | Гиска | 9.125 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2341956746 | Гиска | 9.37 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2341956747 | Гиска | 9.371 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| w353044310 | Протягайловка | 4.484 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2337985528 | Протягайловка | 4.555 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| w320344002 | Протягайловка | 4.736 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| w352285305 | Протягайловка | 4.736 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| w352339715 | Протягайловка | 6.466 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| w352333671 | Протягайловка | 6.469 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| w352042429 | Протягайловка | 6.478 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2337908048 | Протягайловка | 9.033 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| w316845604 | Протягайловка | 9.064 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| w316846224 | Протягайловка | 9.121 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |

## Blocker / gap

Only 3 of the external addresses have a stored canonical route polyline, so only those are geometry-priced. The remaining external addresses are `ROUTE_GEOMETRY_UNAVAILABLE`. **Minimal fix:** persist (or regenerate with the same OSRM engine, profile and central origin that produced the canonical route_km) the per-address `fastest_time` polylines for every external address, then re-run this script — no other change is required. Northern (Северный) additionally needs its addresses promoted into the canonical release (a production step, out of scope).

Verdict: PARTIAL_COVERAGE_OWNER_REVIEW_REQUIRED.
