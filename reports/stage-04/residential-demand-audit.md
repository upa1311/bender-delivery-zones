# Stage 04 — residential delivery-demand audit

- Generated (UTC): `2026-07-23T21:35:04Z`
- zones: **False** · tariffs: **False** · routing graph: **False** · Direct: **False**

> Рабочая территория создана по жилой застройке (Tier A + Tier B) и указаниям владельца. Это ещё не четыре зоны доставки и не тарифы.

## Streets by demand tier

- **A (standard)**: 318 · **B (low density)**: 3 · **C (manual/fringe)**: 7

| Территория | A | B | C | адреса | Δплощадь |
|---|---:|---:|---:|---:|---:|
| Бендеры (`bender_core`) | 204 | 1 | 0 | 5845 | 17.9802 → 13.0298 км² (−27.53%) |
| Липканы (`bender_lipcani`) | 18 | 0 | 1 | 288 | 3.0678 → 1.4006 км² (−54.34%) |
| Протягайловка (`protyagailovka`) | 29 | 0 | 5 | 715 | 16.6775 → 2.5153 км² (−84.92%) |
| Гиска (`giska`) | 29 | 0 | 1 | 623 | 30.8582 → 2.8693 км² (−90.7%) |
| Парканы (`parkany`) | 38 | 2 | 0 | 4508 | 82.4359 → 6.4859 км² (−92.13%) |

## Buildings excluded from demand

- outbuildings (сараи/гаражи/теплицы): **135**
- non-residential (склады/промышленность/торговля): **275**
- abandoned/ruin: **18** · construction: **5** · unknown: **0**
- addresses included: **11979** · confirmed residential customers: **14473**

## Isolated fringe streets (Tier C, not connected to core)

- bender_lipcani: улица Панина — `uncertain_or_disconnected_evidence`
- giska: Гыска-Золотиевка — `at_most_2_probable_residences`
- protyagailovka: Абрикосовая — `at_most_2_probable_residences`
- protyagailovka: Виноградная — `at_most_2_probable_residences`
- protyagailovka: Вишневая — `at_most_2_probable_residences`
- protyagailovka: Полевая — `at_most_2_probable_residences`
- protyagailovka: Сливовая — `at_most_2_probable_residences`

## Streets with only 1-2 probable residences

- giska: Гыска-Золотиевка — 1 (tier C)
- protyagailovka: Абрикосовая — 2 (tier C)
- protyagailovka: Виноградная — 1 (tier C)
- protyagailovka: Сливовая — 1 (tier C)

## K=4 / K=5 (prepared, NOT selected)

- status: `prepared_not_selected` · winner: `None`
- blocked on: local routing, taxi tariffs
- taxi calibration supplied: `False`

### K=4

- cluster 0: центр 46.838088/29.517627, вес 11852.3, улиц 43
- cluster 1: центр 46.785825/29.434349, вес 1385.0, улиц 27
- cluster 2: центр 46.830063/29.459451, вес 9553.5, улиц 137
- cluster 3: центр 46.810898/29.478084, вес 12091.0, улиц 114

### K=5

- cluster 0: центр 46.838088/29.517627, вес 11852.3, улиц 43
- cluster 1: центр 46.783738/29.425735, вес 1006.0, улиц 18
- cluster 2: центр 46.831233/29.458108, вес 8333.5, улиц 124
- cluster 3: центр 46.794742/29.477001, вес 2796.0, улиц 43
- cluster 4: центр 46.815616/29.476576, вес 10894.0, улиц 93

## Limitations

- Tier C never shapes candidate polygons, zone centres or standard tariffs; it is published as a manual-review layer only.
- Tier B is serviceable but carries low statistical weight (0.3); Tier A 1.0.
- building=yes without an address is weak evidence: it may shape a dense block but is never counted as one customer.
- K=4 and K=5 are PREPARED only. The winner cannot be chosen without local routing and real taxi tariffs, which are not part of this batch.
- Taxi calibration values are null placeholders; no tariff was computed.
- OSM building and address coverage is community-contributed and incomplete.
