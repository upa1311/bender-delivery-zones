# External tariff boundary audit v1

Goal: determine whether the external service territories (Парканы, Гиска,
Протягайловка) and Северный have a **provable** tariff boundary that would let a
route be split into `in_city_km` + `outside_city_km`. Result: **none is proven in
the current data.** No coordinates are invented. Output:
`data/interim/external-tariff-boundary-anchors-v1.csv`.

## Парканы — пост ГАИ на ул. Котовского

Owner brief describes a GAI post on Kotovskogo, after which the tariff / meter
allegedly changes toward ~10 руб./км. Findings:

1. **Not present** in `config/boundary-candidates.yml`, `docs/data/*.geojson`, or
   any OSM-derived file. Only administrative relations (OSM `9581354` Municipiul
   Bender, `944727` Bender City Council) exist there, marked `selection: none`.
2. Coordinates **cannot be proven** from repository data.
3. Route coverage (how many Парканы routes pass the point) — **unknown** without
   the point.
4. Alternative entries — **unknown**.
5. City/outside split — **not derivable** without a proven crossing.

Verdict: `UNKNOWN_REQUIRES_OWNER_MAP_CONFIRMATION`. The anchor row carries empty
lat/lon on purpose.

## Гиска and Протягайловка

No single proven tariff boundary. Протягайловка has several corridor files
(`stage-09c-protyagailovka-comparison.csv`, `stage10b-protyagailovka-*`), but per
the owner's instruction nothing is derived from corridor geometry without a
provable crossing, so no outside length is assigned. Both stay
`OWNER_BOUNDARY_DECISION_REQUIRED`. Гиска's boundary is **not** copied from
Парканы.

## Северный

Evidence-collection only (`severny_verified_addresses` = 7). Not auto-classified
as Varnita, city, or external. `OWNER_BOUNDARY_DECISION_REQUIRED`.

## Consequence

Because no external boundary is proven, the external city/outside split is
`OUTSIDE_SPLIT_UNKNOWN` for all 4,350 external addresses. Their taxi / effective /
hybrid economics are given only as an uncertainty bracket in commit 2, never as a
tariff. The owner must confirm the Kotovskogo anchor (and Гиска / Протягайловка
corridors) on a map before any external segment pricing can be verified.
