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

### CITY_K4 — raw пороги 1.73 / 3.28 / 4.98 км
| Policy | z1 ближняя | z2 средняя | z3 средняя | z4 дальняя |
|---|---|---|---|---|
| DRIVER_CONSERVATIVE | 12 ✅ | 13 ✅ | INF (fb 23, 69 %) | INF (29, 70 %) |
| BALANCED | 12 ✅ | INF (fb 13, 99 %) | INF (21, 33 %) | INF (25, 39 %) |
| CUSTOMER_FIRST | 12 ✅ | 13 ✅ | INF (20, 48 %) | INF (25, 57 %) |

### CITY_K4 — operational 0.25 км (PRIMARY) пороги 1.75 / 3.25 / 5.0
Почти совпадает с raw: DRIVER 12/13, CUSTOMER 12/13, BALANCED 12/INF; дальние зоны
INFEASIBLE (см. `zone-operational-policy-prices-v1.csv`).

### CITY_K5 — raw пороги 1.68 / 2.88 / 4.13 / 5.33 км
| Policy | z1 | z2 | z3 средняя | z4 дальняя | z5 дальняя |
|---|---|---|---|---|---|
| DRIVER_CONSERVATIVE | 12 ✅ | 12 ✅ | INF (fb 17, 87 %) | INF (24, 86 %) | INF (31, 78 %) |
| BALANCED | 12 ✅ | 12 ✅ | INF (15, 30 %) | INF (21, 38 %) | INF (27, 49 %) |
| CUSTOMER_FIRST | 12 ✅ | 12 ✅ | INF (15, 42 %) | INF (20, 55 %) | INF (27, 67 %) |

### CITY_K5 — operational 0.25 км (PRIMARY) пороги 1.75 / 2.75 / 4.0 / 5.25
Округление **делает среднюю зону 3 FEASIBLE для DRIVER_CONSERVATIVE (17 руб)** —
пример, что operational-пересчёт реально меняет feasibility, а не копирует raw.
BALANCED/CUSTOMER в средних/дальних остаются INFEASIBLE.

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

## Operational-выбор (документированный scoring)
`score = 1000·max(0, balanced_infeasible − raw_balanced_infeasible) + changed +
same_street_splits + neighbour_diff_100m + 5·manual_flip`; меньше — лучше, ничьи —
в пользу более мелкого шага. Both K4 и K5: **PRIMARY = 0.25 км**, FALLBACK = 0.1 км
(округление не ухудшает BALANCED-feasibility, решает геометрия). Same-street splits
считаются по админ-ключу **территория+район+улица** (одноимённые улицы разных
районов не сливаются).

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
