# Recovered non-residential address candidates v1

Status: **SOURCE RECOVERY COMPLETE; OWNER REVIEW REQUIRED**

All 36 legacy exclusions with reason `address_inside_nonresidential_building` were
recovered from `moldova-260722.osm.pbf`. The file is the exact source represented by
the pinned manifest: SHA-256
`09ba0c058e89faacac7e1b1e7c8d0fbb14b4df66061b43abdce590b65ce8813c`.
No record was blocked and no tag was invented.

Reproduction command:

```text
python scripts/recover_nonresidential_address_candidates.py --pbf data/raw/moldova-260722.osm.pbf
```

## Recovery summary

| Metric | Count |
|---|---:|
| Original exclusions | 36 |
| Source records recovered | 36 |
| Blocked | 0 |
| DELIVERABLE_CANDIDATE | 15 |
| DUPLICATE_EXISTING_ADDRESS | 20 |
| NON_DELIVERABLE_AUXILIARY | 0 |
| NON_DELIVERABLE_LIFECYCLE | 1 |
| UNKNOWN_REQUIRES_REVIEW | 0 |
| MEDICAL | 3 |
| EDUCATION | 0 |
| INDUSTRIAL | 4 |
| WAREHOUSE | 0 |
| RETAIL | 12 |
| OFFICE | 2 |
| GOVERNMENT / PUBLIC_SERVICE | 6 |

## Candidate-by-candidate evidence

Every row below was also searched separately in the visible Yandex Maps interface.
`Owner` is the forward-row owner-review flag.

| Candidate | Source category | Source name | Recovered address | Recovery classification | Yandex result | Owner |
|---|---|---|---|---|---|---|
| REC-001 | RETAIL | Нистру | Тираспольское шоссе 33 | DELIVERABLE_CANDIDATE | DIFFERENT_HOUSE_NUMBER | True |
| REC-002 | RETAIL | Виктория | улица Карла Маркса 1a | DELIVERABLE_CANDIDATE | FACILITY_MATCH_WITH_ADDRESS | False |
| REC-003 | RETAIL | Квинт-Маркет №11 | улица Гоголя 1 | DUPLICATE_EXISTING_ADDRESS | DUPLICATE_EXISTING_ADDRESS | False |
| REC-004 | PUBLIC_SERVICE | Агропромбанк | улица Гоголя 1 | DUPLICATE_EXISTING_ADDRESS | DUPLICATE_EXISTING_ADDRESS | False |
| REC-005 | GOVERNMENT | Госадминистрация с. Парканы | улица Гоголя 1 | DUPLICATE_EXISTING_ADDRESS | DUPLICATE_EXISTING_ADDRESS | False |
| REC-006 | PUBLIC_SERVICE | Приднестровский Сбербанк | улица Гоголя 1 | DUPLICATE_EXISTING_ADDRESS | DUPLICATE_EXISTING_ADDRESS | False |
| REC-007 | MEDICAL | Вивафарм | улица Гоголя 1 | DUPLICATE_EXISTING_ADDRESS | DUPLICATE_EXISTING_ADDRESS | False |
| REC-008 | MEDICAL | Фармпункт №15 | улица Карла Маркса 1а | DELIVERABLE_CANDIDATE | DUPLICATE_EXISTING_ADDRESS | True |
| REC-009 | OFFICE | Центр по правам человека | Тираспольское шоссе 25 | DELIVERABLE_CANDIDATE | NEARBY_ADDRESS_ONLY | True |
| REC-010 | PUBLIC_SERVICE | Болгарское возрождение | Тираспольское шоссе 25 | DUPLICATE_EXISTING_ADDRESS | DUPLICATE_EXISTING_ADDRESS | False |
| REC-011 | UNKNOWN | — | Славянская улица 64 | NON_DELIVERABLE_LIFECYCLE | NON_DELIVERABLE_STRUCTURE | True |
| REC-012 | RETAIL | Шериф | улица Суворова 28 | DUPLICATE_EXISTING_ADDRESS | DUPLICATE_EXISTING_ADDRESS | False |
| REC-013 | FOOD_SERVICE | Авеню | улица Ленина 20a | DELIVERABLE_CANDIDATE | FACILITY_MATCH_WITH_ADDRESS | False |
| REC-014 | PUBLIC_SERVICE | Агропромбанк | улица Суворова 28 | DUPLICATE_EXISTING_ADDRESS | DUPLICATE_EXISTING_ADDRESS | False |
| REC-015 | UNKNOWN | — | улица Полоза 2а | DUPLICATE_EXISTING_ADDRESS | DIFFERENT_HOUSE_NUMBER | True |
| REC-016 | RETAIL | Квинт-Маркет | Советская улица 23 | DELIVERABLE_CANDIDATE | NEARBY_ADDRESS_ONLY | True |
| REC-017 | INDUSTRIAL | ОАО «Флоаре» | Коммунистическая 181 | DELIVERABLE_CANDIDATE | DIFFERENT_HOUSE_NUMBER | True |
| REC-018 | INDUSTRIAL | Шериф | Индустриальная 12/3 | DELIVERABLE_CANDIDATE | FACILITY_MATCH_WITH_ADDRESS | False |
| REC-019 | RETAIL | Грин-Интермаркет | улица Ленина 20 | DUPLICATE_EXISTING_ADDRESS | DUPLICATE_EXISTING_ADDRESS | False |
| REC-020 | INDUSTRIAL | Гарант | Индустриальная 35 | DELIVERABLE_CANDIDATE | FACILITY_MATCH_WITH_ADDRESS | True |
| REC-021 | RETAIL | Клеймс | Советская 29а | DELIVERABLE_CANDIDATE | DIFFERENT_HOUSE_NUMBER | True |
| REC-022 | RETAIL | Гермес | Советская 29 | DUPLICATE_EXISTING_ADDRESS | DIFFERENT_HOUSE_NUMBER | True |
| REC-023 | MEDICAL | Ветеринарная лечебница | Коммунистическая 163 | DELIVERABLE_CANDIDATE | FACILITY_MATCH_WITH_ADDRESS | False |
| REC-024 | RETAIL | Просто Обувь | Советская 27 | DELIVERABLE_CANDIDATE | DIFFERENT_STREET | True |
| REC-025 | RETAIL | Фотогрин | улица Ленина 11 | DUPLICATE_EXISTING_ADDRESS | DIFFERENT_HOUSE_NUMBER | True |
| REC-026 | FOOD_SERVICE | Старый бастион | улица Панина 2/1 | DELIVERABLE_CANDIDATE | FACILITY_MATCH_WITH_ADDRESS | False |
| REC-027 | INDUSTRIAL | ВекПромМеталл | Дзержинского 4А | DELIVERABLE_CANDIDATE | FACILITY_MATCH_WITH_ADDRESS | False |
| REC-028 | HOSPITALITY | Старый бастион | улица Панина 2/1 | DUPLICATE_EXISTING_ADDRESS | DUPLICATE_EXISTING_ADDRESS | False |
| REC-029 | RETAIL | 5 Карманов | улица Ленина 20 | DUPLICATE_EXISTING_ADDRESS | DUPLICATE_EXISTING_ADDRESS | False |
| REC-030 | FOOD_SERVICE | Lavazza | Советская 29 | DUPLICATE_EXISTING_ADDRESS | DIFFERENT_HOUSE_NUMBER | True |
| REC-031 | FOOD_SERVICE | Family Land | улица Ленина 21 | DUPLICATE_EXISTING_ADDRESS | DUPLICATE_EXISTING_ADDRESS | False |
| REC-032 | RETAIL | Авиакасса | улица Ленина 20 | DUPLICATE_EXISTING_ADDRESS | DUPLICATE_EXISTING_ADDRESS | True |
| REC-033 | OFFICE | Бюро переводов АПОСТИЛЬ | улица Ленина 20 | DUPLICATE_EXISTING_ADDRESS | DUPLICATE_EXISTING_ADDRESS | False |
| REC-034 | FOOD_SERVICE | Lovesushi | улица Ленина 21 | DUPLICATE_EXISTING_ADDRESS | DUPLICATE_EXISTING_ADDRESS | False |
| REC-035 | FOOD_SERVICE | Doner Hit | улица Ленина 22 | DUPLICATE_EXISTING_ADDRESS | DIFFERENT_HOUSE_NUMBER | True |
| REC-036 | GOVERNMENT | МРЭО г. Бендеры | Тимирязева 2А | DELIVERABLE_CANDIDATE | AMBIGUOUS_REQUIRES_REVIEW | True |

The 15 candidates can increase a future mutable address base only after owner review.
Rows with address disagreement, nearby-only evidence, closed-business labels, or
conflicting organization cards remain explicitly reviewable. The 20 duplicate grains
must not increase the address count, and REC-011 is supported as lifecycle
non-deliverable. Nothing in this report modifies the immutable release.
