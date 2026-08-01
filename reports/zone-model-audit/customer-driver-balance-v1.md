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

## Price policies — feasibility-proven over ALL zone addresses

Each zone has a proven feasibility interval `[minimum_fee_required_by_driver,
maximum_fee_allowed_by_client]` computed over **every** address (not the median).
A policy zone is `FEASIBLE` only if that interval is non-empty; the fee is then the
lowest integer in it (max client saving), monotone across zones **without** any
post-hoc clamp that breaks a constraint. If the interval is empty the zone is
`INFEASIBLE` and gets a separate `fallback_fee_rub` (labelled
`FALLBACK_PARTIAL_COVERAGE`), never a "satisfied policy" price.

**Result (100 %-coverage hard constraints): only the two near zones are FEASIBLE.**
Full detail: `data/interim/zone-policy-prices-v1.csv`.

CITY_K5R (thresholds 1.675 / 2.875 / 4.125 / 5.325 km):

| Policy | z1 | z2 | z3 | z4 | z5 |
|---|---|---|---|---|---|
| DRIVER_CONSERVATIVE | 12 ✅ | 12 ✅ | INFEASIBLE (fb 17, 87 %) | INFEASIBLE (24, 86 %) | INFEASIBLE (31, 78 %) |
| BALANCED | 12 ✅ | 12 ✅ | INFEASIBLE (17, 86 %) | INFEASIBLE (24, 94 %) | INFEASIBLE (31, 84 %) |
| CUSTOMER_FIRST | 12 ✅ | 12 ✅ | INFEASIBLE (15, 42 %) | INFEASIBLE (20, 55 %) | INFEASIBLE (27, 67 %) |

CITY_K4R (1.725 / 3.275 / 4.975): feasible z1–z2 (DRIVER 12/14, BALANCED 12/14,
CUSTOMER 12/13); z3–z4 INFEASIBLE (fallback coverage 48–77 %). Near-zone fees are
unified upward by the CUSTOMER ≤ BALANCED ≤ DRIVER order, within each ceiling.

Why the outer zones are infeasible: within a wide outer zone the taxi reference
spans a large range (e.g. K5 z5: 32–45 руб), so the fee the far end needs to keep
the driver whole exceeds the fee the near end needs to still save the client — the
driver floor rises above the client ceiling. No single flat fee can satisfy 100 %.

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
