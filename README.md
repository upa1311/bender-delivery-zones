# bender-delivery-zones

Reproducible **OpenStreetMap source-audit** scaffold for the Bender
delivery-zone project. This is the *first* micro-batch: it sets up the project
and a source pre-audit tool. **Nothing here builds delivery zones.**

## Scope

**In scope (this stage):**

- A reproducible project skeleton (uv, ruff, pytest).
- A download tool for the Geofabrik Moldova OSM extract, with a provenance
  manifest and SHA-256.
- An audit tool that inspects two *candidate* boundary relations and reports
  raw address/road coverage metrics per candidate.

**Explicitly OUT of scope (this stage):**

- ❌ Creating or drawing delivery zones / polygons.
- ❌ Computing tariffs or a tariff matrix.
- ❌ Running or integrating any routing engine (OSRM / Valhalla / GraphHopper).
- ❌ Selecting a working boundary for Bender.
- ❌ Producing a production address database.
- ❌ Any integration with `direct-platform`, `DirectDelivery`, or other
  product repositories.

> **Integration with Direct is forbidden until manual acceptance.** This
> repository is standalone. Do not wire any of its output into Direct until a
> human has reviewed and accepted the audit results.

## ⚠️ Two candidate boundaries — neither is selected

The brief names two boundary relations. This tool **verifies and reports** both
but never picks one:

| relation | described as |
| --- | --- |
| `9581354` | official Municipiul Bender / MD-BD boundary |
| `944727`  | de-facto Bender City Council boundary |

The descriptions above come from the brief. The audit reports each relation's
**real, current tags from the PBF**; if the PBF disagrees, the PBF wins.
Choosing between the two is a later, human decision. The report always carries
`boundary_selected: false`.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- (audit, exact spatial step only) the external **osmium-tool** command
  (`osmium`). Install via your OS package manager (e.g. `apt install osmium-tool`,
  `brew install osmium-tool`, `conda install -c conda-forge osmium-tool`). If it
  is missing, the audit stops with a clear error instead of approximating.

## Setup

```bash
uv sync
```

## Quality gates (offline, no PBF download)

```bash
uv run ruff check .
uv run pytest
uv run python scripts/audit_osm.py --help
```

## Download the source (network; run locally, not in CI)

```bash
uv run python scripts/download_osm.py --source osm_moldova
```

This writes `data/raw/moldova-latest.osm.pbf` (git-ignored) and a manifest under
`data/manifests/` (committed intentionally). It refuses to overwrite an existing
file unless you pass `--force`.

## Run the audit (local; needs the PBF and osmium-tool)

```bash
# tags + members + exact per-boundary metrics
uv run python scripts/audit_osm.py --pbf data/raw/moldova-latest.osm.pbf

# tags + members only, no spatial extraction
uv run python scripts/audit_osm.py --pbf data/raw/moldova-latest.osm.pbf --no-spatial
```

Outputs:

- `reports/stage-01/source-audit.json`
- `reports/stage-01/source-audit.md`

## Generated directories

These hold regenerated artifacts and are **git-ignored** (folders kept via
`.gitkeep`); manifests are the deliberate exception and are committed.

| directory | contents |
| --- | --- |
| `data/raw/`       | downloaded source extracts (`*.osm.pbf`) — never committed |
| `data/interim/`   | scratch: relation extracts, boundary GeoJSON, city clips |
| `data/processed/` | reserved for later, cleaned outputs |
| `data/manifests/` | download provenance manifests (JSON) — **committed** |
| `reports/stage-01/` | generated audit reports |

## Attribution

Data © **OpenStreetMap contributors**, licensed under **ODbL 1.0**. Extract
distributed by **Geofabrik**. See [NOTICE.md](NOTICE.md) and
[docs/licensing.md](docs/licensing.md).

## Project decisions

- [ADR-001 — separate repository](docs/decisions/ADR-001-separate-repository.md)
- [ADR-002 — OSM/Geofabrik as primary source](docs/decisions/ADR-002-osm-geofabrik-primary-source.md)
