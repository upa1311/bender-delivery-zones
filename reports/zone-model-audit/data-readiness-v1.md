# Zone-model audit — data readiness v1

Candidate branch `codex/zone-model-audit-v1`. This report inventories the actual
data that exists before any model is built, so that every downstream number has a
provenance and nothing is invented. No production zone, price, release or routing
artifact is modified.

## 1. Canonical population

| Item | Value | Source |
|---|---|---|
| Canonical address grains | **9,216** | `releases/bender-zones-v1.1/address-registry.json` → `addresses` (immutable) |
| Unique `uid` | 9,216 | same |
| Unique `canonical_address_key` | 9,216 | same |
| Varnita addresses in population | **0** | доктрина satisfied (no_delivery / transit only) |

Territory breakdown (settlement):

| Territory | Addresses | Mode |
|---|---:|---|
| Бендеры | 4,866 | city (includes Липканы district = 248, city mode) |
| Парканы | 3,446 | external service territory |
| Протягайловка | 505 | external service territory |
| Гиска | 399 | external service territory |

City total = **4,866**; external total = **4,350**.

## 2. Route distance metric

| Item | Value | Source |
|---|---|---|
| Route metric field | **`expected_km`** | `docs/data/final-address-zone-points.geojson` (per `uid`) |
| Coverage | 9,216 / 9,216 | full |
| Reproduces released `zone_id` | **9,211 / 9,216 (99.95 %)** | binning `expected_km` by baseline edges |
| Route duration | **not available per address** | no per-address duration field exists — left blank, not invented |

`expected_km` is the production origin-weighted OSRM road distance (origin
46.82388, 29.48313). It is the only field that reproduces the released zones, so
it is the route metric for all models. `central_km` (88 %) and `bam_km` (28 %) are
alternative diagnostics and are **not** the zoning metric. The 5 non-reproducing
addresses sit within rounding distance of a threshold and are flagged, not forced.

Route distance distribution (km): min 0.403, median 4.642, p90 6.357, max 9.692.
Straight-line distance is **not** used as a route substitute anywhere.

## 3. Baseline (released K=4)

| Item | Value | Source |
|---|---|---|
| Interior thresholds | 2.424 / 4.076 / 5.577 km | `config/bands.yml` + `docs/data/final-zone-map-summary.json` |
| Outer bound of far zone | 9.692 km (= max routed km) | same |
| Decided K | 4 | `final-zone-map-summary.json` |
| Registry zone_id counts | 1:1659, 2:1902, 3:3413, 4:2242 | `address-registry.json` |

Baseline is reproduced for reference only; production thresholds are never changed.

### Baseline reproduction mismatches — audited exactly

The `<=` recompute reproduces 9,211 / 9,216; the strict `<` convention reproduces
**9,216 / 9,216**. The 5-address gap is fully explained: all five have an
`expected_km` sitting *exactly* on a released threshold (distance 0.000), and the
released dataset assigns the boundary value to the **upper** zone while the `<=`
recompute assigns it to the lower zone. Sole cause = **threshold inclusivity**;
zero unresolved. Full list: `data/interim/zone-baseline-reproduction-mismatches-v1.csv`
(n2337889957, w209267127, w284686410, w306081930, w352111747). Registry zone_id is
never modified.

### Manual-control coverage — honest limits

86 route controls + 90 Yandex measurements. Only **76** controls have a `uid` in
the 9,216 population (10 are Северный/Балка/Кавказ/Ленинский, outside it) and only
**28** are core-city. All controls lie in outer districts — none in the dense city
centre — so city models are validated on 28 real controls, not 90. This is a real
coverage limit, stated rather than hidden.

## 4. City / outside decomposition — NOT AVAILABLE

There is **no `in_city_km` / `outside_city_km` split** in any file
(`config/taxi-calibration.yml` is entirely `null`, `calibration_supplied: false`,
with an explicit guard against inventing tariffs). Consequences, honestly stated:

- **Route models K=4/5/6** — fully buildable on verified `expected_km` for all 9,216.
- **5E (effective_km), 5T-A/5T-B (taxi), HYBRID** — the city/outside split they
  require is only known for **pure-city addresses** (Бендеры/Липканы, where
  `outside_city_km = 0` by doctrine). For the 4,350 external addresses the split
  is `OUTSIDE_SPLIT_UNKNOWN`; no exact economic price is assigned. A lower/upper
  uncertainty **bracket** (whole route at 6 vs at 10 руб./км) is provided in the
  economics stage as a range only — never as a tariff or a basis for thresholds.
- Owner-provided taxi economics (min 18, city 6/km, outside 10/km, commissions
  5 руб. / 35 %) are **DERIVED ASSUMPTIONS**, applied for candidate analysis only
  and never written into `config/taxi-calibration.yml`.

## 5. Boundary anchors — NOT PROVEN

`config/boundary-candidates.yml` contains only administrative boundary relations
(OSM `9581354`, `944727`) marked `selection: none` (inspect-only). The
owner-described **пост ГАИ на ул. Котовского** is **not present** in any GIS/OSM
file. It is recorded as `UNKNOWN_REQUIRES_OWNER_MAP_CONFIRMATION` with **no
invented coordinates**. Гиска, Протягайловка and Северный likewise have no proven
single tariff boundary and stay `OWNER_BOUNDARY_DECISION_REQUIRED`.

## 6. Manual routing controls (validation only)

`docs/data/manual-yandex-route-controls.csv` = 86 controls;
`docs/data/manual-yandex-measurements.csv` = 90 observations. These are used only
to validate candidate models; they are never modified and no new manual audit is run.

## 7. What can be built honestly

| Model family | Status |
|---|---|
| MODEL 4R / 5R / 6R (route_km) | **FULL** — all 9,216, verified metric |
| Baseline K=4 reproduction | **FULL** |
| Boundary-anchor audit | **FULL** (result: unproven → owner decision) |
| MODEL 5E / 5T-A / 5T-B / HYBRID | **CITY-ONLY**; external = `OUTSIDE_SPLIT_UNKNOWN` + bracket |
| Route duration models | **BLOCKED** — no per-address duration; not invented |

Commit 1 delivers the FULL items. Commit 2 delivers the city-only economics with
external UNKNOWN + brackets, the full sensitivity grid, owner pack and dashboard.
