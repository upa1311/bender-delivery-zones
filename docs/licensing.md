# Licensing

## Software

The code in this repository is under the MIT License ([LICENSE](../LICENSE)).

## OpenStreetMap data — ODbL 1.0

All OSM-derived data is governed by the **Open Database License (ODbL) v1.0**:
<https://opendatacommons.org/licenses/odbl/1-0/>.

Consequences we must honour:

- **Attribution** is mandatory: "© OpenStreetMap contributors" must accompany
  any produced map, extract, or derived database.
- **Share-Alike**: a *Derivative Database* must be offered under ODbL. Produced
  Works (e.g. a rendered map or a computed metric table) require attribution but
  are not themselves forced under ODbL; a derived *database* is.
- We keep the raw PBF out of git and record provenance (URL, timestamp,
  SHA-256, ETag, Last-Modified) in a manifest so the exact source is auditable.

## Extract provider — Geofabrik

The primary extract is distributed by **Geofabrik GmbH**
(<https://download.geofabrik.de/europe/moldova.html>). Geofabrik redistributes
OpenStreetMap data; the governing license remains ODbL and attribution remains
to OpenStreetMap contributors. Geofabrik's own download-server terms of use
apply to how we fetch the file (reasonable request rate, honest User-Agent).

## Explicitly NOT import sources

- **Google Maps** and **Yandex Maps**: their terms prohibit bulk extraction and
  reuse of their map/geocoding data. They are **not** import sources for this
  project. They may only ever be used, if at all, for manual, on-screen human
  cross-checking — never bulk-scraped, never imported.
- **Public Nominatim** and **public Overpass**: shared community endpoints with
  strict usage policies; not to be used for bulk data acquisition here.

## Moldova official address register

The official Moldova address register is considered a **potential validation
source only**. Its bulk-access permission and downstream reuse terms are
currently **unverified**. It is **not** imported in this stage; any future use
requires confirming its license and access terms first.
