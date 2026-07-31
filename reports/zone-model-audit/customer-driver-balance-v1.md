# Customer / driver balance v1

City addresses only (4,866; owner assumptions). External territories carry a
bracket, not a price. Full sensitivity grid:
`data/interim/zone-economics-scenarios-v1.csv` (5,184 rows). Exact per-zone prices
for the three policies: `data/interim/zone-policy-prices-v1.csv`.

## Commission benchmark — corrected

`driver_best_taxi_take = max(taxi_reference - 5, 0.65 × taxi_reference)`.

The two models cross over at `taxi_reference = 5 / 0.35 = 14.29 руб`. Because the
minimum fare is 18 руб, **every** city taxi_reference is ≥ 18 > 14.29, so the
fixed-5 model wins for **100 % (4,866 / 4,866)** of city trips. The correct driver
benchmark is therefore **`taxi_reference − 5`** in every zone — *not*
`0.65 × taxi_reference`. (An earlier draft wrongly attributed the balanced fee to
the 65 % platform; that is fixed here.)

## The current flat 25 руб — policy-specific (city, 4,866)

| Test | Addresses | Share |
|---|---:|---:|
| Client overpays (25 > equivalent taxi) | 3,191 | 65.6 % |
| Driver gap > 2 руб | 490 | 10.1 % |
| Driver gap > 3 руб | 355 | 7.3 % |
| Driver gap > 5 руб | 131 | 2.7 % |
| Driver gap > 10 % | 381 | 7.8 % |
| Driver gap > 15 % | 189 | 3.9 % |

A flat 25 руб is dearer than an equivalent taxi for **two thirds** of city
addresses (the near zones), and leaves the driver more than 5 руб short on only
2.7 %. It behaves like a "far-zone" price applied to everyone.

## Three price policies (example: CITY_K5R natural breaks, руб.)

Thresholds 1.975 / 3.075 / 4.175 / 5.175 km; zone city counts 1302 / 1083 / 807 /
1028 / 646.

| Policy | Zone fees | Driver-gap rule |
|---|---|---|
| DRIVER_CONSERVATIVE | 13 / 14 / 17 / 24 / 28 | gap ≤ 2 руб |
| BALANCED | 12 / 13 / 16 / 23 / 27 | gap ≤ 3 руб and ≤ 10 % |
| CUSTOMER_FIRST | 15 / 16 / 18 / 24 / 28 | gap ≤ 5 руб and ≤ 15 % |

Note: in the near zones the taxi reference is pinned at the 18 руб floor, so all
three policies converge to ~12–16 руб there; the policies separate only in the
farther zones. Every fee is integer, monotone and below the equivalent taxi
(joint constraint coverage per zone is in the policy CSV).

## Sensitivity (feasibility envelope, owner baseline city 6 / min 18 / fixed 5)

Under the owner's own assumptions almost any modest discount keeps both sides
satisfied; only an aggressive 20 % client discount with a zero driver gap fails
(≈ 66 % of addresses). Full grid in the scenarios CSV.

## External territories — bracket only (NOT a price)

No proven city/outside split. `data/interim/zone-external-bracket-scenarios-v1.csv`
gives, per territory × city_rate(5/6/7) × outside_rate(8–12) × min_fare(15/18/20/25),
a lower bracket (whole route at the city rate) and an upper bracket (whole route
at the outside rate), each `RANGE_ONLY_NOT_TARIFF`. These are never used as a
tariff or a threshold. The owner must confirm the external boundary on a map first.
