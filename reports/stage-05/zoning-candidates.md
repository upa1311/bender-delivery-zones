# Stage 05 — routing-based candidate zones (K=4 / K=5)

- Generated (UTC): `2026-07-23T21:01:57Z`
- status: **prepared_not_selected** · winner: **None** · prices assigned: **False**
- road graph: 12214 nodes / 13135 edges · routing engine: `none (in-memory Dijkstra; no OSRM/Valhalla/GraphHopper)`
- customers: 14475 · exceptions: {'unsnapped_to_road': 190, 'unreachable': 9}

> Кандидаты зон построены по реальному дорожному времени. Победитель K не выбран, денежные тарифы не назначались.

## Restaurant origins

- Food-service POIs (amenity=restaurant/fast_food/cafe/bar/pub plus takeaway/delivery venues) were read from the LOCAL Bender extract and single-link clustered at 600 m. The largest cluster is the central origin; remaining clusters with >= 3 POIs represent BAM and other outer Bender districts.
- central weight **0.85**, outer total **0.15**
- Bender food POIs: 73 (central cluster 44, outer clusters [7, 5, 3, 3, 3])
- Villages are NOT restaurant origins: too little actual restaurant evidence in the local extract.
- BAM has no place=* object in OSM; the northern outer cluster nearest 'Бамовское озеро' represents it. Confirm with the owner.

## K=4

- connected zones: 4/4 · split streets: 7 · exceptions: 199 · uncertain streets: 27

| Зона | адресов | вес | км p50/p75/p90 | мин p50/p75/p90 | макс.разумный | компактность | центр→ / БАМ→ |
|---|---:|---:|---|---|---|---:|---|
| 0 | 441 | 441.0 | 5.65/7.06/8.17 | 6.38/7.87/9.07 | 9.77 мин | 0.0245 | 6.3 / 6.29 мин |
| 1 | 6340 | 6332.3 | 4.46/5.33/6.16 | 4.69/5.77/6.72 | 7.35 мин | 0.0253 | 4.44 / 6.29 мин |
| 2 | 4712 | 4712.0 | 1.91/2.74/4.27 | 2.26/3.34/4.67 | 5.22 мин | 0.0258 | 2.0 / 3.5 мин |
| 3 | 2783 | 2778.8 | 4.76/5.32/6.34 | 5.35/6.11/7.5 | 8.47 мин | 0.02 | 5.37 / 5.05 мин |

Улицы с неуверенной привязкой к зоне:

- bender_core: Главная улица
- bender_core: Коммунистическая улица
- bender_core: Протягайловская улица
- bender_core: Путейская улица
- bender_core: улица Космонавтов
- bender_core: улица Чернышевского
- bender_lipcani: 1-й переулок Кутузова
- bender_lipcani: 2-й переулок Кутузова
- bender_lipcani: Колхозная улица
- bender_lipcani: Колхозный переулок
- bender_lipcani: Красивая улица
- bender_lipcani: Парканская улица
- bender_lipcani: Пограничный переулок
- bender_lipcani: Подольская улица
- bender_lipcani: Подольский переулок
- bender_lipcani: переулок Грибоедова
- bender_lipcani: переулок Иона Солтыса
- bender_lipcani: переулок Энгельса
- bender_lipcani: улица Гайдара
- bender_lipcani: улица Иона Солтыса
- bender_lipcani: улица Кутузова
- bender_lipcani: улица Панина
- bender_lipcani: улица Шмидта
- bender_lipcani: улица Энгельса
- giska: улица Мира
- giska: улица Суворова
- protyagailovka: Главная улица

## K=5

- connected zones: 5/5 · split streets: 17 · exceptions: 199 · uncertain streets: 37

| Зона | адресов | вес | км p50/p75/p90 | мин p50/p75/p90 | макс.разумный | компактность | центр→ / БАМ→ |
|---|---:|---:|---|---|---|---:|---|
| 0 | 441 | 441.0 | 5.65/7.06/8.17 | 6.38/7.87/9.07 | 9.77 мин | 0.0245 | 6.3 / 6.29 мин |
| 1 | 2739 | 2732.0 | 5.25/5.94/6.54 | 5.54/6.47/7.14 | 7.86 мин | 0.0447 | 5.31 / 7.15 мин |
| 2 | 4714 | 4714.0 | 1.91/2.74/4.27 | 2.26/3.34/4.67 | 5.22 мин | 0.0257 | 2.0 / 3.49 мин |
| 3 | 2783 | 2778.8 | 4.76/5.32/6.34 | 5.35/6.11/7.5 | 8.47 мин | 0.02 | 5.37 / 5.05 мин |
| 4 | 3599 | 3598.3 | 4.15/4.72/5.33 | 4.28/5.15/5.85 | 6.53 мин | 0.0465 | 4.1 / 5.95 мин |

Улицы с неуверенной привязкой к зоне:

- bender_core: Главная улица
- bender_core: Коммунистическая улица
- bender_core: Протягайловская улица
- bender_core: Путейская улица
- bender_core: улица Космонавтов
- bender_core: улица Чернышевского
- bender_lipcani: 1-й переулок Кутузова
- bender_lipcani: 2-й переулок Кутузова
- bender_lipcani: Колхозная улица
- bender_lipcani: Колхозный переулок
- bender_lipcani: Красивая улица
- bender_lipcani: Парканская улица
- bender_lipcani: Пограничный переулок
- bender_lipcani: Подольская улица
- bender_lipcani: Подольский переулок
- bender_lipcani: переулок Грибоедова
- bender_lipcani: переулок Иона Солтыса
- bender_lipcani: переулок Энгельса
- bender_lipcani: улица Гайдара
- bender_lipcani: улица Иона Солтыса
- bender_lipcani: улица Кутузова
- bender_lipcani: улица Панина
- bender_lipcani: улица Шмидта
- bender_lipcani: улица Энгельса
- giska: улица Мира
- giska: улица Суворова
- parkany: Садовая улица
- parkany: улица Анатолия Макалича
- parkany: улица Благоева
- parkany: улица Гоголя
- … и ещё 7

## Оговорки

- Время рассчитано по свободному потоку: без пробок, задержек на перекрёстках, парковки и передачи заказа. Это **нижняя граница**, а не обещанное время доставки.
- Связность зоны измерена по дорожному графу; разбиение полигона на части — артефакт отрисовки.

## Не сделано намеренно

- Победитель K **не выбран** — нужны решения владельца и тарифы такси.
- Денежные цены и тарифы **не назначались**; поля калибровки такси остаются null (`supplied=False`).
- Tier C (1-2 изолированных дома) — **не обслуживается**: исключён из зон, центров, кластеризации и перцентилей.
- Интеграция с Direct не выполнялась.
