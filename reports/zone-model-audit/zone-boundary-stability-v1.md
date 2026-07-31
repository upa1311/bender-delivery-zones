# Zone boundary stability v1

Two independent checks: (1) real validation against the manual Yandex controls,
and (2) geometric near-threshold / same-street / neighbour-discontinuity density.
Route perturbation is reported only as a supplementary geometric sensitivity — it
is **not** called manual validation.

## 1. Real manual-control validation (router expected_km vs Yandex km)

Source: `docs/data/manual-yandex-route-controls.csv` (86) +
`docs/data/manual-yandex-measurements.csv` (90 Yandex measurements).
`data/interim/zone-model-manual-control-validation-v1.csv` holds every row.

**Honest coverage:** only **76** of 86 controls have a `uid` inside the 9,216
population (10 are Северный / Балка / Кавказ / Ленинский, outside it), and only
**28** of those are core-city (Бендеры). All 86 control addresses lie in outer
districts — there is **no** manual control in the dense city centre. So city
models are validated on 28 real controls, not 90.

For each control: router zone = zone of the address `expected_km`; Yandex zone =
zone of the manually measured Yandex km; a "flip" is a zone disagreement.

| Model | Controls | Same zone | 1-zone flip | Multi-zone flip | Flip control IDs |
|---|---:|---:|---:|---:|---|
| CITY_K4R (city) | 28 | 25 (89 %) | 3 | 0 | MY-001, MY-004, MY-062 |
| CITY_K5R (city) | 28 | 22 (79 %) | 6 | 0 | MY-001, MY-002, MY-064, MY-081, MY-083, MY-085 |
| CITY_K6R (city) | 28 | 18 (64 %) | 10 | 0 | MY-001, MY-002, MY-004, MY-064, MY-065, MY-066, MY-072, MY-081, MY-083, MY-085 |
| BASELINE_4 (all 76) | 76 | 61 (80 %) | 15 | 0 | (see CSV) |
| K5R full (all 76) | 76 | 60 (79 %) | 16 | 0 | (see CSV) |

**Reading:** on the real controls, more zones = more Yandex/router disagreements.
CITY_K4R is the most robust (89 % agreement, 3 flips); CITY_K5R drops to 79 %;
CITY_K6R to 64 %. This is measured, not simulated.

## 2. Geometric density (city models)

| Model | ≤50 m of threshold | same-street splits | diff-zone pairs ≤100 m | max price jump руб |
|---|---:|---:|---:|---:|
| CITY_K4R | — | — | 1,750 | 13 |
| CITY_K5R | — | — | 2,766 | 15 |
| CITY_K6R | — | — | 4,163 | 15 |

Neighbour discontinuities (`data/interim/zone-neighbour-discontinuities-v1.csv`,
235,842 city pairs within 250 m) rise sharply with K: K=4 splits the fewest close
neighbours into different-price zones, K=6 more than doubles it.

## 3. Supplementary perturbation (geometry only, NOT validation)

Route ±3 % / ±5 % / ±10 % flip counts are a geometric fragility indicator and are
**not** a substitute for the manual-control check in section 1. They are retained
only to show that flip counts grow with K, consistent with the manual result.

## Conclusion

Both the real manual controls and the geometric density agree: **K=4 is the most
stable, K=6 the least.** K=5 is intermediate — the balance-vs-stability trade the
owner decides on.
