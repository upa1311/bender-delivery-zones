# Yandex routing — pilot (PREREQUISITES NOT MET)

**Read-only. No release, zone, Direct or price change. owner_review_required.**

## Verdict: the pilot cannot start yet

| prerequisite | state |
|---|---|
| `YANDEX_API_KEY` | **not set** |
| storage-permitting licence attested | **no** |
| may call the API | **NO** |

Blockers: YANDEX_API_KEY is not set; storage-permitting licence not attested (YANDEX_LICENSE_ALLOWS_STORAGE / config/yandex-license.json)

**No Yandex request was sent and no Yandex value was invented.** Per the
fail-closed rule I also did not fall back to OSRM as a substitute, and I have
stopped extending the in-house router.

## Required product

Yandex Maps API — Distance Matrix API, on a COMMERCIAL tariff whose terms explicitly permit storing/caching results (the free tier forbids storage). Confirm the exact SKU and the data-retention clause with Yandex before use.

Storing results matters here: the distances are persisted and used to derive
delivery zones, which the free/basic Yandex Maps API tariff does not allow. Only
you can confirm the contract, so the script refuses to run until you attest it.

## How to unblock

```
export YANDEX_API_KEY=…
export YANDEX_LICENSE_ALLOWS_STORAGE=true
export YANDEX_LICENSE_REF="<contract or tariff reference>"
uv run python scripts/yandex_distance_matrix.py
```
(or the same two licence fields in `config/yandex-license.json`)

## Volume and cost

| item | value |
|---|---|
| exact verified addresses | **9216** |
| origins | 1 (fixed central origin 46.82388, 29.48313) |
| destinations | 9216 |
| matrix elements / billing units | **9216** |
| max elements per synchronous request | 100 |
| full-run HTTP requests | **93** |
| pilot addresses | 107 |
| pilot HTTP requests | 2 |

## Pilot set (prepared, 107 addresses)

| district | addresses |
|---|---|
| Борисовка | 20 |
| Гиска | 20 |
| Парканы | 20 |
| Протягайловка | 20 |
| Северный | 7 |
| Хомутяновка | 20 |

The 7 Северный addresses are flagged `in_verified_registry=false` — they are
owner-review objects and are **not** part of the 9 216 verified registry, so the
pilot is 100 registry addresses + 7 Северный.

Every pilot row already carries its exact destination coordinates, current zone
and current OSRM km, so the Yandex columns fill in on the first authorised run.

## Request settings (fixed)

mode `driving` · coordinates `latitude,longitude` · one immutable central origin ·
traffic neutral/static (no `departure_time`) for stable zoning · `avoid_tolls=true` ·
ordinary poor/unpaved roads are **not** excluded pending a separate owner rule.
Only the official Distance Matrix API is used — the web map is never scraped.

## Fail-closed rules in force

- no fabricated values, ever;
- a Yandex error never silently becomes an OSRM value → `YANDEX_ERROR_OWNER_REVIEW`;
- unreachable → `UNREACHABLE_OWNER_REVIEW`, never an automatic Zone 4;
- Yandex vs OSRM divergence > 10 % → `ROUTER_DISAGREEMENT_OWNER_REVIEW`;
- release, zones, Direct and prices unchanged.

## After the pilot

Review the 107 results (geographic plausibility plus the four owner corridors:
Борисовка via the путепровод, Хомутяновка via Пивзавод, Хомутяновка via
Московская/Первомайская/Некрасова, Протягайловка via Старого/Мира). The remaining
**9 109** addresses are **not** requested without your explicit approval.
