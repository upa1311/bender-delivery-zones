# Stage 10B — corridor-constrained routing truth

**Read-only. No OSM edit, no immutable release, no Direct, no price, no zone.
owner_review_required.** Every number below is computed and written to files —
nothing is hardcoded.

## The eight Stage 10 blockers, and what replaced them

| # | Blocker | Fix |
|---|---|---|
| 1 | only OSRM (no multi-source) | added an INDEPENDENT second shortest-path engine over the same OSM car graph (own Dijkstra); external engines still need JVM/Docker |
| 2 | `owner_corridors()` returned hardcoded results | all corridor facts now generated into `stage10b-corridor-*.csv` and read back from them |
| 3 | corridor forced by ONE waypoint | corridors resolved to an **ordered list of OSM way IDs** + mandatory nodes; route must traverse each, in order |
| 4 | Протягайловка never actually forced | Старого→Мира→**exact entry** enforced; plus every house × every entry |
| 5 | `alternatives=3` called "shortest" | replaced by a **true distance-optimal Dijkstra** (global minimum in metres) |
| 6 | connectivity between approximate coords | connectivity now proven by traversal of the **specific OSM ways**, verified after routing |
| 7 | oneway inferred from distance delta | oneway/access read from **OSM tags** (`oneway`, `oneway:motor_vehicle`, `junction=roundabout`, `access`, `motor_vehicle`, `vehicle`) |
| 8 | full-PBF "proved" by file size | **SHA-256 identity** + `.osrm` build inventory + **live process argv** |

## Graph proof — `FULL_MOLDOVA_PBF_CONFIRMED`

- raw Geofabrik PBF SHA-256 `09ba0c058e89faacac7e1b1e7c8d0fbb…`
- OSRM graph input SHA-256 **identical**: `True`
- `.osrm` build files on disk: **26**
- live server argv: `C:\Users\upa13\OneDrive\Desktop\MSLUPA13\bender-delivery-zones\.osrm\bin\osrm-routed.exe --algorithm mld --port 5000 data/interim/osrm/moldova.osrm`

Independent verification graph: **91 522 nodes / 13 845 car ways / 2 497 turn-restriction
relations**, clipped to a bbox whose nearest edge is ~19.8 km from any computed
route (no clip truncation).

## Corridor enforcement (`stage10b-corridor-verification.csv`)

| corridor | mandatory ways | forward km | reverse km | all ways traversed fwd/rev | oneway by TAGS | turn restr. | verdict |
|---|---|---|---|---|---|---|---|
| BORISOVKA | 6 | 10.5197 | 9.6706 | True/True | True | 0 | CORRIDOR_FULLY_TRAVERSABLE_BOTH_DIRECTIONS |
| KHOMUTYANOVKA_A | 3 | 7.374 | 7.2955 | True/True | False | 0 | CORRIDOR_FULLY_TRAVERSABLE_BOTH_DIRECTIONS |
| KHOMUTYANOVKA_B | 5 | 7.67 | 8.3801 | True/True | False | 1 | CORRIDOR_FULLY_TRAVERSABLE_BOTH_DIRECTIONS |
| PROTYAGAILOVKA | 2 | 6.8657 | 6.882 | True/True | False | 0 | CORRIDOR_FULLY_TRAVERSABLE_BOTH_DIRECTIONS |

Every mandatory way is traversed, in order, in **both** directions — no
`DETOUR_ARRIVAL`. Per-segment tags (highway/oneway/access/bridge/layer/maxspeed)
are in `stage10b-corridor-segments.csv` (16 segments).

## Corrected overstated counts — TRUE shortest vs current OSRM route

| district | homes | overstated >10 % | mean excess km | max excess km |
|---|---|---|---|---|
| Борисовка | 511 | 308/511 | 0.9401 | 2.7575 |
| Гиска | 415 | 0/90 | 0.0308 | 0.1923 |
| Парканы | 3768 | 45/90 | 0.4912 | 0.8686 |
| Протягайловка | 513 | 191/513 | 0.6483 | 1.4646 |
| Хомутяновка | 999 | 94/999 | 0.285 | 2.5492 |

**Total: 638 addresses** carry a current route materially longer than the
true distance-optimal path. This supersedes the earlier counts (166/5/13), which
were computed against `alternatives=3` and therefore **undercounted badly** — most
of all for Хомутяновка, where the earlier "5" is really **94**.

## Protyagailovka: every house × every entry

`stage10b-protyagailovka-entry-matrix.csv` — all **513** verified homes routed
through all **21** graph-connected entries (exact single-source Dijkstra per
entry). The best entry is **not** the same for the whole district: 364 homes are
best served by `Про-028`, but 149 homes by six other entries. **191/513** homes
have a current route >10 % longer than the true shortest.

## Zone ban still in force

No zone, release, Direct change or price is produced. The route-cost metric is
still the owner's decision; these files only establish what the road network
really allows.
