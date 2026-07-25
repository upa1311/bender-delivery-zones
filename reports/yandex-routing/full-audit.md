# Yandex routing — full audit (NOT STARTED)

**Read-only. No release, zone, Direct or price change. owner_review_required.**

Status: **NOT STARTED — blocked on prerequisites and on pilot approval.**

Two gates must clear first:

1. `YANDEX_API_KEY` + an attested storage-permitting licence (see `pilot.md`);
2. your explicit approval of the 107-address pilot.

Planned full run: **9216 matrix elements** =
**93 HTTP requests** (1 origin ×
≤ 100 destinations), writing
`docs/data/yandex-full-distance-matrix.csv` and refreshing
`docs/data/yandex-vs-osrm.csv`.

No number in this file will be produced by anything other than the official
Yandex Distance Matrix API. Zones stay unchanged until the audit completes and
you approve the result.
