# ADR-002 — OpenStreetMap via Geofabrik as the primary source

- Status: Accepted
- Date: 2026-07-23

## Context

We need road and address data for the Bender area to later assess delivery-zone
feasibility. Candidate sources include OpenStreetMap, commercial map providers
(Google, Yandex), and the official Moldova address register.

Constraints:

- Reproducibility: an audit must be repeatable from a recorded source.
- Licensing: any imported data must have clear, permissive-enough terms.
- Politeness: shared community APIs must not be bulk-scraped.

## Decision

Use **OpenStreetMap** data, obtained as the **Geofabrik Moldova country
extract** (`moldova-latest.osm.pbf`), as the primary source.

- OSM is ODbL 1.0 licensed — reuse is permitted with attribution and
  share-alike on derived databases.
- A dated country extract with a recorded SHA-256 makes runs reproducible.
- Geofabrik is a well-established redistributor with clear download terms.

**Not** chosen as import sources:

- Google Maps / Yandex Maps — terms prohibit bulk extraction/reuse.
- Public Nominatim / public Overpass — shared endpoints, unsuitable for bulk
  acquisition.

The Moldova official address register is retained as a **validation-only**
candidate with **unverified** bulk-access/reuse terms; it is not imported now.

## Consequences

- We depend on OSM completeness, which is **not** guaranteed; the audit reports
  raw coverage and never claims completeness.
- Attribution ("© OpenStreetMap contributors") is required on any produced work.
- Boundary geometry and metrics are computed from the extract; exact spatial
  clipping uses osmium-tool (no bounding-box approximation).
