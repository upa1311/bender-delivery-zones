# Probability sample checkpoint v1

| Measure | Value |
|---|---:|
| Selected | 400 |
| `PREEXISTING_LINKED` (derived from selection-time links) | 33 |
| Eligible for new random review | 367 |
| `NEW_RANDOM_BATCH` reviewed | 267 |
| Second-phase selection rule | `FIRST_N_ELIGIBLE_IN_FROZEN_SAMPLE_ORDER` |
| Second-phase batch size | 267 |
| Total reviewed | 300 |
| Exact + normalized | 144 |
| Descriptive unweighted reviewed rate | 48.00% |
| Second-phase probability, linked rows | 1 |
| Second-phase probability, new random batch | 267/367 (72.752044%) |
| Corrected two-phase Hájek estimate | 51.98% |
| Design-based confidence interval | Unavailable pending larger/completed probability review |

This is a 300/400 interim checkpoint, not a final exact count for the 9,216-address
population. The former first-stage-only 55.13% estimate and effective-n Wilson
approximation remain withdrawn because they did not account for unequal
second-phase review probabilities.

## Unweighted reviewed results by territory

| Territory | Reviewed | Exact + normalized | Rate |
|---|---:|---:|---:|
| Бендеры | 152 | 89 | 58.55% |
| Гиска | 28 | 6 | 21.43% |
| Парканы | 92 | 29 | 31.52% |
| Протягайловка | 28 | 20 | 71.43% |

## Unweighted reviewed results by street-size post-stratum

| Canonical addresses on street | Reviewed | Exact + normalized | Rate |
|---|---:|---:|---:|
| 1–5 | 19 | 9 | 47.37% |
| 6–25 | 84 | 41 | 48.81% |
| 26+ | 197 | 94 | 47.72% |
