# K=5 analysis v1

Natural-break (DP-optimal) K=5 over `expected_km`. K=5 was a hypothesis only; the
numbers below are not tuned to favour it.

## Zones (DP-optimal K=5)

| Zone | Route km | Addresses | Share | City fee (bal.) руб | Client saving | Driver gap |
|---|---|---:|---:|---:|---:|---:|
| 1 | ≤ 2.175 | 1420 | 15.4 % | 13 | ~5 | ~0 |
| 2 | 2.175–3.675 | 1570 | 17.0 % | 14 | ~4.6 | ~0 |
| 3 | 3.675–4.975 | 2605 | 28.3 % | 22 | ~5 | ~0 |
| 4 | 4.975–6.225 | 2483 | 26.9 % | 27 | ~5 | ~0 |
| 5 | > 6.225 | 1138 | 12.3 % | 33 | ~4.5 | ~−0.5 |

## Read

- **Strength:** the dominant K=4 middle zone (40 %) is split into zone 3 (28 %)
  and zone 4 (27 %), so no zone exceeds ~28 %. Min share 12.3 % clears the 5 %
  and even the production 12 % floor — no sliver. Pricing tracks distance more
  finely: the 4.2 km and 5.7 km clients now sit in different zones (22 vs 27 руб).
- **Cost:** ~15 more same-street splits than K=4 (109 vs 94) and more
  near-threshold addresses (609 within 50 m vs 466). More neighbours pay
  different prices.
- Economics stay healthy: under owner assumptions client saves ~5 руб/zone and
  driver gap stays within ±0.5 руб across all five zones.

K=5 is the most balanced partition and prices distance more fairly than K=4, at a
modest cost in same-street consistency. Whether that trade is worth it is an
owner decision, not a data verdict.
