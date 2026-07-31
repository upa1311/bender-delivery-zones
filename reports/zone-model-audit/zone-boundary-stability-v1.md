# Zone boundary stability v1

Two independent checks: (1) real validation against the manual Yandex controls
using the **fixed-origin** router km, and (2) geometric neighbour-discontinuity
density. Route perturbation is a supplementary geometric indicator only — it is
**not** called manual validation.

## 1. Real manual-control validation (fixed-origin router km vs Yandex km)

Source: `docs/data/manual-yandex-route-controls.csv` (86) +
`docs/data/manual-yandex-measurements.csv` (90). Full rows:
`data/interim/zone-model-manual-control-validation-v1.csv`. Router km is now the
**fixed-origin** central_km (route from 46.82388, 29.48313), which is
apples-to-apples with Yandex's single-origin measurement.

**Honest coverage:** only **28** of the 90 controls are core-city (Бендеры); the
rest are outer districts or outside the 9,216 population. City models are
validated on 28 real controls.

| Model | Controls | Same zone | Flips | Flip control IDs |
|---|---:|---:|---:|---|
| CITY_K4R | 28 | 25 (89 %) | 3 | MY-002, MY-079, MY-085 |
| CITY_K5R | 28 | 25 (89 %) | 3 | MY-002, MY-073, MY-081 |
| CITY_K6R | 28 | 24 (86 %) | 4 | MY-002, MY-063, MY-073, MY-085 |

**Key correction from the previous (blended-metric) round:** on the fixed-origin
metric **CITY_K5 is exactly as stable as CITY_K4** (both 25/28). The earlier
finding that K5 was less stable (79 %) was an artefact of the blended
`expected_km`, not a real property of five zones.

## 2. Neighbour price discontinuity (city models, fixed-origin)

`data/interim/zone-neighbour-discontinuities-v1.csv` (235,842 city pairs ≤ 250 m):

| Model | diff-zone pairs ≤100 m | max price jump руб | p90 jump |
|---|---:|---:|---:|
| CITY_K4R | 1,667 | 15 | 8 |
| CITY_K5R | 2,628 | 17 | 7 |
| CITY_K6R | 2,424 | 19 | 6 |

K=4 splits the fewest close neighbours into different-price zones; K=5 more, K=6
the sharpest single jumps.

## 3. Operational rounding (recomputed, not just rounded edges)

For CITY_K5R the 0.1 / 0.25 / 0.5 km rounded thresholds were re-run end-to-end
(counts, ±5 % flips, same-street splits) — see
`_route-model-summary-v1.json` → `rounding_recompute`. Rounding to 0.25 km barely
moves counts and slightly *reduces* same-street splits, so a 0.25 km operational
grid is a safe simplification.

## 4. Supplementary perturbation (geometry only, NOT validation)

Route ±3/5/10 % flip counts are retained as a geometric fragility indicator and
are **not** presented as manual validation.

## Conclusion

On the corrected fixed-origin metric, **CITY_K4 and CITY_K5 are equally stable
(89 %)**; K5 additionally gives finer, fairer pricing. K4 wins only on fewer
neighbour discontinuities. K=6 is the least stable. The K4-vs-K5 call is the
owner's.
