# Stage 09 — Гиска review

**Provisional audit. No release changed, no price added, Direct untouched.
owner_review_required.**

## What we see

**415 serviceable verified homes** in Гиска (separate OSM settlement, boundary
osm_id 12215667). Current v1.1 zones are mostly Zone 3–4.

## Routing quality

Sampled Гиска entries are **clean**: verdict `ROUTE_CORRECT_ZONE_MODEL_REVIEW`,
detour ratio **1.07**, snap 28–32 m, no shorter-alternative or re-entry flags. The
road graph to Гиска is fine.

## City-exit weighting

Гиска routes leave the city, so the outside-city km are upweighted. Under variant
A the recompute moves **214 of 415 down and 0 up** — again the edge-rescaling
effect: Гиска's own out-of-city distance stretches the upper edges. Which part of
Гиска falls in each zone is reported per-home in
`docs/data/stage-09-current-vs-generalized.csv` and the QA map.

## Verdict

Гиска is **route-correct**; its zoning is a **cost-model / edge-calibration**
question, like Парканы. The city-exit weighting is directionally right but must be
applied with owner-anchored edges, not an auto re-quantile. → owner_review. No
change applied.
