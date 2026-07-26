# Non-deliverable structures audit v1 — PARTIAL

The immutable canonical registry still contains 9,216 address grains: 9,078
`DELIVERABLE`, zero source-confirmed `NON_DELIVERABLE_STRUCTURE`, and 138
`UNKNOWN_REQUIRES_REVIEW`. Detailed auxiliary-building tags were not retained in that
release, so zero is not evidence that such structures do not exist.

The exact pinned source was recovered for all 36 legacy
`address_inside_nonresidential_building` exclusions. Generic non-residential geometry
was not treated as evidence of non-deliverability.

| Recovery classification | Count |
|---|---:|
| DELIVERABLE_CANDIDATE | 15 |
| DUPLICATE_EXISTING_ADDRESS | 20 |
| NON_DELIVERABLE_AUXILIARY | 0 |
| NON_DELIVERABLE_LIFECYCLE | 1 |
| UNKNOWN_REQUIRES_REVIEW | 0 |

The lifecycle result, REC-011 at Славянская улица 64, is classified from explicit
source lifecycle evidence and was also not shown as a normal addressed building in
the manual Yandex review. The legacy outbuilding row REC-001 has a distinct recovered
address and a retail/fuel destination, so it is not automatically discarded merely
because its old unit type contained `outbuilding`.

Medical, industrial, retail, office, hospitality, food-service, government, and
public-service destinations remain legitimate delivery candidates when they have a
separate address or delivery entrance. No canonical file, exclusion, or immutable
release was changed.
