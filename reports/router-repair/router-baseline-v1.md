# Router evaluation — baseline v1

Fresh routes from the local OSRM MLD server were compared with the completed
manual Yandex fastest-route measurements. No Yandex request is made here.

## Execution evidence

- OSRM endpoint: `http://127.0.0.1:5000`;
- fixed origin (lon, lat): `29.48313, 46.82388`;
- request mode: driving, full GeoJSON overview, steps, and OSM node annotations;
- destinations: the exact coordinates in the 86 immutable route controls;
- limitation: the OSRM HTTP response exposes no build identifier, so the checked-in
  profile/build manifests and captured route node sequences are the reproducibility
  evidence. A graph change still requires an independently identified OSM defect.

## Summary

| metric | value |
|---|---:|
| controls | 86 |
| routable | 86 |
| unreachable | 0 |
| median divergence | 3.2% |
| mean divergence | 5.9% |
| p90 divergence | 12.6% |
| divergence >5% | 25 |
| divergence >10% | 10 |
| divergence >20% | 7 |
| suspicious destination snap >60 m | 1 |

## By district

| district | routes | median | mean | >10% |
|---|---:|---:|---:|---:|
| Балка | 2 | 7.4% | 7.4% | 0 |
| Борисовка | 4 | 5.4% | 12.2% | 1 |
| Гиска | 16 | 2.9% | 7.7% | 4 |
| Кавказ | 1 | 5.0% | 5.0% | 0 |
| Ленинский | 1 | 3.7% | 3.7% | 0 |
| Парканы | 14 | 2.7% | 3.2% | 0 |
| Протягайловка | 19 | 2.9% | 4.3% | 1 |
| Северный | 7 | 1.9% | 1.6% | 0 |
| Хомутяновка | 22 | 4.5% | 7.8% | 4 |

## Controls requiring attention

| control | district | Yandex km | router km | divergence | status | probable cause |
|---|---|---:|---:|---:|---|---|
| MY-002 | Борисовка | 4.8280 | 6.5654 | 36.0% | DIVERGENCE_GT20 | ADDRESS_ANCHOR_AMBIGUOUS |
| MY-003 | Борисовка | 6.7592 | 7.2683 | 7.5% | DIVERGENCE_GT5 | TERRITORY_OR_BOUNDARY_AMBIGUOUS |
| MY-005 | Гиска | 4.0716 | 4.6932 | 15.3% | DIVERGENCE_GT10 | ROUTER_CHOOSES_DIFFERENT_VALID_ROUTE |
| MY-018 | Гиска | 5.1499 | 3.6598 | 28.9% | DIVERGENCE_GT20 | ADDRESS_ANCHOR_AMBIGUOUS |
| MY-019 | Гиска | 4.9890 | 3.7429 | 25.0% | DIVERGENCE_GT20 | ADDRESS_ANCHOR_AMBIGUOUS |
| MY-020 | Гиска | 4.9890 | 3.7540 | 24.8% | DIVERGENCE_GT20 | ADDRESS_ANCHOR_AMBIGUOUS |
| MY-021 | Парканы | 5.9546 | 5.5410 | 6.9% | DIVERGENCE_GT5 | ADDRESS_ANCHOR_AMBIGUOUS |
| MY-035 | Протягайловка | 6.9202 | 6.4655 | 6.6% | DIVERGENCE_GT5 | YANDEX_VENDOR_DIFFERENCE |
| MY-044 | Протягайловка | 6.4374 | 5.8636 | 8.9% | DIVERGENCE_GT5 | YANDEX_VENDOR_DIFFERENCE |
| MY-046 | Протягайловка | 4.9890 | 4.7357 | 5.1% | DIVERGENCE_GT5 | ADDRESS_ANCHOR_AMBIGUOUS |
| MY-047 | Протягайловка | 7.2420 | 6.5454 | 9.6% | DIVERGENCE_GT5 | YANDEX_VENDOR_DIFFERENCE |
| MY-048 | Протягайловка | 6.5983 | 6.2632 | 5.1% | DIVERGENCE_GT5 | YANDEX_VENDOR_DIFFERENCE |
| MY-054 | Протягайловка | 5.6327 | 6.4612 | 14.7% | DIVERGENCE_GT10 | ADDRESS_ANCHOR_AMBIGUOUS |
| MY-063 | Хомутяновка | 5.7936 | 7.4577 | 28.7% | DIVERGENCE_GT20 | ROUTER_CHOOSES_DIFFERENT_VALID_ROUTE |
| MY-065 | Хомутяновка | 1.4645 | 1.3123 | 10.4% | DIVERGENCE_GT10 | ROUTER_CHOOSES_DIFFERENT_VALID_ROUTE |
| MY-067 | Балка | 2.4301 | 2.2936 | 5.6% | DIVERGENCE_GT5 | YANDEX_VENDOR_DIFFERENCE |
| MY-071 | Хомутяновка | 2.6232 | 2.4511 | 6.6% | SUSPICIOUS_SNAP | ADDRESS_ANCHOR_AMBIGUOUS |
| MY-072 | Хомутяновка | 1.3036 | 1.2239 | 6.1% | DIVERGENCE_GT5 | YANDEX_VENDOR_DIFFERENCE |
| MY-073 | Хомутяновка | 1.6898 | 1.2567 | 25.6% | DIVERGENCE_GT20 | ROUTER_CHOOSES_DIFFERENT_VALID_ROUTE |
| MY-074 | Хомутяновка | 1.6737 | 1.5070 | 10.0% | DIVERGENCE_GT5 | YANDEX_VENDOR_DIFFERENCE |
| MY-075 | Хомутяновка | 3.9107 | 3.0020 | 23.2% | DIVERGENCE_GT20 | ROUTER_CHOOSES_DIFFERENT_VALID_ROUTE |
| MY-077 | Хомутяновка | 6.7592 | 7.2531 | 7.3% | DIVERGENCE_GT5 | YANDEX_VENDOR_DIFFERENCE |
| MY-078 | Хомутяновка | 6.7592 | 7.3109 | 8.2% | DIVERGENCE_GT5 | YANDEX_VENDOR_DIFFERENCE |
| MY-082 | Балка | 2.7681 | 2.5124 | 9.2% | DIVERGENCE_GT5 | ADDRESS_ANCHOR_AMBIGUOUS |
| MY-085 | Хомутяновка | 5.3108 | 4.7868 | 9.9% | DIVERGENCE_GT5 | ADDRESS_ANCHOR_AMBIGUOUS |

The probable-cause field is triage, not proof of a graph defect. Graph changes
require concrete OSM node/edge evidence and a regression-safe before/after test.

Golden measurements normalized SHA-256: `58a71e47ac546f2788af0fc977709db169baea792bb866184e8ca926e177571c`.
