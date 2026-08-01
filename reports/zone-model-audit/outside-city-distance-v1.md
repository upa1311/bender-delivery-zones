# Outside-city route & city-boundary audit v1

**Verdict: BLOCKED_BY_CITY_BOUNDARY**

No VERIFIED_FOR_TARIFF city boundary yet: the Bender OSM boundary (relation 12463379) is a provisional proxy per the repo. The full geometry of ALL THREE candidate relations (12463379, 9581354, 944727) has now been EXTRACTED from OSM (see data/interim/osm-boundaries/ and boundary-candidates-comparison-v2.csv); the earlier 'no geometry in repo' blocker for 9581354 / 944727 is lifted. None is approved as the operational tariff boundary, so the 12 external routes still cannot be priced without an owner boundary decision.

Repo evidence the boundary is provisional: `exact point unknown; current Bender OSM boundary is a provisional proxy`

Analysis/test layer only; production, Direct, releases, routing graph,
canonical addresses, driver cabinet, the driver zone switch, operational
dispatch zones, GitHub Pages and live tariffs are untouched.

## Route inventory

| Source | features | external central routes | sha256 |
|---|---:|---:|---|
| docs/data/stage-09a-control-routes.geojson | 37 | 9 | b2bd311f796c… |
| docs/data/stage-09b-map-routes.geojson | 57 | 3 | 16c443521da8… |

- Unique usable external routes (deduped): **12**
- Route conflicts: none

## Route-length sensitivity

| Threshold km | Accepted | Total |
|---:|---:|---:|
| 0.005 | 12 | 12 |
| 0.01 | 12 | 12 |
| 0.02 | 12 | 12 |
| 0.05 | 12 | 12 |
| 0.1 | 12 | 12 |

Acceptance changes across thresholds: **False**; price impact: none (boundary unverified → no approved price at any threshold).

## City-boundary candidates (all three geometries extracted)

All three relation geometries have been extracted from OSM (Overpass, ODbL) at commit 6d4679c and stored under data/interim/osm-boundaries/. Unified suitability comparison: boundary-candidates-comparison-v2.csv.

| relation | admin_level | geometry extracted | verification | area km² | geometry path | geom sha256 | name |
|---|---|---|---|---:|---|---|---|
| relation 12463379 | 8 | yes | **PROVISIONAL_PROXY** | 21.048 | `data/interim/osm-boundaries/relation-12463379.geojson` | 2df13ada7b09… | Бендеры |
| relation 9581354 | 4 | yes | **EXTRACTED_ADMIN_BOUNDARY_UNVERIFIED** | 37.7255 | `data/interim/osm-boundaries/relation-9581354.geojson` | cac2eb437855… | Municipiul Bender |
| relation 944727 | 5 | yes | **EXTRACTED_ADMIN_BOUNDARY_UNVERIFIED** | 72.0325 | `data/interim/osm-boundaries/relation-944727.geojson` | cf5819572e1c… | Бендеры |

Provenance per relation: raw_source_path, geometry_path, raw_sha256, geometry_sha256, source_object_timestamp and original_retrieval_timestamp_utc are recorded in `data/interim/osm-boundaries/boundary-extraction-provenance.json`. The 'no geometry in repo' blocker (relations 9581354 / 944727) was lifted at the boundary-extraction stage (commit 6d4679c).

**Critical rule:** an OSM administrative boundary is NOT automatically the approved operational tariff boundary. None of the candidates has reproducible proof of being the tariff switch boundary, so none is VERIFIED_FOR_TARIFF and no address gets an approved final_fee.

## Coverage per external territory

| Territory | Total | Routes found | Valid routes | Approved-priced | Unavailable |
|---|---:|---:|---:|---:|---:|
| Парканы | 3446 | 6 | 6 | 0 | 3446 |
| Гиска | 399 | 5 | 5 | 0 | 399 |
| Протягайловка | 505 | 1 | 1 | 0 | 505 |

### Status counts

- CITY_BOUNDARY_UNAVAILABLE: 12
- ROUTE_GEOMETRY_UNAVAILABLE: 4338

## Северный

- In canonical 9,216: **False** (aliases checked: Северный, Severny, Severnyy, Nord, микрорайон Северный, Severnii, Nordul; settlements scanned: Бендеры, Гиска, Парканы, Протягайловка)
- Non-canonical source: 57 rows in `docs/data/severny-delivery-units.csv`
- Северный addresses exist only in the non-canonical severny-delivery-units.csv; a future analysis-only step could map them to OSM/verified coordinates and route them, but promoting them into the canonical release is a production step and is out of scope.

## Scenario analytics (NON-PRODUCTION)

Under the PROVISIONAL boundary 12463379, `outside_city_km` and would-be fees are computed for the 12 routed addresses ONLY as scenario analytics in `data/interim/outside-city-boundary-scenarios-v1.csv`. These are NOT approved prices and are kept separate from the production-readiness CSV (whose final_fee is empty for every external address).

## Control addresses

### A. Real canonical routes
| id | territory | route_km | polyline_km | Δm | route_val | status |
|---|---|---:|---:|---:|---|---|
| n2323343711 | Парканы | 3.167 | 3.1648 | 2.2 | LENGTH_OK | CITY_BOUNDARY_UNAVAILABLE |
| n2457586634 | Парканы | 3.181 | 3.1793 | 1.7 | LENGTH_OK | CITY_BOUNDARY_UNAVAILABLE |
| n2457586635 | Парканы | 3.199 | 3.1983 | 0.7 | LENGTH_OK | CITY_BOUNDARY_UNAVAILABLE |
| n2457586636 | Парканы | 3.214 | 3.2128 | 1.2 | LENGTH_OK | CITY_BOUNDARY_UNAVAILABLE |
| n2457586637 | Парканы | 3.23 | 3.2287 | 1.3 | LENGTH_OK | CITY_BOUNDARY_UNAVAILABLE |
| w353619672 | Гиска | 3.66 | 3.6639 | 3.9 | LENGTH_OK | CITY_BOUNDARY_UNAVAILABLE |
| w353817270 | Гиска | 3.66 | 3.6637 | 3.7 | LENGTH_OK | CITY_BOUNDARY_UNAVAILABLE |
| w353817271 | Гиска | 3.686 | 3.6901 | 4.1 | LENGTH_OK | CITY_BOUNDARY_UNAVAILABLE |
| w353817272 | Гиска | 3.708 | 3.7112 | 3.2 | LENGTH_OK | CITY_BOUNDARY_UNAVAILABLE |
| n2321749482 | Гиска | 6.385 | 6.3859 | 0.9 | LENGTH_OK | CITY_BOUNDARY_UNAVAILABLE |
| w353259234 | Протягайловка | 6.91 | 6.9102 | 0.2 | LENGTH_OK | CITY_BOUNDARY_UNAVAILABLE |
| n4418837238 | Парканы | 7.075 | 7.0754 | 0.4 | LENGTH_OK | CITY_BOUNDARY_UNAVAILABLE |
| n2457586661 | Парканы | 3.23 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2457586638 | Парканы | 3.247 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2457586639 | Парканы | 3.267 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2460035286 | Парканы | 7.56 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2460035283 | Парканы | 7.574 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2460033782 | Парканы | 7.575 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| w353818413 | Гиска | 3.718 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| w353818412 | Гиска | 3.73 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| w353818414 | Гиска | 3.743 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2341956745 | Гиска | 9.125 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2341956746 | Гиска | 9.37 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2341956747 | Гиска | 9.371 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| w353044310 | Протягайловка | 4.484 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2337985528 | Протягайловка | 4.555 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| w320344002 | Протягайловка | 4.736 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| n2337908048 | Протягайловка | 9.033 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| w316845604 | Протягайловка | 9.064 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |
| w316846224 | Протягайловка | 9.121 | — | — | — | ROUTE_GEOMETRY_UNAVAILABLE |

### B. Synthetic geometry fixtures (unit tests, not real addresses)

fully_inside, fully_outside, single_crossing, multiple_crossings, touching_boundary, multipolygon, hole, invalid_route, invalid_boundary, missing_geometry

Verdict: BLOCKED_BY_CITY_BOUNDARY.
