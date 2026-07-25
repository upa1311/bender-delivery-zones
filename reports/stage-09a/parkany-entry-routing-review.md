# Stage 09A — Парканы entry routing review

**Read-only. No override, no release, no Direct changes. owner_review_required.**

Sampled first-serviceable Парканы homes (closest to Bender). Every sampled entry:

- verdict **`ROUTE_CORRECT_ZONE_MODEL_REVIEW`**;
- detour ratio **1.34–1.40** (clean — no wandering);
- snap distance **12–19 m** (well under the 40 m threshold);
- **no** flags: no alternative >10 % shorter, no leave-and-re-enter, no
  service/pedestrian snap.

## Conclusion

The road graph and OSRM routing to the Парканы entry are **correct**. The Zone-2
assignment is therefore **not a routing bug** — it is the **cost model**
under-charging the outside-city portion of the trip (median 1.76 km outside the
city). That is a Stage 09 question (city-exit weighting + owner-anchored edges),
not a Stage 09A fix. No route correction is needed or applied.
