# Stage 10C — edge-valid routing truth

**Read-only. No OSM edit, no immutable release, no Direct, no price, no zone.
owner_review_required.**

## The ten Stage 10B defects, and what replaced them

| # | Defect | Fix |
|---|---|---|
| 1 | turn restrictions counted, not applied | **stateful edge-based Dijkstra** enforces them: 1546 `no_*`, 421 `only_*` (via=node) and 2 via=way, with `restriction:motorcar`/`motor_vehicle` and `except=` exemptions |
| 2 | barrier nodes ignored | **1387 blocking barrier nodes** (gate/bollard/block/…) now stop passage through the node |
| 3 | `access=delivery` blocked | delivery is **allowed** for a courier van; `private`/`customers` still blocked for transit; most specific key wins |
| 4 | node snapping, partial length not charged | **edge snapping**: projection onto the edge, partial edge length charged, off-road distance reported separately (mean 18.89–18.25 m) |
| 5 | one way per street, greedy | a street is the **edge set of all its OSM ways** (exact-name matched) |
| 6 | huge anchor gaps accepted | consecutive streets need a shared node or a **routed, documented connector**; >50 m ⇒ `CORRIDOR_UNRESOLVED` |
| 7 | Главана silently missing | root cause: OSM calls it **«улица Бориса Главана»**; exact-name lists fix it and a missing mandatory street now fails the corridor loudly |
| 8 | traversal = way_id present | traversal is entry_node → exit_node **within the street's own edges** |
| 9 | oneway Титова "reverse=True" | reverse is computed inside the street's own directed edges, so a oneway street can never be reverse-traversed via a loop |
| 10 | cache not tied to PBF | cache key = **PBF SHA-256 + bbox + graph schema + access profile + restriction parser** versions |

## Graph + build provenance

Edge-valid graph: **193,294 directed edges**, 91,554 nodes,
13,856 ways, 1873 access-blocked ways,
2497 restrictions parsed.
PBF SHA-256 `09ba0c058e89faacac7e1b1e…`, profile `car.lua`
SHA-256 `48bbb716c2b68ce6…`, OSRM `['v26.7.3']`,
26 `.osrm` outputs hashed (`stage10c-osrm-build-manifest.json`).

## Corridor continuity (`stage10c-corridor-verification.csv`)

| corridor | direction | streets resolved | max gap m | verdict |
|---|---|---|---|---|
| BORISOVKA | forward | 5/6 | 1092.4 | CORRIDOR_UNRESOLVED |
| BORISOVKA | reverse | 3/6 | 1092.4 | CORRIDOR_UNRESOLVED |
| KHOMUTYANOVKA_A | forward | 1/4 | 915.4 | CORRIDOR_UNRESOLVED |
| KHOMUTYANOVKA_A | reverse | 1/4 | 915.4 | CORRIDOR_UNRESOLVED |
| KHOMUTYANOVKA_B | forward | 4/6 | 915.4 | CORRIDOR_UNRESOLVED |
| KHOMUTYANOVKA_B | reverse | 4/6 | 915.4 | CORRIDOR_UNRESOLVED |
| PROTYAGAILOVKA | forward | 1/2 | 330.4 | CORRIDOR_UNRESOLVED |
| PROTYAGAILOVKA | reverse | 0/2 | 330.4 | CORRIDOR_UNRESOLVED |

Every corridor is **CORRIDOR_UNRESOLVED** — not because a street is missing, but
because consecutive named streets of a *bus route* do not touch: the gaps are
73–1092 m of other roads. Per the >50 m rule this cannot be called a continuous
street corridor; each gap's routed connector is documented in
`stage10c-corridor-links.csv` so the owner can see exactly what lies between.

## Recomputed distances (supersede ALL earlier overstated figures)

| district | addresses | routable | overstated >10 % | mean off-road m |
|---|---|---|---|---|
| Борисовка | 511 | 469 | 171/469 | 18.89 |
| Гиска | 415 | 373 | 0/80 | 18.72 |
| Парканы | 3772 | 3752 | 2/88 | 16.07 |
| Протягайловка | 513 | 455 | 95/455 | 19.45 |
| Северный | 7 | 7 | 0/0 | 24.84 |
| Хомутяновка | 999 | 937 | 36/937 | 18.25 |

**Two findings need owner attention.** First, roughly **200 verified addresses are
now UNREACHABLE** once barriers, access and turn restrictions are enforced — they
sit behind a barrier or on a blocked way and need review. Second, the overstated
counts fell sharply versus Stage 10B (e.g. Борисовка 171 vs 308, Хомутяновка 36 vs
94, Протягайловка 95 vs 191): Stage 10B's "true shortest" cut through barriers and
illegal turns, so it understated the legal distance and overstated the gap.

No zone, release, Direct change or price is produced.
