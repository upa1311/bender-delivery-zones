# Probability sample checkpoint v1

| Measure | Value |
|---|---:|
| Selected | 400 |
| `PREEXISTING_LINKED` (derived from selection-time links) | 33 |
| Eligible for new random review | 367 |
| `NEW_RANDOM_BATCH` reviewed | 100 |
| Second-phase selection rule | `FIRST_N_ELIGIBLE_IN_FROZEN_SAMPLE_ORDER` |
| Second-phase batch size | 100 |
| Total reviewed | 133 |
| Exact + normalized | 63 |
| Descriptive unweighted reviewed rate | 47.37% |
| Second-phase probability, linked rows | 1 |
| Second-phase probability, new random batch | 100/367 (27.247956%) |
| Corrected two-phase Hájek estimate | 55.73% |
| Design-based confidence interval | Unavailable pending larger/completed probability review |

Because fewer than 300 probability rows are reviewed, this checkpoint is not a
final estimate for the 9,216-address population. The former first-stage-only 55.13%
estimate and effective-n Wilson approximation are withdrawn because they did not
account for the unequal second-phase review probabilities.

## Unweighted reviewed results by territory

| Territory | Reviewed | Exact + normalized | Rate |
|---|---:|---:|---:|
| Бендеры | 72 | 43 | 59.72% |
| Гиска | 16 | 2 | 12.50% |
| Парканы | 33 | 12 | 36.36% |
| Протягайловка | 12 | 6 | 50.00% |

## Unweighted reviewed results by street-size post-stratum

| Canonical addresses on street | Reviewed | Exact + normalized | Rate |
|---|---:|---:|---:|
| 1–5 | 11 | 5 | 45.45% |
| 6–25 | 38 | 18 | 47.37% |
| 26+ | 84 | 40 | 47.62% |
