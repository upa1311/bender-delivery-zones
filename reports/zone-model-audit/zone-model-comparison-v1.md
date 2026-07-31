# Zone-model comparison — route distance models v1

> **DIAGNOSTIC ONLY.** The full-population 4R/5R/6R models below describe the
> route_km distribution over all 9,216 addresses. They are **not** deployable city
> tariffs, because 4,350 external addresses have OUTSIDE_SPLIT_UNKNOWN. The city
> tariff decision uses the separate **CITY_K4/K5/K6** models (4,866 city addresses)
> in `owner-decision-pack-v1.md` and the per-K analysis reports.

Route-only comparison over `expected_km` for the 9,216 canonical addresses. Three
reproducible partition methods are compared per K: **quantile** (equal
population), **1-D k-means** (Lloyd, deterministic quantile init), and
**DP-optimal / Jenks** (exact minimum weighted within-class SSE on 0.05 km bins,
matching `config/bands.yml`). Economics (fee, savings, driver gap) are added in
commit 2; this report is the geometric foundation only.

## Thresholds (km)

| Model | Method | Thresholds | Zone shares |
|---|---|---|---|
| BASELINE_4 | released | 2.424 / 4.076 / 5.577 | 18.0 / 20.6 / 37.1 / 24.3 |
| K4R | quantile | 2.939 / 4.642 / 5.546 | 25 / 25 / 25 / 25 |
| K4R | k-means | 2.462 / 4.149 / 5.750 | 18.4 / 21.3 / 40.0 / 20.3 |
| K4R | DP/Jenks | 2.475 / 4.175 / 5.775 | 18.5 / 21.5 / 40.2 / 19.8 |
| K5R | quantile | 2.584 / 4.172 / 4.954 / 5.767 | ~20 each |
| K5R | k-means | 2.190 / 3.690 / 5.004 / 6.222 | 15.6 / 17.1 / 28.8 / 26.2 / 12.4 |
| K5R | DP/Jenks | 2.175 / 3.675 / 4.975 / 6.225 | 15.4 / 17.0 / 28.3 / 26.9 / 12.3 |
| K6R | quantile | 2.301 / 3.740 / 4.642 / 5.204 / 5.937 | ~16.7 each |
| K6R | k-means | 2.057 / 3.340 / 4.497 / 5.570 / 6.978 | 14.7 / 13.9 / 17.5 / 29.4 / 20.8 / **3.7** |
| K6R | DP/Jenks | 2.075 / 3.375 / 4.525 / 5.575 / 6.975 | 14.7 / 14.2 / 17.9 / 28.8 / 20.7 / **3.7** |

## Constraint checks (min/max population share)

Production `config/bands.yml` uses min share 0.12 and max 0.40. Against the
owner's stricter test grid (2 % / 5 % / 10 % min):

| Model | min share | max share | Sliver? |
|---|---:|---:|---|
| BASELINE_4 | 18.0 % | 37.1 % | no; one dominant zone (37 %) |
| K4R natural (DP) | 18.5 % | **40.2 %** | no, but hits the 0.40 cap — one very dominant zone |
| K5R natural (DP) | 12.3 % | 28.3 % | no — most balanced natural partition |
| K6R natural (DP) | **3.7 %** | 28.8 % | **YES** — far zone = 337 addresses, fails 5 % and 12 % |
| K6R quantile | 16.6 % | 16.7 % | no, but ignores the cost structure (forced equal fill) |

## Boundary instability (zone flips under route perturbation)

Count of addresses that change zone under ±3 % / ±5 % / ±10 % route perturbation:

| Model | ±3 % | ±5 % | ±10 % |
|---|---:|---:|---:|
| BASELINE_4 | 1218 | 2029 | 4108 |
| K4R DP | 1206 | 2016 | 4243 |
| K5R DP | 1747 | 2901 | 5554 |
| K6R DP | 1734 | 2953 | 6141 |

Caveat: raw flip counts are not directly comparable across K — more zones means
more interior boundaries and therefore more addresses near *some* threshold. The
50 m / 100 m / 250 m near-threshold counts and same-street splits are added in
commit 2 for a fair per-boundary comparison.

## Preliminary route-geometry reading (NOT a final recommendation)

- The K=4 baseline concentrates **37 %** of addresses in zone 3; natural-break
  K=4 pushes that to **40 %** (the production max-share cap). One dominant middle
  zone is the main geometric weakness of K=4.
- K=5 natural breaks is the most balanced contiguous partition (max share 28 %,
  min 12 %, no sliver).
- K=6 natural breaks creates a **3.7 % sliver far zone** (337 addresses) that
  fails every minimum-share rule; K=6 only "works" if forced to equal quantiles,
  which discards the cost structure.

Route geometry therefore leans **against K=6** and shows K=5 as a plausible
balance improvement over K=4 — but this is geometry only. Whether the extra zone
is *economically* justified (client savings vs driver gap, taxi reference) is
decided in commit 2. **K is not being fitted to a desired answer of 5.**
