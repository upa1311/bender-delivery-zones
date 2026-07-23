# Stage 03 — candidate working service area (housing density)

- Generated (UTC): `2026-07-23T20:01:21Z`
- zones_created: **False** · routing: **False** · Direct: **False**
- OSM boundaries modified: **False**

> Рабочая территория создана по плотности жилой застройки и указаниям владельца. Это ещё не четыре зоны доставки.

## Areas per territory

| Территория | Source км² | Candidate км² | Сокращение | Здания вкл. | Здания искл. | Адреса |
|---|---:|---:|---:|---:|---:|---:|
| Бендеры (`bender_core`) | 17.9802 | 13.8178 | 23.15% | 9672 | 17 | 5872 |
| Липканы (`bender_lipcani`) | 3.0678 | 1.4918 | 51.37% | 620 | 3 | 290 |
| Протягайловка (`protyagailovka`) | 16.6775 | 2.0667 | 87.61% | 1512 | 524 | 573 |
| Гиска (`giska`) | 30.8582 | 3.0492 | 90.12% | 2398 | 20 | 625 |
| Парканы (`parkany`) | 82.4359 | 6.543 | 92.06% | 8807 | 48 | 4508 |

## Inclusion / exclusion reasons

- **Бендеры** — включено: `addressed_buildings`, `dense_residential_buildings`, `required_access_road`, `residential_street`; исключено: `empty_land`, `farmland`, `forest_or_park`, `outside_owner_named_limit`, `sparse_buildings`
- **Липканы** — включено: `addressed_buildings`, `dense_residential_buildings`, `owner_named_boundary`, `required_access_road`, `residential_street`; исключено: `empty_land`, `farmland`, `forest_or_park`, `sparse_buildings`
- **Протягайловка** — включено: `addressed_buildings`, `dense_residential_buildings`, `owner_named_boundary`, `required_access_road`, `residential_street`; исключено: `empty_land`, `farmland`, `forest_or_park`, `outside_owner_named_limit`, `sparse_buildings`
- **Гиска** — включено: `addressed_buildings`, `dense_residential_buildings`, `required_access_road`, `residential_street`; исключено: `empty_land`, `farmland`, `forest_or_park`, `sparse_buildings`
- **Парканы** — включено: `addressed_buildings`, `dense_residential_buildings`, `residential_street`; исключено: `empty_land`, `farmland`, `forest_or_park`, `sparse_buildings`

## Ориентир «Кавказ»

- Найден: **Кавказ** (node 3585559297, place=suburb), lon/lat 29.484333/46.80655
- Применено: исключены незастроенные территории к востоку (east).

## Спорные места (boundary questions)

- [interpretation] «Левее» улицы «Главная улица» невозможно свести к стороне света: улица идёт с юго-запада на северо-восток, а названные владельцем предельные улицы Мунтяна и Лесовая лежат западнее неё. Оставлена сторона, на которой лежат другие названные владельцем предельные улицы (Мунтяна, Лесовая, Первомайская); отсечение применено. Подтвердите сторону.
- [limit_street] Левый предел по указанию владельца.
- [limit_street] Улица «улица Мунтяна» названа владельцем как предел. Какая именно сторона («с одной стороны» / «с другой стороны») имелась в виду — не задано однозначно; застройка вдоль улицы включена.
- [limit_street] Улица «Лесовая улица» названа владельцем как предел. Какая именно сторона («с одной стороны» / «с другой стороны») имелась в виду — не задано однозначно; застройка вдоль улицы включена.
- [limit_street] Улица «Первомайская улица» названа владельцем как предел. Какая именно сторона («с одной стороны» / «с другой стороны») имелась в виду — не задано однозначно; застройка вдоль улицы включена.

## Limitations

- The candidate working area is NOT an official boundary and does not replace the OSM administrative boundaries, which are unmodified.
- No popularity/traffic data exists; street relevance is proxied by residential fabric (buildings and addresses near the street).
- The five candidates are deliberately NOT merged into one production polygon, and no delivery zones, tariffs or routing were created.
- Lipcani has no separate OSM boundary; it is separated from the rest of Bender by the Voronoi cell of its place=suburb node — an approximation to confirm with the owner.
- OSM building/address coverage is community-contributed and incomplete.
