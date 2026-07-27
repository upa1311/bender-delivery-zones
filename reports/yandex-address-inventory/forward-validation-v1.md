# Forward Yandex address validation v1 — PARTIAL

The free visible Yandex Maps interface was used interactively. Each of the 267
probability-review canonical addresses was searched separately and its visible
result was recorded. No
Yandex API, bulk HTTP collection, scraping, OSRM substitution, neighbouring-address
copy, or invented result was used.

## Progress

| Population | Prepared | Before | After |
|---|---:|---:|---:|
| Canonical 9,216 sample | 2,565 | 117 targeted | 384 including 267 probability rows |
| Recovered exclusion candidates | 36 | 36 | 36 |
| Combined forward observations | — | 153 | 420 |

The recovered rows remain a separate evidence layer and do not receive sampling
weights. The original 53 observations, including YAV-0001 through YAV-0003, are
unchanged.

| Match status | Count |
|---|---:|
| EXACT_MATCH | 175 |
| NORMALIZED_EQUIVALENT | 6 |
| FACILITY_MATCH_WITH_ADDRESS | 7 |
| FACILITY_MATCH_WITHOUT_HOUSE_NUMBER | 0 |
| NEARBY_ADDRESS_ONLY | 2 |
| DIFFERENT_STREET | 8 |
| DIFFERENT_HOUSE_NUMBER | 130 |
| SETTLEMENT_ONLY | 9 |
| NOT_FOUND | 0 |
| NON_DELIVERABLE_STRUCTURE | 1 |
| DUPLICATE_EXISTING_ADDRESS | 16 |
| AMBIGUOUS_REQUIRES_REVIEW | 66 |

There are 138 explicit address disagreements: 8 different-street and 130
different-house observations. Facility matches remain real delivery evidence but do
not automatically create new address grains.

For the 117 canonical observations only, the weighted exact+normalized rate is
39.29%, with a Wilson 95% interval of 30.58%–48.73%. This is checkpoint evidence,
not a population estimate: the review is far below 1,000 and includes mandatory,
non-random strata.

The independently selected probability subset has 300 linked observations. Its
descriptive unweighted exact+normalized rate is 48.00%, and the corrected two-phase
Hájek estimate is 51.98%. A design-based interval remains unavailable pending a
completed probability review. This is not a final exact count for all 9,216
addresses.
