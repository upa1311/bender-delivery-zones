# Stage 09B — route-cost metric decision (owner comparison)

**Read-only. No metric is auto-chosen. No zone is proposed until the owner picks
one. No price, no release, no Direct.**

The fastest-by-**duration** route is not automatically the right basis for a
**km-based** tariff. Стage 09B records, per control home and per origin, four
comparable indices (NOT prices) on the chosen route:

| metric | definition | picks |
|---|---|---|
| A — duration | travel time (min) | fastest-time route |
| B — distance | road km | shortest-distance route |
| C — generalized | in_city_km + outside_city_km × 1.6667 | city-exit weighted |
| D — time-value | distance_km + 0.5 × duration_min | blend of B and A |

Data: `docs/data/stage-09b-metric-comparison.csv` (1 733 homes × 3 origins).

## Why it matters (Борисовка)

- **166 / 511** Борисовка homes: the shortest valid route is **>10 % shorter**
  than the fastest-time route. Кишинёвская 1: A/B fastest 6.57 km / 411 s vs
  shortest 4.77 km / 427 s — 27 % less distance for +16 s.
- **169 / 177** validated Борисовка fastest routes touch a `service`/restricted
  segment (OWNER_REVIEW_ROUTE): metric A/B on those is unreliable.
- Парканы, Гиска, Хомутяновка show **~0** such gaps — the metric choice barely
  moves them; their zoning is the Stage 09 cost-model question.

## Recommendation (owner decides, no publish)

1. For a **km/rub tariff**, metric **A (duration-only)** is the wrong basis — it
   inflates rail-adjacent in-city homes via faster-but-longer loops and
   service-segment detours. Prefer **B (shortest valid distance)** or **C
   (generalized)** among **VALID** routes only.
2. **Exclude OWNER_REVIEW_ROUTE homes** (service/restricted segments) from any
   automatic zoning until their access segment is confirmed on the ground.
3. Whatever metric the owner picks, re-run Stage 09's edges with **owner-anchored
   thresholds** (not auto-quantile) on **valid** routes only.

Until the owner selects a metric and clears the OWNER_REVIEW_ROUTE homes: no new
zone, no release, no Direct change, no price.
