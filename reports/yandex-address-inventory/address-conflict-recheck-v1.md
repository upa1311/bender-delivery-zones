# Canonical address conflict recheck v1

Status: **COMPLETE FOR THE 69 EXISTING CANONICAL CONFLICT ROWS**

Every canonical row whose original status was `DIFFERENT_HOUSE_NUMBER`,
`DIFFERENT_STREET`, `NEARBY_ADDRESS_ONLY`, `SETTLEMENT_ONLY`, `NOT_FOUND`, or
`AMBIGUOUS_REQUIRES_REVIEW` was rechecked in the visible Yandex Maps interface on
2026-07-27. Each review used a full address query, an alternative spelling/order,
and the canonical coordinates. Original observations were not overwritten.

| Resolution | Count |
|---|---:|
| YANDEX_NEAREST_RESULT_ONLY | 36 |
| CANONICAL_COORDINATE_ANCHOR_ERROR_SUSPECTED | 16 |
| CANONICAL_ADDRESS_NOT_VISIBLE_IN_YANDEX | 10 |
| LETTER_SUFFIX_DIFFERENCE | 4 |
| STREET_RENAME_OR_VARIANT | 2 |
| SETTLEMENT_LABEL_DIFFERENCE | 1 |
| EXACT_MATCH_ON_RECHECK | 0 |
| HOUSE_NUMBER_RENUMBERING | 0 |

An opened nearest house is evidence of substitution, not proof that the requested
canonical number is absent. Canonical records were not edited automatically.
