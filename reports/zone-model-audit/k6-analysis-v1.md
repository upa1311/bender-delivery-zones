# K=6 analysis v1

Natural-break (DP-optimal) K=6 over `expected_km`.

## Zones (DP-optimal K=6)

| Zone | Route km | Addresses | Share | City fee (bal.) руб |
|---|---|---:|---:|---:|
| 1 | ≤ 2.075 | 1358 | 14.7 % | 13 |
| 2 | 2.075–3.375 | 1306 | 14.2 % | 14 |
| 3 | 3.375–4.525 | 1651 | 17.9 % | 18 |
| 4 | 4.525–5.575 | 2655 | 28.8 % | 25 |
| 5 | 5.575–6.975 | 1909 | 20.7 % | 30 |
| 6 | > 6.975 | 337 | **3.7 %** | — (no city addresses) |

## Read

- **Blocker:** zone 6 holds only **337 addresses (3.7 %)** and fails the 5 % and
  12 % minimum-share rules — an economically meaningless sliver. It is also
  almost entirely external, so it has **no city fee at all** under the honest
  city-only economics.
- Forcing K=6 into equal quantiles removes the sliver (16.6 % each) but discards
  the cost structure entirely — the breaks no longer sit at natural distance gaps.
- Same-street splits (97) are not worse than K=5, but the far sliver plus the
  still-dominant zone 4 (29 %) means K=6 adds a boundary without buying balance.

**Route geometry argues against K=6:** it over-segments the tail into a sliver
without fixing the dominant middle zone. K=6 is not recommended on the current
data.
