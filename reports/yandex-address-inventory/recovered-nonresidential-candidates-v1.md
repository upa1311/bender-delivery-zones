# Recovered non-residential address candidates v1

Status: **SOURCE RECOVERY COMPLETE; OWNER REVIEW RECORDED; RELEASE UNCHANGED**

All 36 legacy exclusions were recovered from the SHA-256 verified pinned PBF. The
recovery remains 15 `DELIVERABLE_CANDIDATE`, 20 `DUPLICATE_EXISTING_ADDRESS`, and 1
`NON_DELIVERABLE_LIFECYCLE`; no source record is blocked.

The 15 deliverable candidates were compared with their existing manual Yandex
evidence and recorded in `recovered-candidate-owner-review-v1.csv`:

| Recommendation | Count |
|---|---:|
| APPROVE_FOR_FUTURE_RELEASE | 6 |
| REJECT_DUPLICATE | 1 |
| HOLD_ADDRESS_CONFLICT | 5 |
| HOLD_OPERATIONAL_STATUS | 1 |
| HOLD_INSUFFICIENT_EVIDENCE | 2 |
| REJECT_NON_DELIVERABLE | 0 |

An approval recommendation is not a final owner decision. None of these rows was
inserted into the protected canonical address base or an immutable release. Address,
street, and operational conflicts remain explicit rather than being resolved by
assumption.
