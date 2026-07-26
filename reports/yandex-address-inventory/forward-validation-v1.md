# Forward Yandex address validation v1 — PARTIAL

The free visible Yandex Maps interface was used interactively. Every new object was
searched separately and its visible address or organization card was inspected. No
Yandex API, bulk HTTP collection, scraping, OSRM substitution, or copied neighbouring
result was used.

## Progress

| Population | Prepared | Reviewed | Remaining |
|---|---:|---:|---:|
| Canonical 9,216 sample | 2,565 | 17 | 2,548 |
| Recovered exclusion candidates | 36 | 36 | 0 |
| Combined forward observations | — | 53 | — |

This run added 14 canonical observations and 36 recovered-candidate observations: 50
new browser observations. The recovered rows do not receive sampling weights and do
not count toward canonical statistical sufficiency.

| Match status | Count |
|---|---:|
| EXACT_MATCH | 7 |
| NORMALIZED_EQUIVALENT | 0 |
| FACILITY_MATCH_WITH_ADDRESS | 7 |
| FACILITY_MATCH_WITHOUT_HOUSE_NUMBER | 0 |
| NEARBY_ADDRESS_ONLY | 2 |
| DIFFERENT_STREET | 1 |
| DIFFERENT_HOUSE_NUMBER | 15 |
| SETTLEMENT_ONLY | 3 |
| NOT_FOUND | 0 |
| NON_DELIVERABLE_STRUCTURE | 1 |
| DUPLICATE_EXISTING_ADDRESS | 16 |
| AMBIGUOUS_REQUIRES_REVIEW | 1 |

The explicit address disagreements are 1 different-street and 15 different-house
observations. The seven facility matches show real deliverable destinations, but do
not automatically add a new address when the address grain is already canonical.

For the 17 canonical observations only, the weighted exact+normalized rate is 32.98%
and the effective-sample Wilson 95% interval is 14.79%–58.23%. This is checkpoint
evidence, not a population estimate: canonical review remains far below 1,000 and the
mandatory and deterministic selections are not a simple random sample.

YAV-0001 through YAV-0003 retain their original evidence unchanged; the schema-only
population fields do not alter those observations.
