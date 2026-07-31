# K=4 analysis v1

Natural-break (DP-optimal) K=4 over `expected_km`, city economics on owner
assumptions. Address counts are over all 9,216; fees/savings/gaps are city-only.

## Zones (DP-optimal K=4)

| Zone | Route km | Addresses | Share | City fee (bal.) руб | Client saving | Driver gap |
|---|---|---:|---:|---:|---:|---:|
| 1 | ≤ 2.475 | 1708 | 18.5 % | 13 | ~5 | ~0 |
| 2 | 2.475–4.175 | 1979 | 21.5 % | 14 | ~4.6 | ~−0.4 |
| 3 | 4.175–5.775 | 3701 | **40.2 %** | 25 | ~5.2 | ~0.2 |
| 4 | > 5.775 | 1828 | 19.8 % | 31 | ~4.8 | ~−0.3 |

Released baseline (2.424/4.076/5.577): shares 18.0/20.6/37.1/24.3, city fees
13/14/24/30.

## Read

- **Strength:** fewest same-street splits (90 DP / 94 baseline) and lowest
  near-threshold churn (424–466 addresses within 50 m) of any K — simplest to
  explain and support.
- **Weakness:** one dominant zone 3 at **40 %** (2.475–5.775 km is a 3.3 km-wide
  band). A single fee (~25 руб) covers a wide range of real distances, so the
  client at 4.2 km and the client at 5.7 km pay the same though their equivalent
  taxi differs by ~9 руб.
- The released flat 25 руб corresponds almost exactly to the **zone 3** balanced
  fee — i.e. 25 руб is a "zone 3 price" applied to everyone.

K=4 is the simplest and most stable, at the cost of one coarse middle zone.
