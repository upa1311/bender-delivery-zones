# Forward Yandex address validation v1 — PARTIAL

The free visible Yandex Maps interface was used interactively. Each of the 100 new
canonical addresses was searched separately and its visible result was recorded. No
Yandex API, bulk HTTP collection, scraping, OSRM substitution, neighbouring-address
copy, or invented result was used.

## Progress

| Population | Prepared | Before | After |
|---|---:|---:|---:|
| Canonical 9,216 sample | 2,565 | 117 targeted | 217 including 100 probability rows |
| Recovered exclusion candidates | 36 | 36 | 36 |
| Combined forward observations | — | 153 | 253 |

The recovered rows remain a separate evidence layer and do not receive sampling
weights. The original 53 observations, including YAV-0001 through YAV-0003, are
unchanged.

| Match status | Count |
|---|---:|
| EXACT_MATCH | 95 |
| NORMALIZED_EQUIVALENT | 5 |
| FACILITY_MATCH_WITH_ADDRESS | 7 |
| FACILITY_MATCH_WITHOUT_HOUSE_NUMBER | 0 |
| NEARBY_ADDRESS_ONLY | 2 |
| DIFFERENT_STREET | 1 |
| DIFFERENT_HOUSE_NUMBER | 83 |
| SETTLEMENT_ONLY | 7 |
| NOT_FOUND | 0 |
| NON_DELIVERABLE_STRUCTURE | 1 |
| DUPLICATE_EXISTING_ADDRESS | 16 |
| AMBIGUOUS_REQUIRES_REVIEW | 36 |

There are 84 explicit address disagreements: 1 different-street and 83
different-house observations. Facility matches remain real delivery evidence but do
not automatically create new address grains.

For the 117 canonical observations only, the weighted exact+normalized rate is
39.29%, with a Wilson 95% interval of 30.58%–48.73%. This is checkpoint evidence,
not a population estimate: the review is far below 1,000 and includes mandatory,
non-random strata.

The independently selected probability subset has 133 linked observations. Its
unweighted exact+normalized rate is 47.37% (Wilson 95%: 39.08%–55.81%) and its
design-weighted rate is 55.13%. Fewer than 300 probability addresses have been
reviewed, so this is not a final estimate for all 9,216 addresses.
