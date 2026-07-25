# Stage 11 — Google Routes as the primary routing oracle

**Read-only. No zone, release, Direct or price change. owner_review_required.**

## Status: `NOT_RUN_GOOGLE_API_KEY_MISSING`

`GOOGLE_MAPS_API_KEY` is **not configured in this environment**, so no Google call
was made and **no Google distance, duration or verdict is fabricated**. The
integration is complete and run-ready: export the key and re-run
`scripts/stage11_google_routes.py`.

## Roles

| role | engine |
|---|---|
| **PRIMARY oracle** | Google Routes API v2 `computeRoutes` |
| QA + fallback | local OSRM (full Moldova PBF) and the Stage 10D edge-valid graph |

## Request contract (exactly what will be sent)

- `travelMode: DRIVE`
- **zone computation** → `routingPreference: TRAFFIC_UNAWARE`
- **live order** → `routingPreference: TRAFFIC_AWARE_OPTIMAL`
- `requestedReferenceRoutes: ["SHORTER_DISTANCE"]` (so DEFAULT_ROUTE and
  SHORTER_DISTANCE are both returned)
- exact `latLng` per verified address — never an address string
- field mask: `routes.distanceMeters,routes.duration,routes.staticDuration,routes.polyline.encodedPolyline,routes.routeLabels,routes.warnings,routes.description,fallbackInfo`

Recorded per address: `distanceMeters`, `duration`, `staticDuration`, encoded
polyline (cache only), `routeLabels`, `warnings`, `fallbackInfo`.

## Control routes (OSRM baseline captured; Google pending)

| slot | address | OSRM m | Google m | status |
|---|---|---|---|---|
| Борисовка | улица Богдана Хмельницкого 1 | 6442.1 | — | PENDING_GOOGLE |
| Хомутяновка | улица Интернационалистов 5 | 7253.1 | — | PENDING_GOOGLE |
| Протягайловка | Садовая улица 18 | 8549.5 | — | PENDING_GOOGLE |
| Гиска | улица Кирова 40 | 4515.7 | — | PENDING_GOOGLE |
| Северный | Strada Dimitrie Cantemir 11 | 7640.5 | — | PENDING_GOOGLE |
| Парканы:начало | улица Ленина 1 | 3166.3 | — | PENDING_GOOGLE |
| Парканы:середина | улица Петра Николаева 39 | 5182.2 | — | PENDING_GOOGLE |
| Парканы:конец | улица Свердлова 98 | 7574.8 | — | PENDING_GOOGLE |

## Disagreement rule

`>10.0% distance -> ROUTER_DISAGREEMENT_OWNER_REVIEW`. Until Google answers, every row is `PENDING_GOOGLE` —
never silently counted as agreement.

## Google Maps Platform terms

Google polylines are written **only** to the git-ignored
`data/interim/google-cache/`. They are never placed in `docs/` (the public map) or
in a release. `assert_no_google_polyline_in_public()` enforces this and is covered
by a test; current leaks: **0**.
Any future use of Google geometry on a non-Google map requires a separate terms
review.

## Next

1. `export GOOGLE_MAPS_API_KEY=…`
2. re-run the script — control routes first, then all verified addresses
3. review `ROUTER_DISAGREEMENT_OWNER_REVIEW` rows (Google vs OSRM, rail side,
   district entry, Google shorter-distance vs default, Google vs owner corridors)
4. only after that consider any zone change — **zones are unchanged here**
