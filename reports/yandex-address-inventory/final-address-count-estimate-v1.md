# Yandex address inventory comparison v1 — PARTIAL

## Result

**INCONCLUSIVE.** The prepared sample meets the size and deterministic-coverage design
requirements, but only 3 of 2,565 sampled addresses have been inspected and no street
has completed the reverse audit. An estimate of the full Yandex address count would be
unsupported.

The clarified destination rule has been applied to the audit model: addressed medical,
educational, industrial, warehouse, retail, office, public, and other real destinations
are deliverable. The current release does not retain enough facility metadata to
measure those categories, and 34 potentially deliverable non-residential address nodes
were excluded upstream. Category zeros below mean “not attributable from retained
evidence,” not “absent from the delivery territory.”

| Requested result | Current evidence |
|---|---|
| Canonical population | 9,216 unique addresses |
| DELIVERABLE | 9,078 |
| NON_DELIVERABLE_STRUCTURE | 0 confirmed |
| UNKNOWN_REQUIRES_REVIEW | 138 |
| Sample prepared / reviewed | 2,565 / 3 |
| Unique streets reviewed | 3 of 316 groups represented in the sample |
| EXACT_MATCH | 3 |
| NORMALIZED_EQUIVALENT | 0 |
| NEARBY_ADDRESS_ONLY | 0 |
| Address disagreements | 0 observed |
| NOT_FOUND | 0 observed |
| NON_DELIVERABLE_STRUCTURE in browser review | 0 observed |
| Weighted exact+normalized rate | 100% checkpoint-only |
| Wilson 95% interval | 43.85%–100% checkpoint-only |
| Estimated canonical addresses confirmed by Yandex | withheld; insufficient review |
| HIGH-confidence Yandex-only addresses | 0 observed |
| Observed lower bound of extras | 0 |
| Estimated Yandex-only uplift | unavailable |
| Estimated full normal Yandex address range | unavailable |
| Comparison with 9,216 | INCONCLUSIVE |

## Facility coverage is residential-only in retained metadata

| Facility category | Attributable addresses in current 9,216 | Evidence status |
|---|---:|---|
| RESIDENTIAL | 9,078 | Retained as addressed residential buildings |
| MEDICAL | 0 | Facility tags unavailable; count not measurable |
| EDUCATION | 0 | Facility tags unavailable; count not measurable |
| INDUSTRIAL | 0 | Facility tags unavailable; count not measurable |
| WAREHOUSE | 0 | Facility tags unavailable; count not measurable |
| RETAIL / FOOD_SERVICE / OFFICE | 0 | Facility tags unavailable; count not measurable |
| GOVERNMENT / PUBLIC_SERVICE | 0 | Facility tags unavailable; count not measurable |
| HOSPITALITY / RELIGIOUS / SPORTS / TRANSPORT / OTHER_DELIVERABLE | 0 | Not measurable |
| NON_DELIVERABLE_AUXILIARY | 0 confirmed inside the 9,216 | Detailed tags unavailable |
| UNKNOWN | 138 | Address exists; object/facility evidence is insufficient |

Outside this denominator, the upstream exceptions contain 34 address nodes excluded
only as generic non-residential, one outbuilding, and one abandoned/ruin. The 34 must
be recovered and reviewed against the source dataset before any facility-category or
total-address comparison is decision-ready.

## Owner review

The 138 `UNKNOWN_REQUIRES_REVIEW` rows remain in scope. Three of them have now shown an
exact Yandex building result; 135 remain unreviewed. Known discrepancy proxies remain
mandatory in the prepared sample. No canonical row is edited by this audit.

There is no ranked discrepancy-street list yet: the three reviewed street groups had
no address disagreement. The complete owner-review address list is the 138 rows with
`manual_review_required=True` in
`data/interim/canonical-deliverable-address-classification-v1.csv`; embedding all rows
again in this report would create a second source of truth.

## Limitations

- Yandex does not provide a complete licensed address export in this workflow.
- The browser checkpoint is far below the 1,000-reviewed-address sufficiency rule.
- Reverse coverage is zero, so the absence of observed extras has no completeness
  meaning.
- Retained release metadata cannot distinguish garages, sheds, construction, or
  technical buildings; unclear rows are not silently excluded.
- Retained release metadata cannot distinguish medical, education, industrial,
  warehouse, retail, government, or other legitimate destination categories.
- Thirty-four potentially deliverable address nodes were excluded by the old generic
  non-residential rule and lack the address fields needed for safe restoration here.
- Северный is not part of the canonical 9,216-row release population.
- District and development-type metadata is incomplete, and terminal-branch evidence
  is unavailable on the specified base commit.

The canonical address base, IDs, coordinates, exclusions, territory assignments,
zones, thresholds, Kishinevskaya, Severny/Varnita data, routing graph, OSM/PBF,
immutable releases, Direct, prices, and tariff matrix were not changed.

## Recommended next steps

1. Recover the pinned `moldova-pbf:09ba0c058e89` source or an equivalently
   checksummed tag extract and rejoin building, amenity, shop, office, industrial,
   tourism, leisure, facility name, and address tags by OSM ID.
2. Review the 34 generic non-residential exclusions as candidate delivery
   destinations; keep the outbuilding and abandoned/ruin cases separate.
3. Produce a non-mutating candidate-address comparison before proposing any change
   to canonical IDs, exclusions, territory assignments, zones, or releases.
4. Continue the manual Yandex forward and reverse batches from the existing
   checkpoint. Facility categories may be promoted from UNKNOWN only with retained
   source evidence or an explicit manual observation.

## Open questions

- Which of the 34 excluded non-residential nodes had a complete official street and
  house number in the pinned source?
- Which represent independent delivery addresses or entrances rather than internal
  building parts?
- How many named facilities without house numbers are uniquely selectable delivery
  destinations and should enter a future candidate inventory as owner-review rows?
