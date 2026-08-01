# CITY_K5 far-zone base+distance formula v1 (candidate)

Follows from `balanced-fragmentation-v1.md`: a flat-fee BALANCED tariff needs ~14
steps. For the CITY_K5 middle/far zones (3–5, route_km > 2.875 km) a single
**base + distance** rule replaces those flat steps and satisfies BALANCED at
**100 % coverage**. City-only, fixed-origin km, owner assumptions. **Candidate
only — not applied to production, Direct, releases or GitHub Pages.**

## Formula

```
fee = floor(6 * route_km − 5)        # base = −5 руб, rate = 6 руб/км
```

That is: charge the equivalent taxi (`6 · route_km`) minus the 5-ruble commission,
floored to whole rubles.

## Why it satisfies BALANCED for 100 %

Beyond the taxi floor, `taxi_reference = 6·km` and `driver_best = taxi_reference − 5`.
With `fee = floor(6·km − 5)`:

- `client_saving = 6·km − fee ∈ [5, 6)` → always ≥ 5 (BALANCED client rule holds);
- `driver_gap = (6·km − 5) − fee ∈ [0, 1)` → always ≤ 3 and ≤ 10 % (driver rules hold);
- `fee < taxi_reference` always → client always cheaper than a taxi.

The floor rounds down, which is what guarantees saving ≥ 5 and gap < 1 for every
address simultaneously — no per-zone infeasibility.

## Result

| Metric | Value |
|---|---|
| Far city addresses (zones 3–5) | 2,471 |
| BALANCED-feasible under formula | 2,471 (100 %) |
| Client saving | 5–6 руб (every address) |
| Driver gap | 0–1 руб (every address) |

Per-address detail: `data/interim/zone-k5-far-base-distance-v1.csv`.

## Read

The near zones (1–2) keep a simple flat fee (they are feasible flat); the far
zones use `floor(6·km − 5)`. This is one formula plus two flat near fees — far
simpler and fully BALANCED-compliant versus 14 flat steps. It is a candidate for
owner review, not a production tariff; production prices, Direct and releases are
unchanged.

Verdict: ANALYSIS_COMPLETE / OWNER_DECISION_REQUIRED.
