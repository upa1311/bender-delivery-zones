# Owner decision pack v1

This pack organizes recommendations; it does not approve a release or change the
canonical registry.

## A. APPROVE_FOR_FUTURE_RELEASE recommendations

`REC-002`, `REC-013`, `REC-018`, `REC-023`, `REC-026`, `REC-027`.

## B. Seven HIGH Yandex-only observations

`YOX-0001` through `YOX-0007`. Four are provisional zero-effect number
substitutions; three remain unresolved. The owner must decide whether each is a
replacement, a distinct delivery address, or insufficient evidence.

Known provisional net effect: 0. Three reconciliations remain unresolved and are excluded from the numeric net effect.

## C. HOLD_ADDRESS_CONFLICT

`REC-001`, `REC-017`, `REC-021`, `REC-024`, `REC-036`.

## D. HOLD_OPERATIONAL_STATUS

`REC-020`.

## E. HOLD_INSUFFICIENT_EVIDENCE

`REC-009`, `REC-016`.

For exact recovered address, Yandex label, coordinates, category, duplicate state,
confidence, and evidence, use the three source CSVs. All decisions remain
owner-owned.

## Detailed recovered-candidate rows

| ID | Recovered address / source coordinates | Visible Yandex evidence | Category; duplicate/conflict | Recommendation; confidence; owner decision |
|---|---|---|---|---|
| REC-001 | Тираспольское шоссе 33; 46.8360422, 29.5283052 | Тираспольское шоссе 35 | RETAIL; no duplicate; number conflict | HOLD_ADDRESS_CONFLICT; HIGH; decide 33 vs 35 |
| REC-002 | Парканы, Карла Маркса 1a; 46.8356503, 29.5215913 | Магазин Виктория, 1А | RETAIL; no duplicate; none | APPROVE_FOR_FUTURE_RELEASE; HIGH; approve/reject |
| REC-008 | Парканы, Карла Маркса 1a; 46.8356601, 29.5217426 | Аптека inside house 1А | MEDICAL; canonical duplicate | REJECT_DUPLICATE; HIGH; confirm rejection |
| REC-009 | Тираспольское шоссе 25; 46.8356689, 29.5222701 | house 25, nearby-only facility | OFFICE; no duplicate; nearby only | HOLD_INSUFFICIENT_EVIDENCE; MEDIUM; seek entrance evidence |
| REC-013 | Ленина 20a; 46.8227655, 29.4819819 | Авеню, 20А | FOOD_SERVICE; no duplicate; none | APPROVE_FOR_FUTURE_RELEASE; HIGH; approve/reject |
| REC-016 | Советская 23; 46.8266134, 29.4837783 | house 23, nearby-only facility | RETAIL; no duplicate; nearby only | HOLD_INSUFFICIENT_EVIDENCE; MEDIUM; seek independent destination evidence |
| REC-017 | Коммунистическая 181; 46.8098922, 29.4710801 | Коммунистическая 187А | INDUSTRIAL; no duplicate; number conflict | HOLD_ADDRESS_CONFLICT; HIGH; decide 181 vs 187А |
| REC-018 | Индустриальная 12/3; 46.7883322, 29.4881218 | Шериф-17, 12/3 | INDUSTRIAL; no duplicate; none | APPROVE_FOR_FUTURE_RELEASE; HIGH; approve/reject |
| REC-020 | Индустриальная 35; 46.7982621, 29.4884651 | Гарант, 35 | INDUSTRIAL; no duplicate; none | HOLD_OPERATIONAL_STATUS; HIGH; verify active delivery destination |
| REC-021 | Советская 29а; 46.8257873, 29.4834238 | Советская 31 | RETAIL; no duplicate; number conflict | HOLD_ADDRESS_CONFLICT; HIGH; decide 29а vs 31 |
| REC-023 | Коммунистическая 163; 46.8124472, 29.4727093 | Ветклиника, 163 | MEDICAL; no duplicate; none | APPROVE_FOR_FUTURE_RELEASE; HIGH; approve/reject |
| REC-024 | Советская 27; 46.8260939, 29.4836545 | Просто Обувь linked to Гагарина | RETAIL; no duplicate; street conflict | HOLD_ADDRESS_CONFLICT; HIGH; choose valid delivery street |
| REC-026 | Strada Panin 2/1; 46.8339960, 29.4885005 | Старый бастион, Панина 2/1 | FOOD_SERVICE; no duplicate; none | APPROVE_FOR_FUTURE_RELEASE; HIGH; approve/reject |
| REC-027 | Дзержинского 4А; 46.8285290, 29.4743407 | industrial facility, 4А | INDUSTRIAL; no duplicate; none | APPROVE_FOR_FUTURE_RELEASE; HIGH; approve/reject |
| REC-036 | Тимирязева 2А; 46.7849268, 29.4835971 | 2А; facility linked to Индустриальная 14А | GOVERNMENT; no duplicate; facility-address conflict | HOLD_ADDRESS_CONFLICT; MEDIUM; determine facility delivery address |

## Detailed HIGH Yandex-only rows

| ID | Yandex address / coordinates | Nearest canonical | Relationship; net; confidence | Owner decision |
|---|---|---|---|---|
| YOX-0001 | Советская 31; 46.823889, 29.482151 | Советская 36 (exact point also conflicts with another canonical street) | UNRESOLVED; UNKNOWN; LOW | decide distinct address vs cross-street substitution |
| YOX-0002 | Ленина 9; 46.824900, 29.476994 | Ленина 12 | UNRESOLVED; UNKNOWN; LOW | decide addition vs numbering shift |
| YOX-0003 | Коммунистическая 187А; 46.806621, 29.467607 | Коммунистическая 187 | SAME_BUILDING_DIFFERENT_NUMBER; ZERO_SUBSTITUTION; HIGH | choose retained number |
| YOX-0004 | Индустриальная 14А; 46.786349, 29.488601 | Индустриальная 12 | UNRESOLVED; UNKNOWN; LOW | decide facility substitution vs additional address |
| YOX-0005 | Гиска, Молодёжная 3; 46.787392, 29.449551 | Молодёжная 1 | SAME_BUILDING_DIFFERENT_NUMBER; ZERO_SUBSTITUTION; MEDIUM | choose retained number |
| YOX-0006 | Гиска, Молодёжная 49; 46.789527, 29.455363 | Молодёжная 51 | SAME_BUILDING_DIFFERENT_NUMBER; ZERO_SUBSTITUTION; HIGH | choose retained number |
| YOX-0007 | Гиска, Ленина 61; 46.786923, 29.448293 | Ленина 59 | NUMBER_SHIFT_ON_SAME_STREET; ZERO_SUBSTITUTION; MEDIUM | confirm numbering shift |
