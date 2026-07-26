# Yandex address validation sample v1

Status: **PARTIAL — sample prepared; 17 canonical rows reviewed; browser review incomplete**

## Population and grain

The source is `releases/bender-zones-v1.1/address-registry.json`, release 1.1.0,
dataset `moldova-pbf:09ba0c058e89`. Its normalized SHA-256 is
`bc66ad113a6ba5706bb6d2797ddc543e5b576482051d0d981551f014561c1817`.
It contains 9,216 rows, 9,216 unique IDs, and 9,216 unique canonical keys after
deduplication. The full source catalog has 23,229 rows: 9,777 rows met export
eligibility before deduplication, 561 eligible duplicates were removed, and 14,013
source objects are outside the final registry as administrative QA/non-export rows.
The audit grain is territory + normalized street + normalized house number;
apartments, entrances, organizations, and POIs inside the same building are not
separate addresses.

Coordinates and retained object type are joined by immutable ID from
`docs/data/delivery-units.csv`. Every registry ID has coordinates. Population counts:

| Territory | DELIVERABLE | UNKNOWN | Total |
|---|---:|---:|---:|
| Бендеры | 4,789 | 77 | 4,866 |
| Парканы | 3,440 | 6 | 3,446 |
| Гиска | 376 | 23 | 399 |
| Протягайловка | 473 | 32 | 505 |
| Total | 9,078 | 138 | 9,216 |

`NON_DELIVERABLE_STRUCTURE` is zero because detailed building tags are unavailable,
not because zero has been proven visually.

The classification schema also carries `facility_category`, `facility_name`,
`public_or_commercial_destination`, `independent_delivery_entrance`,
`shared_address_with_other_pois`, and `deliverable_reason`. A complete address for a
hospital, school, factory, warehouse, shop, office, government building, or other real
destination is classified as `DELIVERABLE`; non-residential type alone is never an
exclusion. A named destination without a house number remains
`UNKNOWN_REQUIRES_REVIEW` until its address or independent delivery entrance is
confirmed.

## Deterministic selection

`scripts/build_yandex_address_inventory_sample.py` produces 2,565 rows with fixed
seed `20260726`. Selection is by the 316 territory/district/street groups and includes:

- all 138 UNKNOWN rows;
- all 138 addresses on the 44 street groups having at most five addresses;
- geographic start, 25%, middle, 75%, end, and the highest routing-anomaly score on
  every longer street;
- 500 lettered, 65 fractional, and 441 high-tail house-number selections (overlap is
  retained once per address);
- 31 rows with snap distance at least 40 m;
- geographic extremes for each territory;
- all 57 known discrepancy IDs, using an explicitly labelled nearest canonical proxy
  when the control UID is outside the 9,216-row population;
- addresses within approximately 0.003 degrees of the protected Varnita no-delivery
  geometry and addresses carrying an existing Varnita-transit flag.

Each row receives the stratum population/sample ratio as a positive sampling weight.
The sample is intentionally larger than 1,000 because mandatory rules overlap but
must not be discarded. IDs and ordering are stable across rebuilds.

Because much of this sample is selected with certainty by mandatory rules, the raw
population/sample ratio is a transparent calibration weight, not a claim of a pure
simple-random design. It must not be used for a final population estimate until the
sample is fully reviewed and the mandatory/random components are analysed separately.

## Coverage limitations

The 9,216-row release has four territories: Бендеры, Парканы, Гиска, and
Протягайловка. Северный is excluded upstream from this canonical population, so it
cannot honestly be sampled without changing the requested population. District
metadata is mostly absent (8,968 rows empty; 248 Липканы), and detailed private,
multifamily, commercial, and industrial building classes were not retained. Unique
terminal-branch membership is also unavailable on the requested base commit.

These missing strata are disclosed rather than inferred. The source registry,
coordinates, exclusions, and territory assignments remain unchanged.

There is also an upstream coverage defect: `docs/data/delivery-exceptions.csv` contains
36 address nodes rejected as `address_inside_nonresidential_building`—34 generically
non-residential, one outbuilding, and one abandoned/ruin. All 36 source records were
recovered from the exact pinned Geofabrik file `moldova-260722.osm.pbf`, whose SHA-256
is `09ba0c058e89faacac7e1b1e7c8d0fbb14b4df66061b43abdce590b65ce8813c`.
Recovery produced 15 potential additional deliverable address candidates, 20 duplicate
address grains, and one lifecycle non-deliverable object. These records remain a
separate audit population and are not added to the protected 9,216-row release.

## Population separation

The forward file now contains 17 `CANONICAL_9216` observations and 36
`RECOVERED_EXCLUSION_CANDIDATE` observations. Only the canonical observations receive
sampling weights or contribute to the weighted canonical match rate. The 36 recovered
records are a complete review of a known exclusion set, not a probability sample.

The original YAV-0001 through YAV-0003 evidence is protected by the normalized
fingerprint `a184e12c61488120f559419c3a66296d7ed0e40ed4f0392e6c7e008aa94f6380`.
