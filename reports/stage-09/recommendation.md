# Stage 09 — recommendation (K=4, NOT published)

**Provisional audit. No immutable release was changed, no new release was
published, no price/fee/payout was added, Direct was not touched. Every number
here is `owner_review_required`.**

## Headline

The current Zone 1–4 rank homes by **origin-weighted OSRM road km only**. That
mixes two different problems that must be fixed separately:

1. **Out-of-city homes are under-charged** (Парканы/Гиска entries) — a **cost
   model** gap the city-exit weighting addresses.
2. **Some in-city homes look too expensive** (Борисовка/Хомутяновка Zone 3–4) — a
   **routing-truth + metric** issue (a real rail-belt detour and a
   duration-vs-distance mismatch), NOT a weighting issue.

## Numbers

| Edge set (K=4 upper edges, km) | Zone 1 | Zone 2 | Zone 3 | Zone 4 |
|---|---|---|---|---|
| current v1.1 | 2.424 | 4.076 | 5.577 | 9.692 |
| audit recompute on **raw** km (sanity) | 2.477 | 4.125 | 5.727 | 9.758 |
| generalized `eq_km`, weights A (85/15) | 3.523 | 6.073 | 8.376 | 13.646 |
| generalized `eq_km`, weights B (85/10/5) | 3.478 | 6.022 | 8.326 | 13.580 |

The raw-km recompute reproduces the current edges (validates the pipeline). The
generalized edges widen because outside-city km are multiplied by 1.667.

- Homes changing zone (generalized vs current): **A = 3 839 / 9 784, B = 3 814**.
- **Direction: 3 832 down, 7 up.** Almost all moves are *downward*.
- Switch-point sensitivity (`stage-09-sensitivity.json`): **4 727** homes have a
  route that leaves the city; **729** are **unstable** across the three switch
  scenarios (boundary / −300 m / +300 m); B vs A moves 423, C vs A moves 306.

## The trap — do NOT auto-republish the generalized recompute

A naive re-quantile on `equivalent_city_km` is the **wrong instrument**: Парканы
(3 772 of 9 784 homes) and its distant tail (eq up to ~13 km) **stretch the upper
edges**, so nearly everyone drifts *down* — and the Парканы entry the owner wanted
to raise is not reliably raised. The weighting is directionally correct; the
**edge derivation is not**.

## Recommendation (for owner review, no publish)

1. **Keep K=4.** Adopt `equivalent_city_km` (in-city + outside-city×1.667) as the
   cost axis **once the owner confirms the switch point** and the 6/10 rate ratio.
2. **Do NOT set edges by auto-quantile.** Use **owner-anchored cost thresholds**
   (fixed km/eq bands the owner endorses), so the Парканы entry rises and a small
   dense district cannot rescale the whole city.
3. **Resolve Борисовка/Хомутяновка in Stage 09A first** — confirm the rail-belt
   crossings and decide the **km-vs-duration** metric. Those two fixes move most
   Борисовка Zone-4 homes to Zone 3 with **no** weighting change.
4. **Send the 729 switch-point-unstable homes to owner review** individually.
5. Only after 1–4 and owner approval should a **new** immutable release be built.
   Until then the current zones are **not final**, no release is published, Direct
   is not updated, and no price changes.

## Provenance (not money)

city rate 6, outside rate 10 (owner's words), multiplier 1.667, switch point
unknown (Bender OSM boundary used as a provisional proxy), `owner_review_required`.
`equivalent_city_km` is a relative difficulty coefficient, never a Direct tariff.
