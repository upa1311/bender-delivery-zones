# Северный re-investigation v1

**Prior verdict corrected.** Северный is NOT globally `TERRITORY_DATA_UNAVAILABLE`. It is absent from the canonical 9,216 pricing set, but a dedicated stage produced real candidate data.

## Sources checked (Cyrillic + Latin aliases)

- `docs/data/severny-service-area.geojson` — 1 candidate residential footprint polygon.
- `docs/data/severny-delivery-units.geojson` — 57 delivery units WITH `central_km` (route distance from the central origin).
- `docs/data/severny-candidate-buildings.geojson` — 59 raw candidate buildings.
- `docs/data/severny-route-qa.geojson` — 58 route-QA polylines.
- Canonical address set (`outside-city-distance-v1.csv`, 9,216) — Северный NOT present.
- `external-tariff-boundary-anchors-v1.csv` — SEVERNY_BOUNDARY UNPROVEN.
- Aliases searched: Северный / Severny / Severnyy / Nord / микрорайон Северный / Северная.

## What the data says

- Real place: `микрорайон Северный` (place=suburb node 5135654201), north of Varniţa village.
- Footprint: raw 59 candidate buildings → 57 included; 7 confirmed addresses, 23 apartment buildings; empty area 61.5%.
- Status: `candidate_residential_footprint`, resolution `owner_review_required`, disconnected_from_main_service = True.
- Delivery units: 7 `verified_osm_address` + 50 `unaddressed_delivery_unit`; all 57 carry `central_km` (6.925–8.726 km).

## Северный vs the three candidate boundaries

| boundary | Северный units inside | outside |
|---|---:|---:|
| r12463379 (level 8, city) | 0 | 57 |
| r9581354 (level 4, municipality) | 0 | 57 |
| r944727 (level 5, de-facto PMR) | 56 | 1 |

So Северный falls INSIDE only the de-facto PMR city (944727); it is OUTSIDE both the de-jure municipality and the city-proper. The boundary choice decides whether Северный is a city district or external.

## Honest status

**SEVERNY_CANDIDATE_OWNER_REVIEW_REQUIRED** — data exists but is unconfirmed: the footprint is disconnected from the main service area, 50/57 units are unaddressed, and the OSM source itself flags `owner_review`. It is NOT in the canonical pricing set and MUST NOT be priced without owner confirmation.

## Reproducible unblocker (analysis-only)

To integrate Северный: (1) owner confirms the footprint and which buildings are real delivery targets; (2) resolve the 50 unaddressed units to canonical addresses; (3) route each from the required origin with the canonical OSRM; (4) classify against the chosen boundary. Add as a separate analysis stage — no production change.
