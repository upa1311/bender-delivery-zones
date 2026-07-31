# CITY_K5 analysis v1 (fixed-origin)

City deployable model over the fixed-origin km (route from 46.82388, 29.48313),
4,866 city addresses, natural-break DP. K=5 was a hypothesis; numbers are not
tuned to favour it.

## Zones

| Zone | Fixed-origin km | City addresses | Share | BALANCED fee руб |
|---|---|---:|---:|---:|
| 1 | ≤ 1.675 | 1322 | 27 % | 11 |
| 2 | 1.675–2.875 | 1072 | 22 % | 11 |
| 3 | 2.875–4.125 | 629 | 13 % | 18 |
| 4 | 4.125–5.325 | 1141 | 23 % | 24 |
| 5 | > 5.325 | 702 | 14 % | 33 |

Policies (руб.): DRIVER_CONSERVATIVE 11/11/18/25/35 · BALANCED 11/11/18/24/33 ·
CUSTOMER_FIRST 11/11/16/22/29.

## Read
- Prices distance more finely than K=4 (no 27 %+ far band); min share 13 %, no
  sliver.
- **Now equally stable to K=4:** 25/28 manual agreement (flips MY-002, MY-073,
  MY-081) — identical to K=4. The earlier "K5 less stable" result was an artefact
  of the blended metric and does **not** hold on the fixed-origin metric.
- **Cost:** more neighbour discontinuities — 2,628 different-zone pairs within
  100 m (vs 1,667 for K=4), max jump 17 руб.

CITY_K5 is the fairest-by-distance city option and, on the corrected metric, no
less stable than K=4. Its only cost is more neighbours priced differently.
Recommended primary; owner decides K4 vs K5.
