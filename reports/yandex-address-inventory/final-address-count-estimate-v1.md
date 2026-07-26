# Yandex address inventory comparison v1 — PARTIAL

## Result

**INCONCLUSIVE.** The prepared sample meets the size and deterministic-coverage design
requirements, but only 3 of 2,565 sampled addresses have been inspected and no street
has completed the reverse audit. An estimate of the full Yandex address count would be
unsupported.

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
- Северный is not part of the canonical 9,216-row release population.
- District and development-type metadata is incomplete, and terminal-branch evidence
  is unavailable on the specified base commit.

The canonical address base, IDs, coordinates, exclusions, territory assignments,
zones, thresholds, Kishinevskaya, Severny/Varnita data, routing graph, OSM/PBF,
immutable releases, Direct, prices, and tariff matrix were not changed.
