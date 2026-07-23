"""Exact boundary extraction via the external ``osmium`` command-line tool.

To count objects *inside* a candidate boundary we need the boundary polygon and
an exact spatial clip. This module drives ``osmium-tool`` to do that:

1. ``osmium getid -r -t`` pulls the relation plus every referenced member.
2. ``osmium export`` assembles the boundary polygon as GeoJSON.
3. ``osmium extract --polygon`` clips the source to that polygon.

If ``osmium-tool`` is missing, or any step fails, we raise
:class:`SpatialAuditUnavailableError`. We never silently fall back to a
bounding-box count, because a bbox count would overstate coverage by including
neighbouring settlements.

The real subcommand availability is probed at runtime (``osmium --help`` /
``osmium <cmd> --help``) rather than assumed, per the project's audit rules.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import SpatialAuditUnavailableError


def osmium_tool_path() -> str | None:
    """Return the path to the ``osmium`` executable, or ``None`` if absent."""
    return shutil.which("osmium")


def osmium_version() -> str | None:
    """Return the ``osmium-tool`` version string, or ``None`` if unavailable."""
    exe = osmium_tool_path()
    if exe is None:
        return None
    try:
        proc = subprocess.run(
            [exe, "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - defensive
        return None
    line = (proc.stdout or proc.stderr or "").splitlines()
    return line[0].strip() if line else None


def _require_subcommand(exe: str, subcommand: str) -> None:
    """Verify ``osmium <subcommand>`` exists before relying on it."""
    try:
        proc = subprocess.run(
            [exe, subcommand, "--help"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        raise SpatialAuditUnavailableError(
            f"could not probe 'osmium {subcommand}': {exc}"
        ) from exc
    if proc.returncode != 0:
        raise SpatialAuditUnavailableError(
            f"'osmium {subcommand}' is not available in this osmium-tool build"
        )


def _run(exe: str, args: list[str]) -> None:
    proc = subprocess.run(
        [exe, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SpatialAuditUnavailableError(
            "osmium command failed: "
            f"osmium {' '.join(args)}\n{proc.stderr.strip()}"
        )


@dataclass(frozen=True)
class ExtractResult:
    """Paths produced by :func:`extract_boundary`."""

    relation_pbf: Path
    boundary_geojson: Path
    city_pbf: Path


def extract_boundary(
    pbf_path: str | Path,
    relation_id: int,
    workdir: str | Path,
    *,
    strategy: str = "smart",
) -> ExtractResult:
    """Produce an exact city extract clipped to *relation_id*'s polygon.

    Raises :class:`SpatialAuditUnavailableError` if osmium-tool or a required
    subcommand is missing, or if any step fails. Callers must treat that as a
    hard stop, not a reason to approximate.
    """
    exe = osmium_tool_path()
    if exe is None:
        raise SpatialAuditUnavailableError(
            "external 'osmium' (osmium-tool) not found on PATH; exact boundary "
            "extraction is required and bounding-box fallback is not permitted"
        )

    for sub in ("getid", "export", "extract"):
        _require_subcommand(exe, sub)

    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    src = str(pbf_path)

    relation_pbf = work / f"relation-{relation_id}.osm.pbf"
    boundary_geojson = work / f"boundary-{relation_id}.geojson"
    city_pbf = work / f"city-extract-{relation_id}.osm.pbf"

    # 1. Relation + all referenced members (complete geometry pieces).
    _run(exe, ["getid", "-r", "-t", src, f"r{relation_id}",
               "-o", str(relation_pbf), "--overwrite"])

    # 2. Assemble the boundary polygon as GeoJSON.
    _run(exe, ["export", str(relation_pbf), "--geometry-types=polygon",
               "-f", "geojson", "-o", str(boundary_geojson), "--overwrite"])

    # 3. Exact clip of the source to that polygon.
    _run(exe, ["extract", "--polygon", str(boundary_geojson),
               f"--strategy={strategy}", src, "-o", str(city_pbf), "--overwrite"])

    return ExtractResult(
        relation_pbf=relation_pbf,
        boundary_geojson=boundary_geojson,
        city_pbf=city_pbf,
    )
