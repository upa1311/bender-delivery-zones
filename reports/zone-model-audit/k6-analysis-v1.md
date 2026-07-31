# CITY_K6 analysis v1

City deployable model (4,866 city addresses; natural-break DP over city
`expected_km`).

## Zones (CITY_K6R natural breaks)

| Zone | Route km | City addresses | Share | BALANCED fee руб |
|---|---|---:|---:|---:|
| 1 | ≤ 1.475 | 739 | 15.2 % | 12 |
| 2 | 1.475–2.225 | 717 | 14.7 % | 13 |
| 3 | 2.225–3.125 | 974 | 20.0 % | 14 |
| 4 | 3.125–4.175 | 762 | 15.7 % | 16 |
| 5 | 4.175–5.175 | 1028 | 21.1 % | 23 |
| 6 | > 5.175 | 646 | 13.3 % | 27 |

Three policies (руб.): DRIVER_CONSERVATIVE 13/14/15/17/24/28 · BALANCED
12/13/14/16/23/27 · CUSTOMER_FIRST 15/16/17/18/24/28.

## Read

- Unlike the full-population K=6 (which produced a 3.7 % external sliver), the
  city-only K=6 has no sliver (min share 13.3 %) — the sliver was an external-tail
  artefact. So K=6 is geometrically *feasible* for the city.
- **But it is the least stable:** only **64 % router/Yandex agreement** on the 28
  city controls (10 flips), and **4,163** different-zone neighbour pairs within
  100 m — more than double K=4.
- The near zones (1–4) differ by only 1–2 руб (12/13/14/16), so K=6 buys very
  little pricing resolution for a large stability cost.

**CITY_K6 is not recommended:** it adds boundaries and neighbour churn without a
meaningful pricing gain, and is the least robust against real Yandex divergence.
