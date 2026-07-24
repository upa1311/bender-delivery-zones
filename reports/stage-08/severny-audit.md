# Stage 08 — Северный (исправлено, полный PBF)

- Сгенерировано (UTC): `2026-07-24T05:11:30Z`
- resolved: **False** · Real Северный resolved from full PBF — owner_review_required
- decided_k: **4** · цены: **False** · Direct: **False**

## Исправление регрессии

- прежний обрезанный терминал: {'lon': 29.480231, 'lat': 46.854251}
- реальный терминал маршрутов: {'lon': 29.464, 'lat': 46.890752}
- узел place=suburb «Северный»: {'id': 5135654201, 'lon': 29.472287, 'lat': 46.881852}
- причина: previous run read only city-extract-12463379; routes and the enclave lie outside it

## Реальный жилой контур Северного

- зданий: **59** · адресов: **7** · квартирных: **23**
- улицы: Strada Academician Iacob Bumbu, Strada Dimitrie Cantemir, Strada Tighina, Северная улица
- официальный формат: `Бендеры, микрорайон Северный, дом N` (примеры: Бендеры, микрорайон Северный, дом 13, Бендеры, микрорайон Северный, дом 19A, Бендеры, микрорайон Северный, дом 21, Бендеры, микрорайон Северный, дом 21/1)
- севернее села Варница: **True** · отсоединён: **True**

## Overlap-отчёт (Липканы / уже обслуживается)

- уже в service area: **0**
- уже как Липканы: **0**
- на улицах Липкан: **0**
- новые здания Северного: **59**
- новые адреса Северного: **7**

Прежние кластеры (n=8) — `rejected_false_candidates_lipcani` (Липканы, не Северный).

## Проверки

- терминал ≠ обрезанная точка 46.854251: **True**
- контур севернее Варницы (село): **True**
- контур пересекает село Варница: **False**
- central→Северный доезжает: **True** (8.135 км)
- узел внутри admin-relation Варницы: **True** — The OSM admin_level=8 Varnița relation geographically encloses the Bender Северный enclave. Северный is operationally Бендеры; exclusion is enforced against the Varnița VILLAGE built-up area, not the admin claim.

## Варница — исключение

- обслуживаемых адресов внутри села Варница: **0**
- Северный-кандидатов внутри села Варница: **0**

## Сценарии

- **Scenario A**: keep K=4 edges; extend Zone 4 only if beyond current maximum. expected_km(центр) = **7.757**, зона **4**, за макс.: **False**.
- маршрут через Варницу: **True**
- **Scenario B** (превью): границы [2.975, 4.875, 6.426, 9.686] км; units существующих 22120 (адресов 9777); меняют зону **8863**; добавлено Северного — units 59, адресов 7 (units и адреса отдельно).

## Требуются решения владельца

- Approve or reject the Северный candidate residential footprint.
- Confirm Scenario A (extend Zone 4 if beyond max) vs a Scenario-B recompute.
- Confirm the enclave handling: Северный served as Бендеры though it lies within the OSM admin Varnița relation.
