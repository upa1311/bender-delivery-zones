# CITY_K5 analysis v1

City deployable model (4,866 city addresses; natural-break DP over city
`expected_km`). K=5 was a hypothesis only; numbers are not tuned to favour it.

## Zones (CITY_K5R natural breaks)

| Zone | Route km | City addresses | Share | BALANCED fee руб |
|---|---|---:|---:|---:|
| 1 | ≤ 1.975 | 1302 | 26.8 % | 12 |
| 2 | 1.975–3.075 | 1083 | 22.3 % | 13 |
| 3 | 3.075–4.175 | 807 | 16.6 % | 16 |
| 4 | 4.175–5.175 | 1028 | 21.1 % | 23 |
| 5 | > 5.175 | 646 | 13.3 % | 27 |

Three policies (руб.): DRIVER_CONSERVATIVE 13/14/17/24/28 · BALANCED
12/13/16/23/27 · CUSTOMER_FIRST 15/16/18/24/28.

## Strengths
- Splits the broad K=4 far zone (30 %) into two (21 % + 13 %), so pricing tracks
  distance more finely; no zone exceeds ~27 %, none is a sliver (min 13.3 %).

## Costs
- **Stability drops:** 79 % router/Yandex agreement on the 28 city controls
  (6 flips) vs 89 % for K=4.
- **More neighbour discontinuities:** 2,766 different-zone pairs within 100 m
  (vs 1,750 for K=4), max jump 15 руб.

CITY_K5 is the fairest-by-distance city option; the cost is measurably lower
boundary stability and more neighbours priced differently. Owner trade-off.
