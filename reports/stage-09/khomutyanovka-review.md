# Stage 09 — Хомутяновка review

**Provisional audit. No release changed, no price added, Direct untouched.
owner_review_required.**

## What we see

Nearest-OSM-place labelling puts **999 serviceable verified homes** in Хомутяновка
(OSM `place=suburb` node 3085770191). Current v1.1 zones: Zone 1 = 29, Zone 2 = 1,
**Zone 3 = 829**, Zone 4 = 140.

## Why Zone 3

Хомутяновка is **inside** the Bender boundary; its routes are essentially all
**in-city** (outside-city km ≈ 0), so the city-exit weighting does not change
them. The Zone-3 assignment comes from an **in-city road distance of ~5.0 km
(median, up to 7.45 km)** from the central origin, versus a much shorter straight
line — median detour ratio **2.74**.

## Routing quality (Stage 09A)

Of 999 Хомутяновка suspects: **949 INSUFFICIENT_EVIDENCE** (route plausible, no
clearly shorter alternative), **21 ROUTE_CORRECT_ZONE_MODEL_REVIEW**, **15
WRONG_ADDRESS_SNAP** (snap > 40 m, max 108 m), **10 WRONG_ACCESS_TAG** (snapped to
a `service` road), and **17 routes leave and re-enter the city**. So the bulk of
Хомутяновка Zone 3 is a **real in-city road distance** (same rail-belt geometry as
Борисовка, to a lesser degree), with a **small tail of snap/service-road cases**
that need address-point or OSM-tag review.

## Verdict

Хомутяновка Zone 3 is **mostly route-correct** (real ~5 km in-city road distance),
not a city-exit issue. Actions → owner_review:

1. Fix the **~25 snap/service/re-entry cases** (address point or OSM tag), which
   currently inflate a few homes.
2. Decide the **duration-vs-distance** metric (as for Борисовка): a km tariff on
   the shortest comparable-time route would slightly lower some Хомутяновка homes.

No change applied here.
