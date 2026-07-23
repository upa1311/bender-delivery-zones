# Stage 06 — ordered OSRM tariff distance bands

- Generated (UTC): `2026-07-23T21:50:43Z`
- model: **ordered_cost_bands_over_osrm_road_km** (не пространственная кластеризация)
- routing: **OSRM MLD**, профиль `car.lua`
- recommendation_status: **owner_review_required** · suggested K: **4**
- prices assigned: **False**

## Demand units

- raw building objects: **23643**
- raw address objects: **11885**
- duplicates merged (address node on its building): **1241**
- unique serviceable delivery units: **23400** (из них адресных: 10611)
- Tier C units excluded (no_delivery): **18**
- outside service area: **119** · unreachable: **0** (см. delivery-exceptions.csv)

## K=4 ordered bands

- monotonic: **True** · split streets: 108 · weighted km dispersion: 0.5193

| Зона | км min/p50/p75/p90/max | мин p50/p90 | единиц | вес | центр км | БАМ км |
|---|---|---|---:|---:|---:|---:|
| Zone 1 | 0.361/1.679/2.305/2.569/2.973 | 2.532/3.632 | 4886 | 3794.0 | 1.464 | 4.091 |
| Zone 2 | 2.974/4.274/4.56/4.72/4.823 | 5.521/6.503 | 6801 | 4989.0 | 4.227 | 4.739 |
| Zone 3 | 4.824/5.469/5.819/6.057/6.276 | 6.911/8.02 | 7790 | 5584.25 | 5.446 | 5.829 |
| Zone 4 | 6.277/6.885/7.663/8.302/11.203 | 8.844/10.509 | 3923 | 2624.6 | 6.968 | 7.079 |

## K=5 ordered bands

- monotonic: **True** · split streets: 120 · weighted km dispersion: 0.4295

| Зона | км min/p50/p75/p90/max | мин p50/p90 | единиц | вес | центр км | БАМ км |
|---|---|---|---:|---:|---:|---:|
| Zone 1 | 0.361/1.658/2.263/2.537/2.824 | 2.514/3.565 | 4781 | 3705.0 | 1.444 | 4.071 |
| Zone 2 | 2.825/3.999/4.228/4.351/4.425 | 5.188/6.393 | 4382 | 3234.5 | 3.929 | 4.574 |
| Zone 3 | 4.426/4.969/5.255/5.448/5.576 | 6.33/7.343 | 6984 | 5053.35 | 4.945 | 5.428 |
| Zone 4 | 5.577/6.106/6.484/6.754/7.023 | 7.756/8.896 | 5546 | 3967.9 | 6.185 | 6.476 |
| Zone 5 | 7.024/7.783/8.274/8.708/11.203 | 9.741/10.991 | 1707 | 1031.1 | 7.867 | 8.184 |

## QA routes (OSRM)

| origin | target | км | мин |
|---|---|---:|---:|
| central_bender_origin | Parkany | 3.893 | 5.26 |
| central_bender_origin | Giska | 6.11 | 6.81 |
| central_bender_origin | Protyagailovka | 6.411 | 8.18 |
| central_bender_origin | Lipcani | 3.546 | 5.36 |
| bam_origin | Parkany | 4.591 | 6.51 |
| bam_origin | Giska | 8.724 | 9.56 |
| bam_origin | Protyagailovka | 4.705 | 6.79 |
| bam_origin | Lipcani | 1.242 | 2.13 |

- directionality probe: forward 0.723 км, reverse 1.523 км, asymmetric=**True**
- bridge crossing probe: 1.487 км, plausible=**True**

## Limitations

- Bands are cost ranges, not geographic clusters; a band polygon is only a drawing of which units fall in that price range.
- Tier C units are no_delivery and appear in no band or matrix.
- Travel times come from the OSRM car profile without live traffic.
- No money is assigned; taxi calibration fields remain null.
