# Stage 08 — Северный (финальный контур + адресные зоны)

- Сгенерировано (UTC): `2026-07-24T05:42:01Z`
- resolved: **False** · Real Северный footprint + per-address zones — owner_review_required
- decided_k: **4** · направление: **Scenario A (individual distances, Zone 4)** · цены: **False** · Direct: **False**

## Контур (морфологический, без convex hull)

- метод: morphological: residential/apartment building buffers (22 m) + named access streets (14 m) + residential landuse, 25 m gap-closing, isolated components (<5 buildings) dropped, disconnected components kept separate. No convex hull.
- raw кандидатов: **59** → включено **57**, исключено изолированных **2**
- компонентов: **1** · пустая площадь: **61.5%**
- адресов: **7** · квартирных: **23** · улицы: Strada Academician Iacob Bumbu, Strada Dimitrie Cantemir, Strada Tighina, Северная улица

## Overlap (Липканы / уже обслуживается)

- уже в service area: **0** · на улицах Липкан: **0** · новые здания: **59**
- прежние кластеры (n=8) — rejected_false_candidates_lipcani.

## Провенанс адресной нумерации

- ключ: `external_address_reference` · verified_for_automatic_import: **False**
- источник: Owner statement (Stage-08 task brief) (unverified_owner_statement), импорт разрешён: **False**
- ссылка (внешняя): 1-105 · примеры: Бендеры, микрорайон Северный, дом 13, Бендеры, микрорайон Северный, дом 19A, Бендеры, микрорайон Северный, дом 21, Бендеры, микрорайон Северный, дом 21/1
- дома 1–105 НЕ синтезируются.

## Варница — два слоя

- `varnita-admin-reference.geojson` — только пунктирная граница, без заливки (охватывает анклав).
- `varnita-village-no-delivery.geojson` — застройка села, серая заливка, `no_delivery`.
- контур Северного пересекает заливку села: **False** · адресов внутри села: **0**
- The OSM admin_level=8 Varnița relation (8289510) encloses the Bender Северный enclave. It is published as a reference LINE only. Exclusion is enforced against the derived Varnița VILLAGE built-up footprint, which Северный does not touch.

## Поюнитные расстояния (OSRM)

- units: **57** (доступны 57, недоступны **0**), транзит через село Варница: **57**
- units по зонам: {1: 0, 2: 0, 3: 0, 4: 57}
- адресов по зонам: {1: 0, 2: 0, 3: 0, 4: 7}
- expected_km: min 6.584 / p50 7.508 / p90 7.942 / max 8.385

## Готовность

| признак | значение |
|---|---|
| `geometry_ready` | True |
| `zone_assignment_ready` | True |
| `direct_export_ready` | False |
| `address_catalog_ready` | False |
| `verified_osm_addresses` | 7 |
| `osm_housenumber_without_street` | 0 |
| `unaddressed_delivery_units` | 50 |
| `missing_requirement` | verified mapping of микрорайон Северный houses to coordinates |

## Сценарии

- **Scenario A** (production): keep K=4 edges; assign each unit by its OWN OSRM distance; extend Zone 4 only for units beyond the current maximum. Индивидуальные расстояния: **True**. За макс.: **0** units.
- **Scenario B** (превью): same as Stage 06 (1-D weighted DP, balance bounds, split penalty 'low'); границы [2.424, 4.076, 5.577, 9.692] км; существующих units 22120 (адресов 9777), меняют зону **0**; добавлено Северного units 57 / адресов 7.

## Требуются решения владельца

- Approve or reject the Северный residential footprint.
- Confirm Scenario A (per-unit distances, Zone 4) as production direction.
- Provide a verified source for the микрорайон Северный 1-105 numbering before any address import.
