# Customer / driver balance v1

City addresses only (4,866; owner assumptions), on the **fixed-origin** km metric
(route from 46.82388, 29.48313). External territories carry a bracket, not a price.
Full grid: `data/interim/zone-economics-scenarios-v1.csv`. Exact per-zone policy
prices: `data/interim/zone-policy-prices-v1.csv`.

## Commission benchmark

`driver_best_taxi_take = max(taxi_reference - 5, 0.65 × taxi_reference)`. The two
cross over at `taxi_reference = 5 / 0.35 = 14.29 руб`. Because the minimum fare is
18 руб, every city taxi_reference ≥ 18 > 14.29, so the fixed-5 model wins for
**100 % (4,866 / 4,866)** of city trips. The correct driver benchmark is
**`taxi_reference - 5`** in every zone, not `0.65 × taxi_reference`.

## Price policies — constraint-driven over ALL zone addresses

Each fee is the most client-favourable integer whose driver-gap constraint holds
for the required fraction of **all** addresses in the zone (not the median), then
clamped so **CUSTOMER_FIRST ≤ BALANCED ≤ DRIVER_CONSERVATIVE** and monotone.

Example CITY_K5R (thresholds 1.675 / 2.875 / 4.125 / 5.325 km):

| Policy | Zone fees руб | Driver rule |
|---|---|---|
| DRIVER_CONSERVATIVE | 11 / 11 / 18 / 25 / 35 | gap ≤ 2, cover ≥ 95 % |
| BALANCED | 11 / 11 / 18 / 24 / 33 | gap ≤ 3 and ≤ 10 %, cover ≥ 90 % |
| CUSTOMER_FIRST | 11 / 11 / 16 / 22 / 29 | gap ≤ 5 and ≤ 15 %, cover ≥ 80 % |

Near zones pin at the 18 руб taxi floor, so all policies meet at 11 руб there; the
policies separate in the farther zones.

## The current flat 25 руб — policy-specific (city, 4,866)

| Test | Addresses | Share |
|---|---:|---:|
| Client overpays (25 > equivalent taxi) | 3,051 | 62.7 % |
| Driver gap > 2 руб | 692 | 14.2 % |
| Driver gap > 3 руб | 560 | 11.5 % |
| Driver gap > 5 руб | 348 | 7.2 % |
| Driver gap > 10 % | 587 | 12.1 % |
| Driver gap > 15 % | 407 | 8.4 % |

A flat 25 руб is dearer than an equivalent taxi for ~63 % of city addresses and
leaves the driver >5 руб short on ~7 %. It behaves like a far-zone price applied
to everyone.

## Sensitivity envelope

`zone-economics-scenarios-v1.csv` (5,184 rows). Under the owner's baseline (city 6
/ min 18 / fixed 5) almost any modest discount satisfies both sides; only an
aggressive 20 % client discount with a zero driver gap fails for a large share.

## External territories — bracket only (NOT a price)

`data/interim/zone-external-bracket-scenarios-v1.csv`: per territory × city_rate
(5/6/7) × outside_rate (8–12) × min_fare (15/18/20/25), a lower bracket (whole
route at the city rate) and an upper bracket (whole route at the outside rate),
each `RANGE_ONLY_NOT_TARIFF`. Never a tariff, never a threshold.
