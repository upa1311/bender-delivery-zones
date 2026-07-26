# Recovered candidate owner review v1

Fifteen recovered `DELIVERABLE_CANDIDATE` rows were reviewed against the existing
manual Yandex evidence. This file records recommendations for the owner; it does not
make final business decisions or change the canonical release.

| Decision | Count | Meaning |
|---|---:|---|
| APPROVE_FOR_FUTURE_RELEASE | 6 | Address/facility evidence supports later owner-approved inclusion |
| REJECT_DUPLICATE | 1 | The address grain already exists canonically |
| HOLD_ADDRESS_CONFLICT | 5 | Street, number, or facility address conflicts remain |
| HOLD_OPERATIONAL_STATUS | 1 | A visible closed label requires owner resolution |
| HOLD_INSUFFICIENT_EVIDENCE | 2 | Only nearby or otherwise incomplete evidence exists |

The row-level evidence and recommendation are in
`data/interim/recovered-candidate-owner-review-v1.csv`. Six recommendations support a
future mutable release, but none is applied here.
