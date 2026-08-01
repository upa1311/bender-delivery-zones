# Owner-approved distance tariff — analysis layer v1

Analysis/test layer only. Production, Direct, releases, routing graph,
canonical addresses, fixed-origin routes, GitHub Pages and live zones/prices
are untouched. Every number below is generated from
`data/interim/owner-tariff-fees-v1.csv`.

## Formula

- City ≤ 3.0 km: **14 MDL**
- City > 3.0 km: **ceil(14 + (route_km - 3.0) * 4)**
- External surcharge: **max(5, ceil(outside_city_km * 2)), 0 at boundary**
- External final: **base_city_fee + external_surcharge**
- Rounding: full-precision km; ceil applied only to the final price

## City (Бендеры)

- Addresses: **4866**
- Fee min/median/max: **14 / 14.0 / 32** MDL

### Fee distribution (city)

| Fee MDL | Addresses |
|---:|---:|
| 14 | 2446 |
| 15 | 86 |
| 16 | 163 |
| 17 | 132 |
| 18 | 117 |
| 19 | 180 |
| 20 | 320 |
| 21 | 235 |
| 22 | 205 |
| 23 | 212 |
| 24 | 210 |
| 25 | 161 |
| 26 | 114 |
| 27 | 110 |
| 28 | 70 |
| 29 | 48 |
| 30 | 33 |
| 31 | 19 |
| 32 | 5 |

## External territories

| Territory | Addresses | Auto-calculated | OUTSIDE_DISTANCE_UNAVAILABLE |
|---|---:|---:|---:|
| Парканы | 3446 | 0 | 3446 |
| Гиска | 399 | 0 | 399 |
| Протягайловка | 505 | 0 | 505 |
| Северный | 0 | 0 | 0 |

outside_city_km source: NONE — no proven city-boundary route split exists in the data; outside_city_km left blank, status OUTSIDE_DISTANCE_UNAVAILABLE, final_fee empty. Not invented.

## Control addresses

| address_id | territory | route_km | base | surcharge | final_fee | status |
|---|---|---:|---:|---:|---:|---|
| w160140720 | Бендеры | 0.5 | 14 | 0 | 14 | CITY_OK |
| w222794975 | Бендеры | 1.0 | 14 | 0 | 14 | CITY_OK |
| w295540309 | Бендеры | 1.5 | 14 | 0 | 14 | CITY_OK |
| w303323464 | Бендеры | 1.999 | 14 | 0 | 14 | CITY_OK |
| w304087554 | Бендеры | 2.5 | 14 | 0 | 14 | CITY_OK |
| w531651451 | Бендеры | 2.897 | 14 | 0 | 14 | CITY_OK |
| w352306780 | Бендеры | 2.99 | 14 | 0 | 14 | CITY_OK |
| w352307871 | Бендеры | 3.0 | 14 | 0 | 14 | CITY_OK |
| w354300758 | Бендеры | 3.005 | 15 | 0 | 15 | CITY_OK |
| w531651458 | Бендеры | 3.048 | 15 | 0 | 15 | CITY_OK |
| w352468414 | Бендеры | 3.1 | 15 | 0 | 15 | CITY_OK |
| w330883126 | Бендеры | 3.252 | 16 | 0 | 16 | CITY_OK |
| w352312106 | Бендеры | 3.499 | 16 | 0 | 16 | CITY_OK |
| w404791979 | Бендеры | 3.748 | 17 | 0 | 17 | CITY_OK |
| w404798022 | Бендеры | 3.999 | 18 | 0 | 18 | CITY_OK |
| w304088417 | Бендеры | 4.5 | 20 | 0 | 20 | CITY_OK |
| w115331461 | Бендеры | 5.0 | 22 | 0 | 22 | CITY_OK |
| w318084687 | Бендеры | 5.501 | 25 | 0 | 25 | CITY_OK |
| w209273575 | Бендеры | 5.999 | 26 | 0 | 26 | CITY_OK |
| w209267113 | Бендеры | 6.496 | 28 | 0 | 28 | CITY_OK |
| n2334334346 | Бендеры | 7.0 | 30 | 0 | 30 | CITY_OK |
| w299956671 | Бендеры | 7.458 | 32 | 0 | 32 | CITY_OK |
| w162030333 | Бендеры | 0.032 | 14 | 0 | 14 | CITY_OK |
| n2323152058 | Парканы | 4.551 | 21 |  | — | OUTSIDE_DISTANCE_UNAVAILABLE |
| n2321749385 | Гиска | 4.574 | 21 |  | — | OUTSIDE_DISTANCE_UNAVAILABLE |
| n11222053152 | Протягайловка | 7.939 | 34 |  | — | OUTSIDE_DISTANCE_UNAVAILABLE |

## Economics vs old BALANCED

City addresses failing the old BALANCED math under this owner tariff: **3802**. The owner-approved tariff is intentionally NOT altered to satisfy the old policy; consequences are shown in `owner-tariff-fees-v1.csv` (client_saving, driver_gap, passes_old_balanced).

Verdict: ANALYSIS_COMPLETE / OWNER_REVIEW_REQUIRED.
