# Yandex address inventory comparison v1 — PARTIAL EVIDENCE ONLY

## Result

**INCONCLUSIVE / PARTIAL_EVIDENCE_ONLY.** The audit now contains 420 forward
observations: 384 canonical addresses and 36 recovered candidates. The independent
probability sample has 300/400 linked observations (267 newly reviewed), and the
reverse audit covers 143/316 street groups, 25 completely for the visible map.

| Evidence layer | Current evidence | Counting rule |
|---|---|---|
| Canonical population | 9,216 immutable address grains | Existing denominator; unchanged |
| Targeted canonical sample | 117 reviewed of 2,565 | Diagnostic evidence only |
| Probability sample | 300 reviewed of 400 | 48.00% descriptive unweighted; corrected two-phase Hájek estimate 51.98%; interval unavailable pending completed review |
| Recovered exclusions | 36/36 reviewed | Separate layer; no automatic addition |
| Yandex-only observations | 7 HIGH, 0 MEDIUM | Observed lower bound only; owner review required |
| Reverse audit | 143 reviewed, 25 complete | Partial visible-map coverage |
| Number reconciliation | 7 gross Yandex-only; 5 gross canonical-only; 4 paired substitutions; 2 confirmed additions; 1 unresolved | Known provisional net 2; unresolved row excluded; not a city total |
| Recovered owner review | 15 recommendations | No final owner decision made |

The canonical classification still contains 9,078 `RESIDENTIAL` rows and 138
`UNKNOWN_REQUIRES_REVIEW` rows. Recovered evidence continues to expose the
`MEDICAL`, `EDUCATION`, `INDUSTRIAL`, and `WAREHOUSE` facility categories without
turning non-residential use into an automatic exclusion.

The 15 owner-review recommendations are: 6 `APPROVE_FOR_FUTURE_RELEASE`, 1
`REJECT_DUPLICATE`, 5 `HOLD_ADDRESS_CONFLICT`, 1 `HOLD_OPERATIONAL_STATUS`, and 2
`HOLD_INSUFFICIENT_EVIDENCE`. These are recommendations only and do not modify any
release.

Estimated full normal Yandex address range | unavailable

Known provisional net effect: 2. One reconciliation remains unresolved and is excluded from the numeric net effect.

Canonical 9,216, address IDs and coordinates, existing exclusions, zones,
thresholds, Kishinevskaya, Severny/Varnita data, routing graph and restrictions,
Direct, prices, tariff matrix, and immutable releases remain unchanged.
