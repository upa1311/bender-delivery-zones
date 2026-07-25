# Stage 09A — Борисовка road-connectivity

**Read-only PBF probe. No OSM data was modified. owner_review_required.**

Corridor between the central origin (29.48313, 46.82388) and Борисовка
(29.46735, 46.83524), bbox `[29.455, 46.820, 29.487, 46.842]`. Source: local
`data/interim/city-extract-12463379.osm.pbf` (same Moldova PBF as the release).

| measure | value |
|---|---|
| straight line origin→Борисовка | 2.16 km |
| railway segments in corridor | 125 |
| railway segments crossing the straight line | 19 |
| waterway segments crossing the straight line | 0 |
| car roads in corridor | 199 |
| car roads with `access=no/private` | 0 (all car-accessible) |
| car roads that actually cross a railway | **5** |
| tagged car level-crossings | **0** |

## Interpretation

The **Bender rail junction** lies directly across the origin→Борисовка line (19
rail crossings of the straight line, no river). Almost no car road in the corridor
crosses the railway (only 5), and OSM tags **0** car level-crossings, so OSRM must
route ~3 km south to the nearest usable crossing. That is the physical cause of
the 5–7 km road distance and the Zone-4 assignment.

## Open question for the owner

Is there a **direct car-legal crossing** of the rail belt toward NW Борисовка on
the ground that is **missing or mis-tagged** in OSM (e.g. an untagged
`railway=level_crossing`, or a connector road not mapped)?

- **If yes** → a documented **local routing override** is proposed (with photo /
  local evidence), `owner_review_required`, and — only after owner approval —
  applied so the shorter path is used. Most Борисовка Zone-4 homes would then drop
  to Zone 3.
- **If no** → the detour is real; Борисовка Zone 4 is route-correct and the
  question becomes the km-vs-duration metric (see the routing review).

No override is applied here. No OSM edit was made.
