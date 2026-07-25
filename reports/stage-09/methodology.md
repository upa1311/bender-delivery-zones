# Stage 09 — city-exit route weighting audit (methodology)

**Status: provisional audit. No immutable release was changed, no new release was
published, no price/fee/payout was added, and Direct was not touched. Every
result below is `owner_review_required`.**

## Why re-audit

The published Zone 1–4 (release `bender-zones-v1.1`) rank each home by
**origin-weighted OSRM road kilometres** only. The local taxi model, however,
charges more per kilometre once a car leaves Bender:

- in-city: ≈ 6 rub/km (owner's words);
- after leaving Bender toward Parkany / Giska: ≈ 10 rub/km (owner's words);
- the exact switch point is **unknown** and pending owner confirmation.

Because raw kilometres ignore this, some assignments look wrong on the map: the
start of Parkany can land in Zone 2, Khomutyanovka in Zone 3, and specific
Borisovka streets inside Bender in Zone 4.

## The metric — fastest **valid** route first

Per the owner clarification, a home's zone comes only from the **fastest valid
driving route** (minimum realistic travel duration) found over the whole
connected car graph — never straight-line distance, the nearest road, a random
alternative, a fixed district entry, or a street's "primary zone".

We use the local OSRM MLD car profile (`v26.7.3`, same Moldova PBF as the
release). OSRM's shortest-path search returns the global minimum-duration route
while already respecting one-ways, turn restrictions, access tags and barriers,
so its default route **is** the fastest valid route under the car profile. We
additionally request `alternatives=true` and keep the shortest-distance variant
for QA comparison, but the fastest route is the shortest-path result, not "one of
the alternatives".

For each home and **each** origin (central 0.85, BAM 0.10, outer 0.05) we take
the fastest route **separately**, then apply origin weights — routes are never
averaged before optimisation.

## Provisional generalized cost

For the chosen fastest valid route we split the geometry against the **real
Bender OSM admin boundary** (`source-boundaries.geojson`, `key=bender`,
osm_id 12463379) into in-city and outside-city kilometres, then:

```
equivalent_city_km = in_city_km + outside_city_km * (10 / 6)
outside_multiplier = 1.6666667
```

`equivalent_city_km` is **only a temporary relative difficulty coefficient** for
comparing zones. It is **not** money and **not** a Direct tariff. Provenance
(`docs/data/stage-09-recompute-summary.json`): city rate 6, outside rate 10,
switch point unknown, Bender OSM boundary used as a provisional proxy,
`owner_review_required=true`.

## Districts

Homes are labelled by the **nearest real OSM `place=suburb/neighbourhood`** node
(Борисовка, Хомутяновка, Птичник, Ленинский, Шёлковый, Солнечный/БАМ, Липканы,
Центр, Балка, Кавказ, Нижний Днестр). No boundary is invented. Северный has no
OSM place object (named only by marshrutka route relations) and stays
`owner_review`; Липканы/Северный keep the catalog's authoritative labels.

## K=4 recompute

Zones stay K=4. Edges are recomputed with the **same optimizer and config as the
release** (`bender_zones.bands.optimal_bands`, `config/bands.yml`:
bin_width 0.05 km, min/max weight share 0.12/0.40) fed `equivalent_city_km`
instead of raw km, under two origin weightings:

- **A** — 85 % central / 15 % BAM (the current basis);
- **B** — the actual restaurant distribution 85 / 10 / 5.

The audit recompute uses a uniform per-address weight (demand proxy) and is
**not** declared final — it is a comparison for owner review.

## Switch-point sensitivity

The switch point is unknown, so three scenarios are tested
(`stage-09-sensitivity.json`): switch at the boundary (A), 300 m before (B),
300 m after (C). A home is **stable** only if its zone is identical in all three;
unstable homes go to owner review.

## Outputs

- `docs/data/stage-09-current-vs-generalized.csv` / `.geojson`
- `docs/data/stage-09-sensitivity.json`
- `docs/data/stage-09-recompute-summary.json`
- `reports/stage-09/{borisovka,khomutyanovka,parkany-entry,giska-entry}-audit.csv`
- `docs/stage-09-audit-map.html` (current / generalized A / B / changed /
  unstable / boundary / control routes)
