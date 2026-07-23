# ADR-001 — Separate repository for Bender delivery-zone research

- Status: Accepted
- Date: 2026-07-23

## Context

The Bender delivery-zone work involves exploratory GIS processing over OSM data:
downloading large extracts, building geometry, and (later) modeling zones and
tariffs. The existing product repositories (`direct-platform`, `DirectDelivery`)
are production codebases with their own release, review, and data-handling
constraints.

Mixing an exploratory geodata pipeline into a product repo risks:

- committing large binary geodata by accident,
- coupling experimental modeling to production release cycles,
- premature, unreviewed integration of unvalidated boundaries and metrics.

## Decision

Do this work in a **separate, standalone repository** (`bender-delivery-zones`).
No file in `direct-platform`, `DirectDelivery`, or any other product repository
is created, modified, or committed as part of this work.

Integration into Direct is **explicitly deferred** until a human has reviewed
and accepted the outputs of this research (see README scope).

## Consequences

- Clean isolation: large geodata and experiments never touch production repos.
- The repo owns its own tooling (uv, ruff, pytest) and `.gitignore` tuned for
  geodata.
- A later, deliberate integration step will be needed once (and if) results are
  accepted. That step is out of scope here.
