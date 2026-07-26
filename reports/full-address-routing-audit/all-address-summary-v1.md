# Full address routing audit v1

Canonical registry: `releases/bender-zones-v1.1/address-registry.json` (normalized SHA-256 `bc66ad113a6ba5706bb6d2797ddc543e5b576482051d0d981551f014561c1817`); coordinate join: `docs/data/delivery-units.csv` (normalized SHA-256 `7f52e5119db0bfeb8a68464ad79ed1288a070c3563d887c088f72283c85c4250`).

Grain: one immutable v1.1 delivery address (`address_id = uid`). The audit uses
fresh local OSRM routes from `http://127.0.0.1:5000` and never calls Yandex.

## Source reconciliation

| stage | objects |
|---|---:|
| full catalog before eligibility/exclusions | 23,229 |
| eligible verified rows before canonical dedupe | 9,777 |
| canonical duplicate rows removed | 561 |
| immutable working registry after dedupe | 9,216 |
| admin QA objects outside the working registry | 14,013 |

## Routing summary

| metric | value |
|---|---:|
| addresses | 9216 |
| routable | 9216 |
| unreachable | 0 |
| router errors | 0 |
| invalid coordinates | 0 |
| median / mean / p90 distance | 4.592 / 4.265 / 6.420 km |
| median / p90 destination snap | 16.5 / 26.9 m |
| snap >30 / >60 / >100 m | 556 / 27 / 4 |
| continuity outliers | 637 |
| robust high detour factors | 68 |
| known discrepancy rows / matched canonical addresses | 57 / 50 |
| unique corridor signatures | 243 |
| unique terminal branch signatures | 581 |
| provisional-boundary review addresses | 1439 |

## Manual-control coverage

| STRONG | PARTIAL | WEAK | UNCOVERED |
|---:|---:|---:|---:|
| 2056 | 726 | 4392 | 2042 |

The 86 controls are not treated as sufficient merely because they share a
district. Strong coverage requires a matching corridor plus terminal evidence
and street/branch proximity.

## Additional manual review

- minimum representative set: **970** routes;
- expanded confidence set: **2148** routes;
- candidate CSV rows: **2148**.

## Decision

**GO_WITH_REVIEW** for zone recalculation analysis. This does not authorize a zone
release. Zones, thresholds and assignments were not changed.
