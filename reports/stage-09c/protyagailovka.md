# Stage 09C — Протягайловка (full audit, Corridors A & B)

**Read-only. No OSM edit, no release, no Direct, no price, no new zone.
owner_review_required.** Stage 09A did not audit Протягайловка as a separate
direction — this does.

Every **513** verified Протягайловка home
(`docs/data/stage-09c-protyagailovka-comparison.csv`) routed from the central
origin: unrestricted fastest, shortest-distance, forced Corridor A, forced
Corridor B, provisional driver-cost, forward and reverse.

| measure | value |
|---|---|
| homes | 513 |
| overstated current route (>10 % over best valid) | **13** |
| homes where Corridor A gives the best route | 0 |
| homes where Corridor B gives the best route | 0 |
| provisional proposed-zone changes (shortest-km basis) | 12 (6 cheaper) |

The Старого → Мира → Протягайловка continuation is traversable in OSRM (Старого→
Мира 2.09 km forward / 2.77 km reverse — oneway-asymmetric). Corridors A/B never
beat the unrestricted route into Протягайловка, so no corridor shortens it; **13**
homes have a mildly overstated current route (duration-vs-distance), flagged for
owner review. Provisional proposed zones are recorded for review only — **no zone
is republished**.
