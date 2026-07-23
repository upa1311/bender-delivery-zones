# Data sources

## Primary: Geofabrik Moldova extract (OpenStreetMap)

- Landing page: <https://download.geofabrik.de/europe/moldova.html>
- Download: <https://download.geofabrik.de/europe/moldova-latest.osm.pbf>
- Format: OSM PBF
- License: ODbL 1.0, © OpenStreetMap contributors
- Acquisition: `scripts/download_osm.py` (honest User-Agent, timeout, limited
  retries, SHA-256, provenance manifest). Never committed to git.

Why a country extract and not a live API: reproducibility. A single dated PBF
with a recorded SHA-256 lets any audit run be reproduced exactly, and avoids
hammering shared community API endpoints. See
[ADR-002](decisions/ADR-002-osm-geofabrik-primary-source.md).

## Candidate boundaries (inspect only)

Defined in [`config/boundary-candidates.yml`](../config/boundary-candidates.yml):

- relation `9581354` — described as official Municipiul Bender / MD-BD.
- relation `944727` — described as de-facto Bender City Council.

The audit reports each relation's real tags and metrics. It selects neither.

## Validation-only (not imported here)

- **Moldova official address register** — potential validation source; bulk
  access / reuse terms **unverified**; not imported in this stage.

## Explicitly excluded as import sources

- Google Maps, Yandex Maps — terms prohibit bulk reuse.
- Public Nominatim, public Overpass — shared endpoints; no bulk acquisition.

## Tooling versions

Captured per audit run in `reports/stage-01/source-audit.json`:
Python, pyosmium, libosmium, and (if present) osmium-tool.
