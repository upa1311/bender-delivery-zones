# Stage 09A — Борисовка routing review

> **CORRECTION (superseded by Stage 09B/09C).** The "railway barrier forces a
> ~3 km southern loop" conclusion below is WRONG. Reading OSM **nodes** finds 116
> level-crossing nodes and 43 real car crossings; the Кишинёв–Тирасполь
> **путепровод** (bridge=yes, layer=2) carries bus route №5 to Borisovka and is in
> the OSRM graph. The rail belt is NOT a barrier. The southern arc is only the
> fastest-by-**duration** route (6.57 km); a 27 %-shorter route (4.77 km) goes
> NORTH over the путепровод. See `reports/stage-09c/borisovka-corridor.md` and
> `reports/stage-09b/`. This is a duration-vs-distance METRIC issue, not a barrier.


**Prove the route before trusting the zone. Read-only; no OSM edits, no override
applied, no release, no Direct changes. owner_review_required.**

## Finding

169 Борисовка homes are Zone 4. Their routes from the central origin are a **3–6×
detour**: median detour ratio **3.39**, max **6.30**. Of the 169, **137 carry
verdict `OSRM_ROUTE_SELECTION_ISSUE`** — a materially shorter valid route exists
than the fastest-by-duration one used for zoning.

Worked example — **Кишинёвская улица 1** (46.83524, 29.46735):

| metric | value |
|---|---|
| straight line from central origin | 1.74 km |
| fastest-by-duration route (zoning basis) | **6.57 km / 411 s** |
| shortest comparable-time alternative | **4.77 km / 427 s** (−27 % km, +16 s) |
| route shape | loops ~3 km **south** (to 46.807) before returning NW |

## Cause — a real railway barrier

`reports/stage-09a/borisovka-road-connectivity.md` /
`docs/data/stage-09a-road-connectivity.json`:

- **125** railway segments in the origin↔Борисовка corridor; **19** cross the
  straight line;
- **0** waterways cross it (so it is rail, not river);
- **199** car roads in the corridor but only **5** actually cross a railway, and
  **0** tagged car level-crossings.

The **Bender rail junction** physically separates the central origin (SE) from
Борисовка (NW). Cars must detour ~3 km south to the nearest crossing, inflating
the road distance to 5–7 km over a ~1.7 km straight line.

## Verdict

Two distinct issues, both `owner_review`:

1. **ROUTE_CORRECT_ZONE_MODEL_REVIEW** — the rail barrier is real, so the long
   road distance is real; a nearby-but-rail-separated home legitimately costs
   more. The question is whether the **zone model** should treat rail-separated
   in-city homes as Zone 4.
2. **OSRM_ROUTE_SELECTION_ISSUE** — zoning uses the fastest-by-**duration** route
   (6.57 km) while a **27 %-shorter, comparable-time** route (4.77 km) exists. For
   a **km-based** tariff this over-states distance; using the shortest
   comparable-time route would move most Борисовка Zone-4 homes to **Zone 3**.

Also flagged: **19 homes WRONG_ADDRESS_SNAP** (snap > 40 m, max 55 m) and 2
`WRONG_ACCESS_TAG` (snapped to service/pedestrian). Those specific points need
address/tag review.

## Not done on purpose

We did **not** invent a road, apply a routing override, or change any zone. If the
owner confirms a direct car-legal NW crossing exists on the ground, a **documented
local routing override** is proposed next (with evidence, `owner_review_required`),
never auto-applied.
