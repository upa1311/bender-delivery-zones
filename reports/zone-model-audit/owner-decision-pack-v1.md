# Owner decision pack — zone models (candidate, not production)

Простыми словами. Анализ, не готовые production-цены. Ничего не применено.
Метрика — fixed-origin km (маршрут от 46.82388, 29.48313). Граница зон единая
**[нижняя, верхняя)**. Бенчмарк дохода водителя = `taxi_reference - 5` (fixed-5
платформа выигрывает у 100 % городских адресов; crossover 14.29 < минималки 18).

**Терминология.** Все зоны K4/K5 — это **городские зоны Бендер**: ближние, средние
и дальние. Дальние городские зоны — это НЕ «внешние территории». Термин
**внешние территории** относится только к Парканам, Гиске, Протягайловке и
нерешённому Северному (раздел B).

## Исправление аудита (BALANCED 5 руб)

Раньше BALANCED считал клиентскую экономию с порогом 1 руб (target_save=5
игнорировался), поэтому зоны помечались FEASIBLE при экономии всего 4 руб. Теперь
**BALANCED требует client_saving ≥ 5 руб для 100 %** адресов зоны (жёстко). Как
следствие ряд зон стал INFEASIBLE — пример: CITY_K4 средняя зона 2 (минимальное
такси 18, ceiling 13 < driver floor 14).

## A. ГОРОДСКИЕ ЗОНЫ БЕНДЕР

Полные таблицы ниже сгенерированы напрямую из `zone-policy-prices-v1.csv` (raw) и
`zone-operational-policy-prices-v1.csv` (0.25) — без ручного ввода чисел. Для каждой
зоны и политики: статус, FEASIBLE-цена или INFEASIBLE, fallback, покрытие, число
нарушенных адресов, минимальная клиентская экономия, максимальный gap водителя.
Округление 0.25 реально пересчитано (например, CITY_K5 0.25 делает
DRIVER_CONSERVATIVE зону 3 FEASIBLE — raw z3 infeasible).

<!-- AUTO-POLICY-TABLES-START -->
### CITY_K4 raw — edges 1.725|3.275|4.975

| Zone | Policy | Status | Fee | Fallback | Coverage | Violated | MinSave | MaxGap |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 1 | CUSTOMER FIRST | FEASIBLE | 12 | — | 1.0 | 0 | 6.0 | 1.0 |
| 1 | BALANCED | FEASIBLE | 12 | — | 1.0 | 0 | 6.0 | 1.0 |
| 1 | DRIVER CONSERVATIVE | FEASIBLE | 12 | — | 1.0 | 0 | 6.0 | 1.0 |
| 2 | CUSTOMER FIRST | FEASIBLE | 13 | — | 1.0 | 0 | 5.0 | 1.63 |
| 2 | BALANCED | INFEASIBLE | — | 13 | 0.9891 | 13 | 5.0 | 1.63 |
| 2 | DRIVER CONSERVATIVE | FEASIBLE | 13 | — | 1.0 | 0 | 5.0 | 1.63 |
| 3 | CUSTOMER FIRST | INFEASIBLE | — | 20 | 0.4777 | 690 | -0.32 | 4.84 |
| 3 | BALANCED | INFEASIBLE | — | 21 | 0.3285 | 887 | -1.32 | 3.84 |
| 3 | DRIVER CONSERVATIVE | INFEASIBLE | — | 23 | 0.6949 | 403 | -3.32 | 1.84 |
| 4 | CUSTOMER FIRST | INFEASIBLE | — | 25 | 0.5737 | 428 | 4.85 | 14.75 |
| 4 | BALANCED | INFEASIBLE | — | 25 | 0.3944 | 608 | 4.85 | 14.75 |
| 4 | DRIVER CONSERVATIVE | INFEASIBLE | — | 29 | 0.6952 | 306 | 0.85 | 10.75 |

### CITY_K4 operational 0.25 — edges 1.75|3.25|5.0

| Zone | Policy | Status | Fee | Fallback | Coverage | Violated | MinSave | MaxGap |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 1 | CUSTOMER FIRST | FEASIBLE | 12 | — | 1.0 | 0 | 6.0 | 1.0 |
| 1 | BALANCED | FEASIBLE | 12 | — | 1.0 | 0 | 6.0 | 1.0 |
| 1 | DRIVER CONSERVATIVE | FEASIBLE | 12 | — | 1.0 | 0 | 6.0 | 1.0 |
| 2 | CUSTOMER FIRST | FEASIBLE | 13 | — | 1.0 | 0 | 5.0 | 1.48 |
| 2 | BALANCED | INFEASIBLE | — | 13 | 0.9966 | 4 | 5.0 | 1.48 |
| 2 | DRIVER CONSERVATIVE | FEASIBLE | 13 | — | 1.0 | 0 | 5.0 | 1.48 |
| 3 | CUSTOMER FIRST | INFEASIBLE | — | 20 | 0.4671 | 720 | -0.49 | 4.98 |
| 3 | BALANCED | INFEASIBLE | — | 21 | 0.3212 | 917 | -1.49 | 3.98 |
| 3 | DRIVER CONSERVATIVE | INFEASIBLE | — | 23 | 0.695 | 412 | -3.49 | 1.98 |
| 4 | CUSTOMER FIRST | INFEASIBLE | — | 25 | 0.586 | 407 | 5.0 | 14.75 |
| 4 | BALANCED | INFEASIBLE | — | 25 | 0.4028 | 587 | 5.0 | 14.75 |
| 4 | DRIVER CONSERVATIVE | INFEASIBLE | — | 29 | 0.7101 | 285 | 1.0 | 10.75 |

### CITY_K5 raw — edges 1.675|2.875|4.125|5.325

| Zone | Policy | Status | Fee | Fallback | Coverage | Violated | MinSave | MaxGap |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 1 | CUSTOMER FIRST | FEASIBLE | 12 | — | 1.0 | 0 | 6.0 | 1.0 |
| 1 | BALANCED | FEASIBLE | 12 | — | 1.0 | 0 | 6.0 | 1.0 |
| 1 | DRIVER CONSERVATIVE | FEASIBLE | 12 | — | 1.0 | 0 | 6.0 | 1.0 |
| 2 | CUSTOMER FIRST | FEASIBLE | 12 | — | 1.0 | 0 | 6.0 | 1.0 |
| 2 | BALANCED | FEASIBLE | 12 | — | 1.0 | 0 | 6.0 | 1.0 |
| 2 | DRIVER CONSERVATIVE | FEASIBLE | 12 | — | 1.0 | 0 | 6.0 | 1.0 |
| 3 | CUSTOMER FIRST | INFEASIBLE | — | 15 | 0.4229 | 363 | 3.0 | 4.74 |
| 3 | BALANCED | INFEASIBLE | — | 15 | 0.3037 | 438 | 3.0 | 4.74 |
| 3 | DRIVER CONSERVATIVE | INFEASIBLE | — | 17 | 0.8744 | 79 | 1.0 | 2.74 |
| 4 | CUSTOMER FIRST | INFEASIBLE | — | 20 | 0.553 | 510 | 4.75 | 6.94 |
| 4 | BALANCED | INFEASIBLE | — | 21 | 0.3804 | 707 | 3.75 | 5.94 |
| 4 | DRIVER CONSERVATIVE | INFEASIBLE | — | 24 | 0.8563 | 164 | 0.75 | 2.94 |
| 5 | CUSTOMER FIRST | INFEASIBLE | — | 27 | 0.6695 | 232 | 4.97 | 12.75 |
| 5 | BALANCED | INFEASIBLE | — | 27 | 0.49 | 358 | 4.97 | 12.75 |
| 5 | DRIVER CONSERVATIVE | INFEASIBLE | — | 31 | 0.7849 | 151 | 0.97 | 8.75 |

### CITY_K5 operational 0.25 — edges 1.75|3.0|4.0|5.25

| Zone | Policy | Status | Fee | Fallback | Coverage | Violated | MinSave | MaxGap |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 1 | CUSTOMER FIRST | FEASIBLE | 12 | — | 1.0 | 0 | 6.0 | 1.0 |
| 1 | BALANCED | FEASIBLE | 12 | — | 1.0 | 0 | 6.0 | 1.0 |
| 1 | DRIVER CONSERVATIVE | FEASIBLE | 12 | — | 1.0 | 0 | 6.0 | 1.0 |
| 2 | CUSTOMER FIRST | FEASIBLE | 12 | — | 1.0 | 0 | 6.0 | 1.0 |
| 2 | BALANCED | FEASIBLE | 12 | — | 1.0 | 0 | 6.0 | 1.0 |
| 2 | DRIVER CONSERVATIVE | FEASIBLE | 12 | — | 1.0 | 0 | 6.0 | 1.0 |
| 3 | CUSTOMER FIRST | INFEASIBLE | — | 15 | 0.5331 | 233 | 3.0 | 3.99 |
| 3 | BALANCED | INFEASIBLE | — | 15 | 0.3828 | 308 | 3.0 | 3.99 |
| 3 | DRIVER CONSERVATIVE | FEASIBLE | 17 | — | 1.0 | 0 | 1.0 | 1.99 |
| 4 | CUSTOMER FIRST | INFEASIBLE | — | 20 | 0.5482 | 520 | 4.01 | 6.49 |
| 4 | BALANCED | INFEASIBLE | — | 21 | 0.3771 | 717 | 3.01 | 5.49 |
| 4 | DRIVER CONSERVATIVE | INFEASIBLE | — | 24 | 0.8488 | 174 | 0.01 | 2.49 |
| 5 | CUSTOMER FIRST | INFEASIBLE | — | 27 | 0.6096 | 301 | 4.5 | 12.75 |
| 5 | BALANCED | INFEASIBLE | — | 27 | 0.4462 | 427 | 4.5 | 12.75 |
| 5 | DRIVER CONSERVATIVE | INFEASIBLE | — | 30 | 0.7289 | 209 | 1.5 | 9.75 |

<!-- AUTO-POLICY-TABLES-END -->

### Вывод по городу
- **Feasible при 100 %-покрытии только ближние зоны** (K4 z1; K5 z1–z2), плюс для
  DRIVER_CONSERVATIVE ещё z2 (K4) и z3 (K5-op). Средние/дальние городские зоны —
  INFEASIBLE одной плоской ценой, только fallback с частичным покрытием.
- Минимальная клиентская экономия у FEASIBLE BALANCED-зон = **6 руб** (≥ порога 5).

## B. ВНЕШНИЕ ТЕРРИТОРИИ (Парканы, Гиска, Протягайловка, Северный)

Split город/внешний **не доказан** → **никаких городских candidate/fallback цен
к ним не применяется**. Только диапазон в `zone-external-bracket-scenarios-v1.csv`
(поле `taxi_reference_bracket_rub`, `direct_feasible_*` пустые), все строки
`RANGE_ONLY_NOT_TARIFF`. Пост ГАИ на Котовского — `UNKNOWN_REQUIRES_OWNER_MAP_CONFIRMATION`;
Северный — `OWNER_BOUNDARY_DECISION_REQUIRED`.

## Operational-выбор (лексикографический, документированный)
Порядок сравнения (не штраф-число): (1) не уменьшать число FEASIBLE BALANCED-зон
относительно raw; (2) максимизировать BALANCED total_joint_coverage по всем 4 866
адресам; (3) минимизировать violated addresses; (4) геометрия = changed +
same_street_splits + neighbour_diff_100m + 5·manual_flip. Метрики покрытия — в
`zone-operational-candidates-v1.csv`.
- **CITY_K4:** покрытие/violated одинаковы у всех округлений → решает геометрия →
  **PRIMARY 0.25 км**, FALLBACK 0.1 км.
- **CITY_K5:** **PRIMARY 0.25 км** выигрывает по шагу 2 — наибольшее BALANCED
  покрытие (0.702 против 0.694 у 0.1 и 0.687 у 0.5) и наименьшие violated (1 452);
  FALLBACK 0.1 км. Выбор 0.25 обоснован покрытием, а не навязан.
Same-street splits считаются по админ-ключу **территория+район+улица** (одноимённые
улицы разных районов не сливаются).

## Business model
`business_constrained` честно переименован **`share_width_density`**: objective =
route SSE + плотность у порога при ограничениях share/width; street/neighbour —
только оценка после partition, не в objective. Не выдаётся за оптимизированную
бизнес-модель.

## Что нужно от владельца
1. **CITY_K4 или CITY_K5** для ближних (feasible) зон.
2. Средние/дальние городские зоны: принять fallback с частичным покрытием
   (и каким порогом), либо дробить мельче до feasibility.
3. Политика цен (CUSTOMER_FIRST / BALANCED / DRIVER_CONSERVATIVE) — точные цены
   для raw и 0.25 показаны выше и в CSV.
4. Внешние территории и Северный — подтвердить границы на карте.

**Итог: ANALYSIS_COMPLETE / OWNER_DECISION_REQUIRED. Готовый тариф до решения
владельца не рекомендуется. В production ничего не применено.**
