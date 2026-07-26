# Yandex address inventory comparison v1 — PARTIAL EVIDENCE ONLY

## Result

**INCONCLUSIVE / PARTIAL_EVIDENCE_ONLY.** The audit now contains 153 forward
observations, including 117/2,565 canonical sample rows, and 35/316 reverse street
groups. Ten groups reached `COMPLETE_FOR_VISIBLE_MAP`, but coverage and statistical
power remain insufficient for a full Yandex address estimate.

| Evidence layer | Current evidence | Counting rule |
|---|---|---|
| Canonical population | 9,216 immutable address grains | Existing denominator; unchanged |
| Canonical sample | 117 reviewed of 2,565 | Weighted checkpoint evidence only |
| Recovered exclusions | 36/36 reviewed | Separate layer; no automatic addition |
| Yandex-only observations | 7 HIGH, 0 MEDIUM | Observed lower bound only; owner review required |
| Reverse audit | 35 reviewed, 10 complete | Partial visible-map coverage |
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

Canonical 9,216, address IDs and coordinates, existing exclusions, zones,
thresholds, Kishinevskaya, Severny/Varnita data, routing graph and restrictions,
Direct, prices, tariff matrix, and immutable releases remain unchanged.
