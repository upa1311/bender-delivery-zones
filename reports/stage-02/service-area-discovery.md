# Stage 02 — service-area discovery (data QA)

- Generated (UTC): `2026-07-23T07:55:21Z`
- Zones created: **False** · boundary_selected: **False**
- Source PBF SHA-256: `09ba0c058e89faacac7e1b1e7c8d0fbb14b4df66061b43abdce590b65ce8813c`

> Это карта проверки данных. Финальные зоны доставки ещё не созданы.

## Allowed territories & discovered OSM objects

### Бендеры (`bender`)
- OSM object: **relation 12463379** · found: True
- Boundary status: **boundary_found**
- Members: 21 `{'w': 20, 'n': 1}`
- Streets: 248 unique · 247 with name:ru · 1 need RU review
- Buildings: 10336 · address objects: 6186
- Key tags: `name=Bender`, `name:ru=Бендеры`, `name:ro=Bender`, `admin_level=8`, `boundary=administrative`

### Протягайловка (`protyagailovka`)
- OSM object: **relation 12463378** · found: True
- Boundary status: **boundary_found**
- Members: 10 `{'n': 1, 'w': 9}`
- Streets: 41 unique · 36 with name:ru · 5 need RU review
- Buildings: 2036 · address objects: 720
- Key tags: `name=Протягайловка`, `name:ru=Протягайловка`, `name:ro=Proteagailovca`, `admin_level=8`, `boundary=administrative`

### Гиска (`giska`)
- OSM object: **relation 12215667** · found: True
- Boundary status: **boundary_found**
- Members: 14 `{'w': 13, 'n': 1}`
- Streets: 32 unique · 31 with name:ru · 1 need RU review
- Buildings: 2419 · address objects: 630
- Key tags: `name=Gîsca`, `name:ru=Гиска`, `name:ro=Gîsca`, `admin_level=8`, `boundary=administrative`

### Парканы (`parkany`)
- OSM object: **relation 7431263** · found: True
- Boundary status: **boundary_found**
- Members: 17 `{'n': 1, 'w': 16}`
- Streets: 47 unique · 47 with name:ru · 0 need RU review
- Buildings: 8858 · address objects: 4514
- Key tags: `name=Парканский сельский совет`, `name:ru=Парканский сельский совет`, `name:ro=Sovetul sătesc Parcani`, `admin_level=8`, `boundary=administrative`

## Boundary status summary

- Found: ['bender', 'protyagailovka', 'giska', 'parkany']
- Need manual decision (boundary_missing): — none

## Excluded

- **varnita** — Excluded from the delivery service area by owner decision.

## Warnings

- none

## Limitations

- This is a data-QA map. No delivery zones, tariffs, routing graph, or production polygon are created.
- Territories are shown as separate real OSM boundaries; they are NOT merged into a final service polygon at this stage.
- Varnița is intentionally excluded from the service area.
- Street Russian names are resolved by strict priority; unconfirmed ones are flagged needs_ru_review and never transliterated.
- Address coverage in OpenStreetMap is community-contributed and NOT complete.
