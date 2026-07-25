# Stage 09 — Борисовка review

**Provisional audit. No release changed, no price added, Direct untouched.
owner_review_required.**

## What we see

Nearest-OSM-place labelling puts **511 serviceable verified homes** in Борисовка
(OSM `place=suburb` node 2989167910). Current v1.1 zones:

| Zone | homes |
|---|---|
| 2 | 234 |
| 3 | 108 |
| 4 | 169 |

Борисовка is **inside** the Bender OSM boundary, yet 169 homes are Zone 4.

## Why Zone 4 (raw km)

The Zone-4 homes have an **origin-weighted road distance of ~5.8 km (median),
6.5 km from the central origin, up to 7.3 km** — even though the straight line
from the central origin is only **~1.1–2.2 km**. The whole route is **in-city**
(outside-city km = 0), so the city-exit generalized cost does **not** change
them: `equivalent_city_km ≈ raw_km` for Борисовка.

So Борисовка Zone 4 is **not** a city/out-of-city weighting problem. It is driven
entirely by a **long in-city road distance**, which Stage 09A shows is a **3–6×
detour** over the straight line (median detour ratio 3.39, max 6.30). See
`reports/stage-09a/borisovka-routing-review.md`.

## What the generalized recompute does to Борисовка

Recomputing K=4 edges on `equivalent_city_km` (variant A) moves **all 169** Zone-4
Борисовка homes **down** — 126 → Zone 2, 43 → Zone 3. But this is largely an
**edge-rescaling artefact**: the distant Парканы tail (eq up to ~13 km) stretches
the upper edges (Zone-4 edge 9.69 → 13.65 km), pulling every in-city home into a
lower band. This is **not** evidence that Борисовка "should" be Zone 2 — it is a
warning that a naive re-quantile on the generalized cost is the wrong instrument
(see the recommendation).

## Verdict

Борисовка Zone 4 is a **routing-truth + metric question**, not a city-exit
question:

1. A **real railway barrier** (Bender rail junction) separates the central origin
   from Борисовка — the road distance is genuinely long
   (`reports/stage-09a/borisovka-road-connectivity.md`).
2. The zone uses the **fastest-by-duration** route (e.g. Кишинёвская 1: 6.57 km /
   411 s) while a **27 %-shorter comparable-time** route exists (4.77 km / 427 s).
   For a **km-based** tariff this over-states Борисовка's distance.

→ **owner_review**: (a) confirm the railway crossings/road graph near Борисовка;
(b) decide whether a km-based tariff should use the shortest comparable-time route
instead of the fastest-by-duration route. Either fix would move most Борисовка
Zone-4 homes to Zone 3 **without** any city-exit weighting. No change is applied
here.
