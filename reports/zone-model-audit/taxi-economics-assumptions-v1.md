# Taxi economics assumptions v1

**Every number here is OWNER-PROVIDED OPERATIONAL EVIDENCE, not a licensed
tariff.** `config/taxi-calibration.yml` stays `null` and untouched; these values
live only in this candidate analysis.

## Assumptions (руб. ПМР)

| Parameter | Value | Type |
|---|---|---|
| Minimum fare | 18 | owner assumption |
| City rate | 6 /км | owner assumption |
| Outside rate | 10 /км | owner assumption |
| Fixed taxi commission (platform A) | 5 /order | owner assumption |
| Percent kept (platform B) | 65 % (35 % taken) | owner assumption |
| Reference USD rate | 16.36 = 1 USD | reference only |

## Two taxi reference models

- **MODEL A (floor):** `taxi_ref_a = max(18, 6·in_city_km + 10·outside_km)`
- **MODEL B (first 3 city km included):**
  `taxi_ref_b = 18 + 6·max(0, in_city_km − 3) + 10·outside_km`

Which model actually applies is **not asserted**. Both are carried.

## Driver take

- `driver_take_fixed = max(0, taxi_ref − 5)`
- `driver_take_percent = 0.65 · taxi_ref`
- `driver_best_taxi_take = max(driver_take_fixed, driver_take_percent)`

For the small trips typical in Bender the 65 % model usually beats the −5 fixed
model, so `driver_best` tracks `0.65 · taxi_ref`.

## Applicability — CITY ONLY

Because no per-address city/outside split exists, all of the above are computed
**only for the 4,866 pure-city addresses** (Бендеры/Липканы, `outside_km = 0`).
For the 4,350 external addresses (Парканы/Гиска/Протягайловка) the split is
`OUTSIDE_SPLIT_UNKNOWN`; they receive only a lower/upper bracket (whole route at 6
vs 10 руб./км) — see `customer-driver-balance-v1.md`. `effective_km = in_city +
1.6667·outside` (the 1.6667 = 10/6 is a derived assumption, not a fact).
