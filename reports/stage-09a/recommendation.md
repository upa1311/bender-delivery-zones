# Stage 09A — routing truth: recommendation

**Prove routes before zones. Read-only audit — no OSM edits, no routing override
applied, no zone recomputed to final, no release, no Direct changes. Every item
`owner_review_required`.**

## Verified

- **OSRM serves Борисовка** — it finds a valid car route; there is no total
  disconnection. But the fastest route is a 3–6× detour.
- **The cause is a real barrier**: the Bender rail junction (19 rail crossings of
  the origin→Борисовка straight line, 0 waterways, only 5 car roads crossing a
  railway, 0 tagged car level-crossings).
- **All three origins snap to real roads** (< 40 m); no `WRONG_ORIGIN`.
- **Парканы and Гиска entries route cleanly** (detour 1.07–1.40, no flags) — their
  low zones are a cost-model issue, not routing.

## Audit totals

1 551 suspects audited (in-city Zone-4, Борисовка/Хомутяновка, first
Парканы/Гиска, neighbour zone jumps > 1). Verdicts:

| verdict | count |
|---|---|
| INSUFFICIENT_EVIDENCE | 1 277 |
| OSRM_ROUTE_SELECTION_ISSUE | 166 |
| ROUTE_CORRECT_ZONE_MODEL_REVIEW | 61 |
| WRONG_ADDRESS_SNAP | 35 |
| WRONG_ACCESS_TAG | 12 |

- **Wrong address snaps (> 40 m): 35** — fix the address point coordinate.
- **OSRM route-selection issues: 166** (mostly Борисовка) — a > 10 %-shorter,
  comparable-time route exists; the km used for zoning is inflated by
  duration-optimisation.
- **Missing/broken OSM road: 0 confirmed** — the Борисовка detour is a real rail
  barrier, not a missing road, unless the owner confirms an unmapped crossing.

## Answers to the owner's questions

1. **Does OSRM route to Борисовка correctly?** It routes *validly* but not
   *cheaply*: a real rail barrier forces a long detour, and OSRM picks the
   fastest-by-duration path, which is 27 % longer in km than a comparable-time
   alternative.
2. **Which current Zone 4 are explained by real distance?** Борисовка's — the road
   distance is real (rail barrier). The open question is the km-vs-duration metric,
   not the road graph.
3. **Which need a route fix?** 35 wrong snaps + 12 wrong access tags + (pending
   owner) any unmapped NW rail crossing. Everything else is a **zone-model** review
   (Stage 09), not a route fix.

## Recommended order (unchanged from the owner's mandate)

1. Confirm the road graph near Борисовка (owner: does a direct NW rail crossing
   exist?).
2. Fix the 35 snaps + 12 access tags (address point / OSM tag review).
3. Decide the **km-vs-duration** metric for zoning.
4. Only then apply Stage 09's city-exit weighting with **owner-anchored edges**.
5. Owner review → and only after approval, build a new immutable release.

Until every step is approved: current zones are **not final**, no new immutable
release is created, Direct is not updated, and no price is changed.
