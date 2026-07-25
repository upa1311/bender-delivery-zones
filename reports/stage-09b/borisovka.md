# Stage 09B — Борисовка (corrected)

**Read-only. No OSM edit, no immutable release, no Direct, no price, no new zone.
owner_review_required.**

## This CORRECTS Stage 09A

Stage 09A claimed a proven railway barrier ("≈5 car crossings, 0 level
crossings"). That was wrong — it read only way tags (not nodes) and counted
geometric line crossings, not graph connectivity. Reading OSM **nodes + ways**
and classifying by **shared graph node / grade separation**:

- **116** `railway=level_crossing` **nodes** in the Bender extract (Stage 09A
  reported 0);
- road/rail crossings: **18 LEVEL_CROSSING, 22 BRIDGE, 3 TUNNEL = 43 real car
  crossings**, 21 access-restricted, **0 geometry-only**;
- in the origin→Борисовка corridor specifically: **49 crossings — 19 BRIDGE, 6
  LEVEL_CROSSING (25 real), 75 level-crossing nodes**, including the
  **Кишинёв–Тирасполь primary-highway bridge** over the rail.

**The rail belt is NOT a barrier.** Борисовка is crossable in many places.

## So why Zone 4?

It is a **duration-vs-distance metric** problem plus **service-segment routing**,
not distance and not a barrier:

- Segment validation of the fastest-time route (OSRM `annotations=nodes` mapped
  to OSM ways): **169 of 177** validated Борисовка routes touch a `service` or
  access-restricted segment → **OWNER_REVIEW_ROUTE**. The zone must not be taken
  from these routes.
- **166 of 511** Борисовка homes have a valid route **>10 % shorter** than the
  fastest-time route used for zoning. Example Кишинёвская 1: fastest-time
  6.57 km / 411 s (uses a service segment) vs shortest 4.77 km / 427 s.
- Forcing the route through **each** cataloged entry never beats OSRM's
  unrestricted route (120 Борисовка entry-routes, min Δ ≈ 0), so the problem is
  **not** a wrong/missing entry — OSRM already uses a good crossing.

## Verdict

Борисовка Zone 4 rests on **fastest-by-duration km inflated by service-segment
detours**, over a rail belt that is actually crossable. This is
**OWNER_REVIEW_ROUTE + metric choice**, not a real cost and not a routing bug to
"fix" by adding a road. → owner picks the route-cost metric
(`reports/stage-09b/route-metric-decision.md`); no zone is proposed here.
