# Stage 10 — ROAD_TRUTH (from available evidence)

> **CORRECTED by Stage 10B.** The counts below used `alternatives=3` as the
> "shortest route", which is NOT a shortest path. Against a TRUE distance-optimal
> Dijkstra over the same car graph the real counts are: Борисовка **308/511**,
> Хомутяновка **94/999** (not 5), Протягайловка **191/513** (not 13), Парканы
> **45/90**, Гиска 0/90. In particular the "Хомутяновка is route-correct"
> conclusion does NOT hold. See `reports/stage-10b/corridor-routing-truth.md`.

**Read-only. No OSM edit, no release, no Direct, no price, no new zone.
owner_review_required.** Verdicts use OSRM (full Moldova PBF) + local OSM topology
+ owner-confirmed public-transport corridors. Cross-engine and imagery verdicts
that need GraphHopper/Valhalla/openrouteservice/Mapillary/KartaView/Yandex/Google
are marked `INSUFFICIENT_EVIDENCE` (pending) and are NOT fabricated.

## Owner-confirmed corridors (`docs/data/stage10-road-truth.csv`)

| corridor | verdict | cross-engine |
|---|---|---|
| Borisovka north (Кишинёв–Тирасполь путепровод) | PUBLIC_TRANSPORT_CORRIDOR_CONFIRMED | INSUFFICIENT_EVIDENCE (pending) |
| Khomutyanovka A (пл.Героев→Пивзавод→Ечина) | PUBLIC_TRANSPORT_CORRIDOR_CONFIRMED | pending |
| Khomutyanovka B (Московская→…→Ечина) | PUBLIC_TRANSPORT_CORRIDOR_CONFIRMED | pending |
| Protyagailovka (Старого→Мира→…) | PUBLIC_TRANSPORT_CORRIDOR_CONFIRMED | pending |

Each corridor is present in the full-PBF OSRM graph and traversable both
directions (three are oneway-asymmetric). None is `OSM_DATA_MISSING` or
`OSM_CONNECTIVITY_BROKEN`.

## What the owner asked to see first

- **Map of all real entries** — `docs/stage10-road-truth-map.html` +
  `docs/data/stage10-entries.geojson` (**218** connected car entries across
  Борисовка/Хомутяновка/Протягайловка/Парканы/Гиска, plus the rail level
  crossings and the four corridors).
- **Engine disagreements** — `docs/data/stage10-engine-disagreements.csv`:
  **PENDING_MULTI_ENGINE** — only OSRM is live; no disagreement is fabricated.
- **Suspect OSM ways/nodes** — `docs/data/stage10-suspect-osm-ways.csv`: **71**
  (Stage 09A wrong-snap / wrong-access + Stage 09B BROKEN_CONNECTIVITY /
  GEOMETRY_ONLY / UNKNOWN crossings) — real, for owner review.
- **Addresses with an overstated current route** —
  `docs/data/stage10-overstated-addresses.csv`: **Борисовка 166** (north
  путепровод shortcut), **Хомутяновка 5**, **Протягайловка 13**.

## Verdict

The corridors are **confirmed by the available sources**. A full CONFIRMED_BY_ALL
/ ROUTER_DISAGREEMENT / IMAGERY_CONFIRMED verdict requires the additional engines
and external sources the owner must provision (see `source-status.md`). No zone,
release, Direct change or price is produced.
