# High-divergence root-cause audit

This audit compares the completed manual Yandex street order with a fresh route
from the local OSRM MLD graph. It does not infer a defect merely because the two
engines choose different streets. OSM node identifiers below come from the OSRM
route annotations; the complete ordered node chain is retained in
`router-baseline-v1.csv`.

## Evidence standard and result

- All 86 primary controls are routable; there are no disconnected results.
- Origin snap is stable at 33.23 m. Only MY-071 has a destination snap above the
  60 m review threshold (73.06 m).
- The observed Yandex corridors are present as legal alternatives in the road
  network evidence, but a street name or a different vendor choice does not prove
  a missing edge, wrong access, one-way error, turn error, or bad weight.
- No concrete unsafe access, false junction, missing real junction, incorrect
  one-way, or incorrect turn restriction was established for the audited cases.
- Consequently no graph mutation is implemented. The rejected alternatives are
  per-control overrides, global street-name forcing, synthetic connectors, and
  unverified speed/access edits.

## Required high-divergence cases

| control | router / Yandex km | our fresh route | manual Yandex order | divergence point and concrete evidence | root cause | proposed action | risk | confidence |
|---|---:|---|---|---|---|---|---|---|
| MY-002 | 6.5654 / 4.8280 | Лазо → Коммунистическая → Ечина → Бендерского Восстания → Кишинёвская | Лазо → Суворова → Ленина → Котовского → Панина → Р2 → Петровского → Зои Космодемьянской → Титова → Кишинёвская | Routes diverge after Лазо. Destination nodes 346864409 → 2334338355 → 3221451783 are reachable, but Yandex labels the same supplied point as house 13 while our control is house 1. | ADDRESS_ANCHOR_AMBIGUOUS | Resolve the house anchor; do not edit the graph. | High | High |
| MY-X01 | 3.5099 / 4.5384 | Лазо → Суворова → Ленина → Котовского → Р2 → Титова | Лазо → Суворова → Ленина → Котовского → Панина → Р2 → Петровского → Зои Космодемьянской → Бельцкая | Both use the northern corridor; Yandex adds a longer loop. Destination evidence 457637388 → 517234914 → 6807662286. | ROUTER_CHOOSES_DIFFERENT_VALID_ROUTE | Keep both legal routes; no forced detour. | High | High |
| MY-X02 | 0.4470 / 0.5633 | Лазо → Суворова | Лазо → Суворова | Street chain agrees. The conflict is our “Московская 42” versus Yandex “Суворова 42”; nodes 3585608293 → 6367515248 → 514211062. | ADDRESS_ANCHOR_AMBIGUOUS | Owner address review. | High | High |
| MY-018 | 3.6598 / 5.1499 | Лазо → Суворова → 40 лет МССР | Лазо → Суворова → 40 лет МССР → Мира → Кирова → 40 лет МССР | Yandex leaves and returns to 40 лет МССР. Our address says Суворова 79 while Yandex says 40 лет МССР 79; destination nodes 1303507101 → 1303506415 → 950490820. | ADDRESS_ANCHOR_AMBIGUOUS | Resolve street anchor before routing changes. | High | High |
| MY-019 | 3.7429 / 4.9890 | Лазо → Суворова → 40 лет МССР | Лазо → Суворова → 40 лет МССР → Мира → Кирова → 40 лет МССР | Same loop pattern as MY-018; Yandex label is 40 лет МССР 85 for our Суворова 87. Nodes 1303506415 → 950490820 → 2315990668. | ADDRESS_ANCHOR_AMBIGUOUS | Resolve street and house anchor. | High | High |
| MY-020 | 3.7540 / 4.9890 | Лазо → Суворова → 40 лет МССР | Лазо → Суворова → 40 лет МССР → Мира → Кирова → 40 лет МССР | Same connected loop; Yandex label is 40 лет МССР 87 for our Суворова 89. Nodes 1303506415 → 950490820 → 2315990668. | ADDRESS_ANCHOR_AMBIGUOUS | Resolve street and house anchor. | High | High |
| MY-005 | 4.6932 / 4.0716 | Лазо → Коммунистическая → Ленина → Первомайская → Студенческая | Лазо → Суворова → Первомайская → Коммунистическая → Студенческая | Divergence starts at the origin approach; both chains reach Студенческая. Destination nodes 12541704219 → 12541704221 → 12541704223. No failed edge or restriction is observed. | ROUTER_CHOOSES_DIFFERENT_VALID_ROUTE | Review vendor speed assumptions only with independent evidence. | High | Medium |
| MY-054 | 6.4612 / 5.6327 | Лазо → Коммунистическая → Ечина → Бендерского Восстания → Старого → Гербовецкая → Главная → Главный → Штефан чел Маре | Лазо → Суворова → Первомайская → Коммунистическая → Ечина → Протягайловская → Главный → Штефан чел Маре | Both corridors exist; the difference begins before Ечина and later at Протягайловская versus Гербовецкая/Главная. Destination nodes 760367282 → 760367168 → 3583919643. Street presence is not weight evidence. | ROUTER_CHOOSES_DIFFERENT_VALID_ROUTE | Inspect speed/access tags only if independently contradicted. | High | Medium |
| MY-063 | 7.4577 / 5.7936 | Лазо → Коммунистическая → Ечина → Бендерского Восстания → Кишинёвская → Деповская | Лазо → Суворова → Ленина → Котовского → Панина → Р2 → Ермакова → Титова → Кишинёвская | Yandex uses the northern bridge/rail corridor; OSRM uses the connected southern corridor. Destination nodes 6782017652 → 3330066658 → 2337982000. Both are routable; no missing crossing is proven. | ROUTER_CHOOSES_DIFFERENT_VALID_ROUTE | Keep both; separate speed-model review from graph topology. | High | Medium |
| MY-065 | 1.3123 / 1.4645 | Лазо → Коммунистическая → Московская | Лазо → Академика Фёдорова → Московская | Routes diverge immediately but converge on Московская; nodes 4004122794 → 4004122793 → 4004122792. The 0.1522 km difference does not prove a defect. | ROUTER_CHOOSES_DIFFERENT_VALID_ROUTE | No change. | Medium | High |
| MY-073 | 1.2567 / 1.6898 | Лазо → Коммунистическая → Московская → Дзержинского | Лазо → Суворова → Комсомольская → Дзержинского | Both approaches are connected and end at nodes 517407672 → 1017871035 → 4016890684. Yandex chooses the longer route; no illegal router shortcut is evidenced. | ROUTER_CHOOSES_DIFFERENT_VALID_ROUTE | Preserve the legal shortest path. | High | High |
| MY-075 | 3.0020 / 3.9107 | Лазо → Коммунистическая → Ечина | Лазо → Коммунистическая → Ечина → Георге Асаке → Мичурина → Ечина | The control has no house number and lies directly on Ечина (zero snap distance). Yandex makes a loop and returns to the same street; nodes 2315990604 → 6367865573 → 2337407447. | ADDRESS_ANCHOR_AMBIGUOUS | Owner must provide a house or landmark anchor. | High | High |

MY-X01 and MY-X02 are the two required extra-landmark cases and are not part of
the 86-control baseline denominator.

## Corridor conclusions

The fresh routes confirm that the northern Borisovka corridor, the southern
Ечина corridor, the near-Khomutyanovka approaches, and both Protyagailovka
approaches are routable. The Yandex order is evidence that the vendor selected a
corridor, not evidence that every segment should receive a global preference.
No corridor override was created.

## Unsafe changes rejected

1. Synthetic edge from MY-071 to the nearest road — rejected because no real OSM
   junction is evidenced.
2. Per-control forcing for MY-002, MY-005, MY-054, MY-063, MY-065, MY-073, or
   MY-075 — rejected as hardcode.
3. Global preference by street name — rejected because names do not identify a
   specific graph edge or prove access/connectivity.
4. Unverified edits to speed, access, one-way, turn restrictions, bridges, or
   level crossings — rejected because no independent contradictory tag evidence
   was found.

The detailed disposition is recorded in
`data/interim/router-repair-actions-v1.csv`.
