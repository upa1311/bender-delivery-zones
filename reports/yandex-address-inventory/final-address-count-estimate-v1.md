# Yandex address inventory comparison v1 - PARTIAL EVIDENCE ONLY

## Result

**INCONCLUSIVE / PARTIAL_EVIDENCE_ONLY.** The audit now has 53 forward observations
and an initial reverse review of 10 street groups, but only 17/2,565 canonical sample
rows have been reviewed and no street group has complete reverse coverage. Publishing
an exact or estimated full Yandex address total would be unsupported.

## Strictly separated evidence layers

| Layer | Current evidence | Counting rule |
|---|---|---|
| 1. Canonical population | 9,216 immutable address grains | Existing release denominator; unchanged |
| 2. Recovered exclusions | 36/36 source records recovered: 15 candidates, 20 duplicates, 1 lifecycle object | Separate audit layer; no automatic canonical addition |
| 3. Yandex-only observations | 1 HIGH and 6 MEDIUM candidates | Observed candidates only; owner approval required |
| 4. Non-deliverable structures | 1 explicit recovered lifecycle object; 0 confirmed in retained canonical metadata | Exclude only with positive evidence |
| 5. Unresolved facilities without official address | Conflicting or incomplete evidence remains in forward rows and owner-review flags | Do not add or exclude automatically |

## Forward evidence

| Metric | Current value |
|---|---:|
| Canonical sample prepared / reviewed | 2,565 / 17 |
| Recovered candidates reviewed | 36 / 36 |
| Combined forward processed | 53 |
| EXACT_MATCH | 7 |
| NORMALIZED_EQUIVALENT | 0 |
| Facility matches with address | 7 |
| Explicit address disagreements | 16 |
| NOT_FOUND | 0 |
| Canonical-only weighted exact+normalized rate | 32.98% checkpoint-only |
| Wilson 95% interval | 14.79%–58.23% checkpoint-only |

## Recovered facility evidence

The 36 recovered records include 3 MEDICAL, 0 EDUCATION, 4 INDUSTRIAL, 0 WAREHOUSE,
12 RETAIL, 2 OFFICE, 2 GOVERNMENT, 4 PUBLIC_SERVICE, 6 FOOD_SERVICE, 1 HOSPITALITY,
and 2 UNKNOWN source categories. At the unique address-grain level, 15 remain
`DELIVERABLE_CANDIDATE`; 20 are duplicates and one is lifecycle non-deliverable.

These numbers describe the known legacy exclusion set, not the complete facility
population. Potential additions require owner review and a future mutable release;
none was inserted into the protected release here.

The retained canonical metadata still labels 9,078 rows as `RESIDENTIAL`. The
recovered layer explicitly reports `MEDICAL`, `EDUCATION`, `INDUSTRIAL`, and
`WAREHOUSE` categories without pretending they describe the full territory.

## Reverse evidence and limitations

Ten of 316 street groups were partially reviewed. Советская улица 31 is the only
HIGH-confidence Yandex-only address because it was independently searched twice and
is absent from canonical and recovered keys. Six other concrete candidates remain
MEDIUM. No group is complete, so reverse coverage cannot support an uplift estimate.

Estimated full normal Yandex address range | unavailable

The canonical database, all 9,216 IDs and coordinates, existing exclusions, zones,
thresholds, Kishinevskaya, Severny/Varnita data, routing graph and restrictions,
Direct, prices, tariff matrix, and immutable releases were not changed.
