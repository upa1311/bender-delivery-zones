# CITY_K4 analysis v1 (fixed-origin)

City deployable model over the fixed-origin km (route from 46.82388, 29.48313),
4,866 city addresses, natural-break DP.

## Zones

| Zone | Fixed-origin km | City addresses | Share | BALANCED fee руб |
|---|---|---:|---:|---:|
| 1 | ≤ 1.725 | 1349 | 28 % | 11 |
| 2 | 1.725–3.275 | 1192 | 24 % | 12 |
| 3 | 3.275–4.975 | 1321 | 27 % | 22 |
| 4 | > 4.975 | 1004 | 21 % | 32 |

Policies (руб.): DRIVER_CONSERVATIVE 11/12/23/34 · BALANCED 11/12/22/32 ·
CUSTOMER_FIRST 11/12/20/28.

## Read
- On the fixed-origin metric K=4 is **well balanced** (max share 28 %), unlike the
  earlier blended-metric K=4 (one 40 % zone).
- **Most stable and fewest neighbour discontinuities:** 25/28 manual agreement
  (flips MY-002, MY-079, MY-085); 1,667 different-zone neighbour pairs within
  100 m — the lowest of any K.
- Simplest to explain and support.

CITY_K4 is the simplest, tied for most stable, with the fewest neighbour price
differences — the safe fallback.
