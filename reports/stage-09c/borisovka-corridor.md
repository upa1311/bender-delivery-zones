# Stage 09C — VERIFIED BORISOVKA CORRIDOR (corrects Stage 09A)

**Read-only. No OSM edit, no immutable release, no Direct, no price, no new zone.
owner_review_required.**

## Owner ground truth

Bus route **№5** (EasyWay ID 21, «Железнодорожный вокзал Бендеры-1 — ул. Дружбы —
ул. 50 лет ВЛКСМ») reaches Borisovka over the **Кишинёв–Тирасполь ПУТЕПРОВОД** —
a bridge / grade-separated interchange, **not** a level crossing. Стage 09A's "0
tagged car level-crossings → barrier" never disproved this corridor, because it
is a **bridge**, not a crossing.

## The corridor exists and is in the OSRM graph

Matched to OSM (`docs/data/stage-09c-corridor-osm-match.csv`,
`public-transport-corridor-osm-match.csv`): **67 car ways**, every owner-named
street present —

| street | highway | note |
|---|---|---|
| Кишинёв–Тирасполь | primary | **bridge=yes, layer=2, oneway=yes** (путепровод + ramps) |
| улица Ермакова | primary | |
| улица Петровского | residential | |
| Тираспольская / Титова / Б. Хмельницкого / 50 лет ВЛКСМ / Осипенко / Дружбы / Кишинёвская | residential–tertiary–primary | |

**All ways are present in the local PBF and the OSRM graph** (`present_in_osrm_graph=true`
for every one). So there is **no ROAD_GRAPH_MISMATCH** and **no missing road**.

## The Stage 09A contradiction — resolved

- Стage 09A's `borisovka-routing-review` said the route "loops ~3 km south". That
  is true **only of the fastest-by-DURATION route** (6.57 km / 411 s), which
  takes a southern arc via Бендерского Восстания / Сергея Лазо and touches a
  `service` segment.
- The **shortest-distance route** (4.77 km / 427 s) goes **NORTH over the
  путепровод** — the owner's route-5 corridor — reaching lat 46.841. This is the
  route the published control geometry showed. **Both are real; they are just
  different metrics.** OSRM picks the south loop as "fastest" only because it is
  **16 s** quicker.

So the earlier phrase **"a real railway barrier forces the car south" is WRONG**
and is corrected: the northern путепровод corridor exists, is car-legal, is in
the graph, and is 27 % shorter; OSRM simply optimises duration, not distance.

## Four-route comparison (`stage-09c-corridor-route-comparison.csv`)

| home | fastest (dur) | owner corridor (via путепровод) | shortest | zone f→s |
|---|---|---|---|---|
| Кишинёвская 1 | 6.57 km / 411 s | 5.84 km / 530 s | 4.77 km / 427 s | 4 → 3 |
| Борисовка start | 7.19 km / 476 s | 6.02 km / 585 s | 4.95 km / 476 s | 4 → 3 |
| Борисовка mid (Титова 60) | 3.52 km / 311 s | 4.58 km / 414 s | 3.52 km | 2 → 2 |
| Борисовка far | 4.42 km / 406 s | 5.48 km / 509 s | 4.42 km | 3 → 3 |

(The forced-waypoint "corridor" figure is slightly longer than the true shortest
because forcing an exact bridge point adds a small detour; the genuine
shortest/corridor route is 4.77–4.95 km for the far homes.)

## Origin check

Central origin (29.48313, 46.82388) is **south of the rail belt in the city
core** (correct city side), 1.92 km from the путепровод — **not** east of the
interchange nor on the wrong side of the tracks (`reports/stage-09c/_origin.json`).

## Zone impact

If the km tariff used the **shortest valid (corridor)** route instead of the
fastest-by-duration route, **168 of 511** Borisovka homes move to a **cheaper**
zone (mostly Zone 4 → 3): `docs/data/stage-09c-borisovka-zone-impact.json`.
**owner_review — no zone is republished.**

## Directions

The interchange ramps are **oneway**, so the forward (to Borisovka) and reverse
corridors differ; both are recorded in `public-transport-corridors.geojson`. Note
EasyWay's web is bot-blocked (HTTP 403), so its polyline was not fetched or
fabricated — the corridor is verified against OSM directly, which is the graph
OSRM uses.

## Verdict

`ROUTE_METRIC_ISSUE` (duration-vs-distance) + `service`-segment fastest routes —
**NOT a barrier, NOT a missing road, NOT a graph mismatch.** Owner decides the
route-cost metric before any zone is recomputed.
