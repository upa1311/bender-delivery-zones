# Stage 09 — Парканы entry review

**Provisional audit. No release changed, no price added, Direct untouched.
owner_review_required.**

## What we see

The homes at the **start of Парканы** (nearest to Bender) are currently **Zone 2**.
For the 60 closest Парканы homes: median origin-weighted road km **3.48**, which
falls in the current Zone-2 band (2.42–4.08 km).

## Why this looks wrong

Those routes already leave the city: median **outside-city km = 1.76**. Under the
owner's local model that 1.76 km costs ~10 rub/km, not ~6. Applying the city-exit
weight:

```
equivalent_city_km(median) ≈ 4.65 km   (vs raw 3.48 km)
```

So on the **generalized cost** the Парканы entry is materially more expensive than
its raw km suggests — consistent with the owner's intuition that an out-of-city
address should not be as cheap as a mid-city Zone-2 address.

## Routing is correct here

Stage 09A confirms the Парканы-entry routes are **clean**: verdict
`ROUTE_CORRECT_ZONE_MODEL_REVIEW` for all sampled entries, detour ratio
**1.34–1.40**, snap 12–19 m, no alternative-shorter/​re-entry flags. So this is a
**cost-model** issue, not a routing bug. Nothing about the road graph needs
fixing for Парканы.

## The catch — naive re-quantile does NOT fix it

Recomputing K=4 edges on `equivalent_city_km` does **not** reliably raise the
Парканы entry, because Парканы is **3 772 of 9 784** serviceable homes and its own
distant tail stretches the edges. Net effect for Парканы under variant A: **7 up,
270 down** — most Парканы homes stay in their band or move down as the edges
rescale.

## Verdict

The Парканы-entry Zone-2 assignment is a **genuine cost-model under-charge** for
the out-of-city segment, and the city-exit weighting is directionally right — but
it must be applied with **owner-anchored edges** (e.g. fixed cost thresholds), not
an automatic re-quantile that Парканы's own mass then rescales away. See the
recommendation. → owner_review. No change applied.
