# CITY_K6 analysis v1 (fixed-origin)

City deployable model over the fixed-origin km (route from 46.82388, 29.48313),
4,866 city addresses, natural-break DP.

## Zones

| Zone | Fixed-origin km | City addresses | Share | BALANCED fee руб |
|---|---|---:|---:|---:|
| 1 | ≤ 1.675 | 1322 | 27 % | 11 |
| 2 | 1.675–2.825 | 1052 | 22 % | 11 |
| 3 | 2.825–3.925 | 532 | 11 % | 17 |
| 4 | 3.925–4.875 | 873 | 18 % | 22 |
| 5 | 4.875–5.825 | 736 | 15 % | 27 |
| 6 | > 5.825 | 351 | **7 %** | 34 |

Policies (руб.): DRIVER_CONSERVATIVE 11/11/17/22/28/36 · BALANCED 11/11/17/22/27/34 ·
CUSTOMER_FIRST 11/11/15/20/25/31.

## Read
- Zone 6 holds only **7 % (351 addresses)** — a near-sliver far zone.
- **Least stable:** 24/28 manual agreement (4 flips) and the **sharpest** single
  neighbour jump (19 руб).
- Near zones (1–2) are identical (11 руб), so K=6 adds a boundary that buys no
  pricing resolution there.

**CITY_K6 is not recommended:** it over-segments the tail into a near-sliver, is
the least robust against real Yandex divergence, and adds sharper neighbour jumps
without a pricing gain.
