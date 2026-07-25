# Stage 09B — recommendation

**Read-only audit. No OSM edited, no immutable release, no Direct, no price, no
new zone. Every item owner_review_required.**

## Corrections to Stage 09A (which is why it was rejected)

1. **The railway barrier claim is refuted.** Reading OSM **nodes** finds **116
   level_crossing nodes**; proper classification finds **43 real car crossings**
   (18 level, 22 bridge, 3 tunnel), **0 geometry-only**, incl. the
   Кишинёв–Тирасполь primary-highway bridge. Stage 09A's "≈5 crossings, 0 level
   crossings" was a geometry/way-only artefact.
2. **All 3 origins are now routed** (not just ORIGINS[0]).
3. **Парканы/Гиска filtered by settlement_ru** (was wrongly district_ru).
4. **steps=true + annotations=nodes**: every fastest route is validated
   segment-by-segment against OSM way tags.
5. **Access/oneway/service come from the ACTUAL route segments**, not the nearest
   geometric road.
6. **level_crossing on nodes is read**; crossings classified LEVEL_CROSSING /
   BRIDGE / TUNNEL / GEOMETRY_ONLY / BROKEN_CONNECTIVITY / UNKNOWN by **shared
   graph node** and bridge/tunnel/layer, not line intersection.

## What the corrected audit shows

- **Borisovka Zone 4 is a metric problem, not a barrier**: 169/177 fastest
  routes use a service/restricted segment (OWNER_REVIEW_ROUTE); 166/511 homes
  have a >10%-shorter valid route. Duration-optimisation + service detours inflate
  the km used for Zone 4.
- **Parkany / Giska**: routes correct and unambiguous; 0 metric gaps → cost-model
  question only.
- **Khomutyanovka**: mostly valid (26/223 review); real in-city distance.
- **Severny**: no verified homes, no OSM place → owner_review.
- **Entries**: forcing routes through each cataloged entry never beats OSRM's
  unrestricted route — no missing/better entry.

## Zone ban (per the owner's mandate)

No new zone is assigned, because not all conditions are met:
- OWNER_REVIEW_ROUTE homes (195 of the validated set, 169 in Борисовка) are not
  cleared;
- the owner has not chosen the route-cost metric
  (`reports/stage-09b/route-metric-decision.md`);
- shortest-vs-fastest is unresolved for the affected homes.

Next, for the owner: (1) pick the metric (prefer shortest **valid** distance or
generalized, not duration-only); (2) confirm/repair the service-segment access on
the flagged routes; (3) then re-run Stage 09 edges with owner-anchored thresholds
on valid routes; (4) only after approval, build a new immutable release. Until
then: current zones NON-final, no release, Direct untouched, no price change.
