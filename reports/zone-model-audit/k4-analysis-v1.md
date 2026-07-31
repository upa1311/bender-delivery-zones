# CITY_K4 analysis v1

City deployable model (4,866 city addresses; natural-break DP over city
`expected_km`). Full-population 4R is a diagnostic only — see
`zone-model-comparison-v1.md`.

## Zones (CITY_K4R natural breaks)

| Zone | Route km | City addresses | Share | BALANCED fee руб |
|---|---|---:|---:|---:|
| 1 | ≤ 2.025 | 1338 | 27.5 % | 12 |
| 2 | 2.025–3.275 | 1243 | 25.5 % | 13 |
| 3 | 3.275–4.525 | 820 | 16.9 % | 17 |
| 4 | > 4.525 | 1465 | 30.1 % | 25 |

Three policies (руб.): DRIVER_CONSERVATIVE 13/14/18/26 · BALANCED 12/13/17/25 ·
CUSTOMER_FIRST 15/16/20/26.

## Strengths
- **Most stable on the real controls:** 89 % router/Yandex agreement (3 flips of
  28 city controls).
- **Fewest neighbour price discontinuities:** 1,750 different-zone pairs within
  100 m, max jump 13 руб.
- Simplest to explain and support.

## Weakness
- Zone 4 (> 4.525 km) holds 30 % of city addresses in one band, so the far-city
  client at 4.6 km and at 6 km pay the same 25 руб.

CITY_K4 is the simplest, most stable option, at the cost of one broad far zone.
