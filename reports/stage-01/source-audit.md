# Bender OSM source audit — stage 01

- Generated at (UTC): `2026-07-23T07:26:48Z`
- Boundary selected: **False**

## Tool versions

- libosmium: `2.23.1`
- osmium_tool: `osmium version 1.19.1`
- pyosmium: `4.3.1`
- python: `3.12.10`

## Source PBF manifest

- content_length: `100293069`
- downloaded_at: `2026-07-23T07:22:59Z`
- etag: `"5fa59cd-6573d50c62a60"`
- last_modified: `Thu, 23 Jul 2026 01:38:40 GMT`
- local_path: `data/raw/moldova-latest.osm.pbf`
- resolved_url: `https://download.geofabrik.de/europe/moldova-260722.osm.pbf`
- sha256: `09ba0c058e89faacac7e1b1e7c8d0fbb14b4df66061b43abdce590b65ce8813c`
- source_url: `https://download.geofabrik.de/europe/moldova-latest.osm.pbf`

## Candidate boundaries

> Two candidates are inspected. Neither is selected. A human must review the tags and metrics below before any boundary is chosen.

### relation 9581354 — Municipiul Bender / MD-BD (official municipal boundary, per brief)

_Brief describes this as the official Municipiul Bender boundary. Verify tags against the PBF before trusting this description._

- found: **True**
- member count: 30
- member type counts: `{'w': 27, 'n': 1, 'r': 2}`
- tags:
  - `ISO3166-2` = `MD-BD`
  - `admin_level` = `4`
  - `alt_name` = `Municipiul Tighina`
  - `boundary` = `administrative`
  - `name` = `Municipiul Bender`
  - `name:de` = `Munizip Bender`
  - `name:en` = `Bender Municipality`
  - `name:es` = `Municipio de Bender`
  - `name:ro` = `Municipiul Bender`
  - `name:ru` = `Муниципий Бендеры`
  - `name:uk` = `Муніципій Бендер`
  - `note` = `This is the official border of Bender municipality in conformity with Republic of Moldova laws. Don't mess this relation with the Bender City Council border in conformity with PMR's laws ( https://www.openstreetmap.org/relation/944727)!`
  - `place` = `municipality`
  - `place:ro` = `municipiu`
  - `ref` = `BD`
  - `ref:cuatm:codstatistic` = `0500000`
  - `ref:cuatm:codunic` = `0500`
  - `ref:cuatm:statut` = `5`
  - `ref:nuts:1` = `MD1`
  - `ref:nuts:2` = `MD12`
  - `ref:nuts:3` = `MD121`
  - `type` = `boundary`
  - `wikidata` = `Q18088065`
  - `wikipedia` = `ro:municipiul Bender`
- spatial audit: **ok**

| metric | value |
| --- | ---: |
| address_nodes | 793 |
| address_objects_without_housenumber | 190 |
| buildings | 12356 |
| buildings_with_housenumber | 6026 |
| car_highway_ways | 1840 |
| duplicate_address_groups | 409 |
| duplicate_address_objects | 480 |
| highway_ways | 2762 |
| housenumber_without_street_or_place | 291 |
| named_highway_ways | 565 |
| objects_with_addr_place | 0 |
| objects_with_addr_street | 6744 |
| objects_with_alt_name | 21 |
| objects_with_name_ro | 1227 |
| objects_with_name_ru | 1652 |
| objects_with_old_name | 55 |
| unique_road_names | 272 |

### relation 944727 — Bender City Council (de-facto city boundary, per brief)

_Brief describes this as the de-facto Bender City Council boundary. Verify tags against the PBF before trusting this description._

- found: **True**
- member count: 33
- member type counts: `{'n': 1, 'w': 29, 'r': 3}`
- tags:
  - `admin_level` = `5`
  - `alt_name` = `Бендеры`
  - `alt_name:en` = `Bendery`
  - `boundary` = `administrative`
  - `name` = `Tighina`
  - `name:de` = `Tighina`
  - `name:en` = `Tighina`
  - `name:pl` = `Tighina`
  - `name:ro` = `Tighina`
  - `name:ru` = `Бендеры`
  - `name:uk` = `Бендери`
  - `note` = `This is the area of Bender, which is under control of the unrecognised PMR. This is the factually existing border.`
  - `old_name:ro` = `Bender`
  - `place` = `municipality`
  - `type` = `boundary`
  - `wikidata` = `Q192176`
  - `wikipedia` = `ro:Tighina`
- spatial audit: **ok**

| metric | value |
| --- | ---: |
| address_nodes | 1037 |
| address_objects_without_housenumber | 379 |
| buildings | 14919 |
| buildings_with_housenumber | 6466 |
| car_highway_ways | 2140 |
| duplicate_address_groups | 498 |
| duplicate_address_objects | 599 |
| highway_ways | 3239 |
| housenumber_without_street_or_place | 558 |
| named_highway_ways | 656 |
| objects_with_addr_place | 0 |
| objects_with_addr_street | 7343 |
| objects_with_alt_name | 22 |
| objects_with_name_ro | 1388 |
| objects_with_name_ru | 1847 |
| objects_with_old_name | 61 |
| unique_road_names | 288 |

## Differences between boundaries

| metric | 944727 | 9581354 | delta |
| --- | ---: | ---: | ---: |
| address_nodes | 1037 | 793 | 244 |
| address_objects_without_housenumber | 379 | 190 | 189 |
| buildings | 14919 | 12356 | 2563 |
| buildings_with_housenumber | 6466 | 6026 | 440 |
| car_highway_ways | 2140 | 1840 | 300 |
| duplicate_address_groups | 498 | 409 | 89 |
| duplicate_address_objects | 599 | 480 | 119 |
| highway_ways | 3239 | 2762 | 477 |
| housenumber_without_street_or_place | 558 | 291 | 267 |
| named_highway_ways | 656 | 565 | 91 |
| objects_with_addr_place | 0 | 0 | 0 |
| objects_with_addr_street | 7343 | 6744 | 599 |
| objects_with_alt_name | 22 | 21 | 1 |
| objects_with_name_ro | 1388 | 1227 | 161 |
| objects_with_name_ru | 1847 | 1652 | 195 |
| objects_with_old_name | 61 | 55 | 6 |
| unique_road_names | 288 | 272 | 16 |

## Limitations

- Address coverage in OpenStreetMap is community-contributed and is NOT complete.
- No working boundary has been selected; both candidates are reported side by side.
- Duplicate metric is a preliminary signal only (NFKC/trim/collapse/casefold); no transliteration or fuzzy matching is applied.
- Metrics are counts of raw OSM objects, not validated postal addresses.
- This stage produces no delivery zones, tariffs, routing graph, or address database.

