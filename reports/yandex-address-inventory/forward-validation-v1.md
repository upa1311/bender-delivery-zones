# Forward Yandex address validation v1 — PARTIAL

The free visible Yandex Maps interface was used interactively. Each processed sample
was searched separately and its address card and map were visually inspected. No API,
scraping, protection bypass, OSRM substitution, or copied neighbouring result was used.

| Metric | Checkpoint value |
|---|---:|
| Prepared sample | 2,565 |
| Processed | 3 |
| Remaining | 2,562 |
| Unique street groups processed | 3 |
| EXACT_MATCH | 3 |
| NORMALIZED_EQUIVALENT | 0 |
| NEARBY_ADDRESS_ONLY | 0 |
| DIFFERENT_STREET | 0 |
| DIFFERENT_HOUSE_NUMBER | 0 |
| SETTLEMENT_ONLY | 0 |
| NOT_FOUND | 0 |
| NON_DELIVERABLE_STRUCTURE | 0 |
| AMBIGUOUS_REQUIRES_REVIEW | 0 |

The three coordinate differences are 1.6 m, 32.6 m, and 27.8 m. All three visible
cards represented addressed buildings. Organizations displayed inside the second
building were not counted as additional addresses.

The checkpoint weighted exact+normalized rate is 100%. With three equal-weight
observations, the effective-sample Wilson 95% interval is 43.85%–100%. This is a
descriptive checkpoint only: 3/2,565 reviewed rows do not support extrapolation to the
9,216-row population. Territory-, street-, and building-type estimates are withheld.
