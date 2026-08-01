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

**BALANCED enforces client_saving >= 5 руб** for 100 % of a zone (the 1-руб /
target_save bug is removed). Full detail: `data/interim/zone-policy-prices-v1.csv`;
per-rounding: `data/interim/zone-operational-policy-prices-v1.csv`. These are all
**city** zones (ближние/средние/дальние городские), never external territories.

CITY_K5R raw (thresholds 1.675 / 2.875 / 4.125 / 5.325 km):

| Policy | z1 near | z2 near | z3 mid | z4 far | z5 far |
|---|---|---|---|---|---|
| DRIVER_CONSERVATIVE | 12 ✅ | 12 ✅ | INF (fb 17, 87 %) | INF (24, 86 %) | INF (31, 78 %) |
| BALANCED | 12 ✅ | 12 ✅ | INF (15, 30 %) | INF (21, 38 %) | INF (27, 49 %) |
| CUSTOMER_FIRST | 12 ✅ | 12 ✅ | INF (15, 42 %) | INF (20, 55 %) | INF (27, 67 %) |

CITY_K4R raw (1.725 / 3.275 / 4.975): DRIVER 12/13 feasible (z1–z2), CUSTOMER 12/13,
**BALANCED feasible only z1 (12); z2 INFEASIBLE** (min taxi 18, fee 14 would give
only 4 руб saving < 5). z3–z4 INFEASIBLE all policies.

Operational 0.25 km recompute is independent, not copied: e.g. CITY_K5 0.25 makes
**DRIVER_CONSERVATIVE z3 FEASIBLE at 17** where raw z3 was infeasible.

Why mid/far city zones are infeasible: within a wide zone the taxi reference spans
a large range (e.g. K5 z5: 32–45 руб), so the fee the far end needs to keep the
driver whole exceeds the fee the near end needs to still save the client ≥ 5 руб —
the driver floor rises above the client ceiling. No single flat fee satisfies 100 %.

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
