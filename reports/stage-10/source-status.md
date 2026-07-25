# Stage 10 — multi-source road-truth: source status (honest)

**Read-only. No OSM edit, no immutable release, no Direct, no price, no new zone.
No source is fabricated.** `docs/data/stage10-source-status.json`.

| source | kind | status | prerequisite / reason |
|---|---|---|---|
| **OSRM** | local router | **LIVE** | osrm-routed on the **FULL Moldova PBF** (96 MB, not a city extract) |
| GraphHopper | local router | unavailable | needs a JVM (no Java here) + graph on full PBF |
| Valhalla | local router | unavailable | needs Docker/build (none here) + tiles on full PBF |
| openrouteservice | local router | unavailable | needs Java/Docker (none here) + graph on full PBF |
| Yandex Maps | external QA | unavailable | needs `YANDEX_API_KEY` |
| Google Routes | external QA | unavailable | needs `GOOGLE_MAPS_API_KEY` (QA only, never copied into product) |
| Mapillary | imagery | unavailable | needs `MAPILLARY_TOKEN` |
| KartaView | imagery | unavailable | needs KartaView access |
| EasyWay | public transport | unavailable | web bot-blocked (HTTP 403) — verified vs OSM instead |

## Key point for the owner

- The anti-truncation requirement is **met**: the OSRM graph is built on the full
  `data/raw/moldova-latest.osm.pbf` (96 MB), not the small Bender extract
  (`osrm_on_full_moldova_pbf = true`).
- The other three local engines and the four external sources need infrastructure
  (a JVM, Docker) or API keys that are **not present in this environment**. They
  are wired into the framework as pluggable sources and will run once the owner
  provides them; until then their verdicts are `INSUFFICIENT_EVIDENCE`, **not
  invented**.

## To enable the full multi-source comparison

1. Install a JVM and run GraphHopper + openrouteservice, and/or Docker + Valhalla,
   each with its graph built on `data/raw/moldova-latest.osm.pbf`.
2. Export `YANDEX_API_KEY`, `GOOGLE_MAPS_API_KEY`, `MAPILLARY_TOKEN` (+ KartaView).
3. Re-run `scripts/stage10_road_truth.py` — the harness will then compute
   cross-engine agreement (CONFIRMED_BY_ALL / ROUTER_DISAGREEMENT) and imagery
   confirmation automatically.
