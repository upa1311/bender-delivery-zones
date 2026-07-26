# Full address routing anomalies v1

Canonical registry: `releases/bender-zones-v1.1/address-registry.json` (normalized SHA-256 `bc66ad113a6ba5706bb6d2797ddc543e5b576482051d0d981551f014561c1817`); coordinate join: `docs/data/delivery-units.csv` (normalized SHA-256 `7f52e5119db0bfeb8a68464ad79ed1288a070c3563d887c088f72283c85c4250`).

## Severity

| severity | addresses |
|---|---:|
| CRITICAL | 4 |
| HIGH | 1029 |
| MEDIUM | 1990 |
| NONE | 6193 |

## Anomaly classes

| anomaly | addresses |
|---|---:|
| ROUTE_STREET_LOOP | 1252 |
| SNAPPED_STREET_NAME_MISMATCH | 593 |
| DESTINATION_SNAP_GT30M | 529 |
| STREET_DISTANCE_CONTINUITY_OUTLIER | 437 |
| STREET_DURATION_CONTINUITY_OUTLIER | 396 |
| UTURN | 248 |
| UNIQUE_TERMINAL_BRANCH | 201 |
| LOCAL_CORRIDOR_DISCONTINUITY | 110 |
| ROBUST_HIGH_DETOUR_FACTOR | 68 |
| STREET_NAME_VARIANT | 24 |
| DESTINATION_SNAP_GT60M | 23 |
| ADDRESS_ANCHOR_DISAGREEMENT | 19 |
| HOUSE_NUMBER_DISAGREEMENT | 13 |
| DESTINATION_SNAP_GT100M | 4 |
| SETTLEMENT_DISAGREEMENT | 3 |

## Territories

| territory | anomaly addresses |
|---|---:|
| Бендеры | 1526 |
| Парканы | 1288 |
| Гиска | 128 |
| Протягайловка | 81 |

## Top streets

| territory / street | anomaly addresses |
|---|---:|
| Парканы / улица Котовского | 163 |
| Парканы / улица Суворова | 161 |
| Парканы / улица Ленина | 145 |
| Парканы / улица Петра Николаева | 107 |
| Парканы / улица Чапаева | 97 |
| Бендеры / улица Ткаченко | 88 |
| Парканы / улица Горького | 69 |
| Парканы / улица Кирова | 63 |
| Парканы / улица Сергея Лазо | 59 |
| Бендеры / Коммунистическая улица | 57 |
| Бендеры / улица Титова | 56 |
| Бендеры / улица Шевченко | 50 |
| Бендеры / улица Кавриаго | 48 |
| Парканы / Молодёжная улица | 46 |
| Бендеры / Бельцкая улица | 46 |
| Бендеры / улица Тамары Кручок | 46 |
| Парканы / улица Гагарина | 43 |
| Парканы / улица Фрунзе | 40 |
| Бендеры / улица Кирова | 39 |
| Гиска / улица Суворова | 37 |
| Бендеры / Первомайская улица | 36 |
| Парканы / Степная улица | 33 |
| Бендеры / Комсомольская улица | 28 |
| Бендеры / улица 12 Октября | 27 |
| Парканы / Коммунистическая улица | 26 |
| Бендеры / улица Ивана Федько | 26 |
| Бендеры / Советская улица | 25 |
| Бендеры / улица Калинина | 25 |
| Бендеры / Песчанная улица | 25 |
| Парканы / улица Калинина | 22 |

High detour and corridor changes are triage signals, not automatic graph
errors: rivers, railways, bridges and legal network separation can explain them.
