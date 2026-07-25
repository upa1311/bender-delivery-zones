# Stage 10D — correct bidirectional snaps + transit polyline matching

**Read-only. No OSM edit, no immutable release, no Direct, no price, no zone.
owner_review_required.**

## The blocker, confirmed

Stage 10C snapped to ONE directed edge and accepted arrival only on that edge.
With snapping fixed to return **one physical position and ALL its legal directed
states**, the result is unambiguous:

| district | addresses | routable | unreachable | directed states / snap | mean off-road m |
|---|---|---|---|---|---|
| Борисовка | 511 | 511 | 0 | 1.82 | 19.18 |
| Гиска | 415 | 415 | 0 | 2.0 | 18.76 |
| Парканы | 3772 | 3772 | 0 | 2.0 | 16.19 |
| Протягайловка | 513 | 513 | 0 | 2.0 | 19.27 |
| Северный | 7 | 7 | 0 | 2.0 | 25.44 |
| Хомутяновка | 999 | 999 | 0 | 2.0 | 18.53 |

**0 of 6 217 addresses are unreachable.** Every "UNREACHABLE" in Stage 10C was an
artefact of single-direction snapping, exactly as reported. The Stage 10C
unreachable and overstated counts are withdrawn.

## What changed in the routing core

| # | Blocker | Fix |
|---|---|---|
| 1-2 | one directed state per snap | snap returns the physical position plus **every** legal directed state; source seeds BOTH ends of a bidirectional segment, each with its own partial length; a oneway keeps only the legal direction |
| 3 | arrival/partial length | arrival accepted from **every** legal direction, remaining length measured to the projected point; source and destination on the SAME segment handled in both orders |
| 4 | premature UNREACHABLE | nothing is UNREACHABLE until all directed representations have been tried |
| 5 | grid endpoint snapping | shapely **STRtree `query_nearest`** over per-segment geometry — no first-radius early stop |
| 6 | delivery/destination as transit | **endpoint-aware access**: 192 restricted segments in 8 components, usable only inside the component holding the route's own source or destination |
| 7 | single from/to | multiple `from`/`to` members supported (no_entry / no_exit) |
| 8 | via-way state was just an id | state carries **ordered progress** through the via sequence |
| 9 | no via-way tests | tests cover multi-via progress, early exit, and `only_*` abandonment |
| 10 | connector picked by straight line | connectors are the **minimal legal road path** searched from ALL nodes of one street to ALL of the other, through the same legality engine |
| 16 | retrospective manifest | the old manifest is now `HISTORICAL_UNVERIFIED`; `scripts/build_osrm_with_manifest.sh` writes the next one **atomically** (temp file moved into place only after customize succeeds) |

Graph: 97,955 physical segments, 193,560 directed
edges, 91,677 nodes, 281 blocking barrier nodes,
2497 restrictions (1546 no_* / 421
only_* via-node, 2 via-way).

## Transit corridors — no continuity claim

| corridor | landmark streets present | verdict |
|---|---|---|
| BORISOVKA | 6/6 | TRANSIT_POLYLINE_MISSING |
| KHOMUTYANOVKA_A | 4/4 | TRANSIT_POLYLINE_MISSING |
| KHOMUTYANOVKA_B | 6/6 | TRANSIT_POLYLINE_MISSING |
| PROTYAGAILOVKA | 2/2 | TRANSIT_POLYLINE_MISSING |

Bus **stops are landmarks, not a guaranteed street chain**, so Stage 10C's
"corridor broken" conclusion is withdrawn. Every landmark street is present in the
graph; the minimal **legal road path** between consecutive landmarks is published
in `stage10d-corridor-legal-connectors.csv` as supporting information only.

To conclude anything about continuity we need the EasyWay stop coordinates and the
forward/reverse polyline, map-matched to OSM edges. EasyWay's web is bot-blocked
(HTTP 403) and no polyline was fabricated, so the verdict is
**TRANSIT_POLYLINE_MISSING**.

## Not published

Per the instruction, no unreachable counts, overstated counts or new zones are
published as confirmed beyond the reachability result above; distances are
recorded per address in `stage10d-by-address.csv` for owner review.
