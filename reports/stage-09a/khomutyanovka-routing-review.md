# Stage 09A — Хомутяновка routing review

**Read-only. No override, no release, no Direct changes. owner_review_required.**

999 Хомутяновка suspects audited. Verdicts:

| verdict | homes |
|---|---|
| INSUFFICIENT_EVIDENCE (route plausible, no clearly shorter path) | 949 |
| ROUTE_CORRECT_ZONE_MODEL_REVIEW | 21 |
| WRONG_ADDRESS_SNAP (snap > 40 m, max 108 m) | 15 |
| WRONG_ACCESS_TAG (snapped to a `service` road) | 10 |
| OSRM_ROUTE_SELECTION_ISSUE | 4 |

Also: **17 routes leave and re-enter the city**, median detour ratio **2.74**.

## Conclusion

Хомутяновка Zone 3 is **mostly route-correct** — a genuine ~5 km in-city road
distance driven by the same rail-belt geometry as Борисовка (to a smaller degree).
A **~25-home tail** has real routing defects to fix at owner review:

1. **15 WRONG_ADDRESS_SNAP** — the address point snaps > 40 m onto a wrong road;
   re-check the building/point coordinate.
2. **10 WRONG_ACCESS_TAG** — snapped onto a `service` road; verify the OSM
   `access`/`service` tags of the access way.
3. **17 leave-and-re-enter** — the fastest route briefly dips outside the boundary
   for an in-city address; usually a boundary-hugging road, worth an eyeball on the
   QA map.

No route correction is applied here.
