"""Exact boundary extraction via the external ``osmium`` command-line tool.

To count objects *inside* a candidate boundary we need the boundary polygon and
an exact spatial clip. This module drives ``osmium-tool`` to do that, in a
strictly **fail-closed** sequence:

1. ``osmium getid -r -t``    pulls the relation plus every referenced member.
2. ``osmium export --stop-on-error`` assembles the boundary polygon as GeoJSON.
3. (validate)                the GeoJSON must be a FeatureCollection containing
                             exactly one Polygon/MultiPolygon feature.
4. ``osmium extract --polygon`` clips the source to that polygon.

If ``osmium-tool`` is missing, any command fails, or the exported geometry is
empty / corrupt / ambiguous, we raise :class:`SpatialAuditUnavailableError`
**before** attempting the clip. We never silently fall back to a bounding-box
count, because a bbox count would overstate coverage by including neighbouring
settlements.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import SpatialAuditUnavailableError


def osmium_tool_path() -> str | None:
    """Return the path to the ``osmium`` executable, or ``None`` if absent.

    osmium-tool selects its sub-command from ``argv[0]``'s basename and expects
    it to be exactly ``osmium``. On Windows ``shutil.which`` resolves to
    ``osmium.EXE``, whose basename (``osmium.EXE``) breaks that dispatch. The
    conda-forge build ships an extensionless, hard-linked ``osmium`` alongside
    it; prefer that so the basename is ``osmium``.
    """
    found = shutil.which("osmium")
    if found is None:
        return None
    path = Path(found)
    if path.suffix.lower() == ".exe":
        # Drop the extension: subprocess passes this string as argv[0] (basename
        # "osmium", which osmium-tool requires), while Windows CreateProcess
        # re-appends ".exe" to locate the real binary.
        return str(path.with_suffix(""))
    return found


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


def _run(exe: str, args: list[str]) -> None:
    """Run ``osmium <args>``; raise fail-closed on any error or non-zero exit."""
    try:
        proc = subprocess.run(
            [exe, *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SpatialAuditUnavailableError(
            f"failed to execute 'osmium {args[0]}': {exc}"
        ) from exc
    if proc.returncode != 0:
        raise SpatialAuditUnavailableError(
            "osmium command failed (exit "
            f"{proc.returncode}): osmium {' '.join(args)}\n{(proc.stderr or '').strip()}"
        )


def _validate_boundary_geojson(path: Path) -> str:
    """Validate the exported boundary GeoJSON, fail-closed.

    Returns the single polygon geometry type on success. Raises
    :class:`SpatialAuditUnavailableError` when the result is missing, empty,
    corrupt, not a FeatureCollection, contains no Polygon/MultiPolygon, or is
    ambiguous (more than one polygon feature, or unexpected geometry types).
    """
    if not path.exists():
        raise SpatialAuditUnavailableError(
            f"osmium export produced no GeoJSON at {path}"
        )
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        raise SpatialAuditUnavailableError(
            f"exported boundary GeoJSON is empty: {path}"
        )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SpatialAuditUnavailableError(
            f"exported boundary GeoJSON is corrupt/invalid JSON: {path}: {exc}"
        ) from exc

    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise SpatialAuditUnavailableError(
            f"exported boundary GeoJSON is not a FeatureCollection: {path}"
        )
    features = data.get("features")
    if not isinstance(features, list) or len(features) == 0:
        raise SpatialAuditUnavailableError(
            f"exported boundary GeoJSON has an empty FeatureCollection: {path}"
        )

    polygon_types: list[str] = []
    other_types: list[str] = []
    for feature in features:
        geometry = (feature or {}).get("geometry") or {}
        gtype = geometry.get("type")
        if gtype in ("Polygon", "MultiPolygon"):
            polygon_types.append(gtype)
        else:
            other_types.append(str(gtype))

    if not polygon_types:
        raise SpatialAuditUnavailableError(
            "exported boundary GeoJSON contains no Polygon/MultiPolygon geometry "
            f"(saw {other_types or 'nothing usable'}): {path}"
        )
    if other_types:
        raise SpatialAuditUnavailableError(
            "exported boundary GeoJSON is ambiguous: mixed geometry types "
            f"{polygon_types + other_types}: {path}"
        )
    if len(polygon_types) > 1:
        raise SpatialAuditUnavailableError(
            "exported boundary GeoJSON is ambiguous: expected exactly one boundary "
            f"polygon feature, found {len(polygon_types)}: {path}"
        )
    return polygon_types[0]


@dataclass(frozen=True)
class ExtractResult:
    """Paths produced by :func:`extract_boundary`."""

    relation_pbf: Path
    boundary_geojson: Path
    city_pbf: Path
    geometry_type: str


def extract_boundary(
    pbf_path: str | Path,
    relation_id: int,
    workdir: str | Path,
    *,
    strategy: str = "smart",
) -> ExtractResult:
    """Produce an exact city extract clipped to *relation_id*'s polygon.

    Raises :class:`SpatialAuditUnavailableError` if osmium-tool is missing, any
    command fails, or the exported geometry is empty/corrupt/ambiguous. Callers
    must treat that as a hard stop, not a reason to approximate.
    """
    exe = osmium_tool_path()
    if exe is None:
        raise SpatialAuditUnavailableError(
            "external 'osmium' (osmium-tool) not found on PATH; exact boundary "
            "extraction is required and bounding-box fallback is not permitted"
        )

    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    src = str(pbf_path)

    relation_pbf = work / f"relation-{relation_id}.osm.pbf"
    boundary_geojson = work / f"boundary-{relation_id}.geojson"
    city_pbf = work / f"city-extract-{relation_id}.osm.pbf"

    # 1. Relation + all referenced members (complete geometry pieces).
    _run(exe, ["getid", "-r", "-t", src, f"r{relation_id}",
               "-o", str(relation_pbf), "--overwrite"])

    # 2. Assemble the boundary polygon as GeoJSON, aborting on any geometry error.
    _run(exe, ["export", str(relation_pbf), "--stop-on-error",
               "--geometry-types=polygon", "-f", "geojson",
               "-o", str(boundary_geojson), "--overwrite"])

    # 3. Validate the exported geometry BEFORE clipping. Fail-closed.
    geometry_type = _validate_boundary_geojson(boundary_geojson)

    # 4. Exact clip of the source to that polygon.
    _run(exe, ["extract", "--polygon", str(boundary_geojson),
               f"--strategy={strategy}", src, "-o", str(city_pbf), "--overwrite"])

    return ExtractResult(
        relation_pbf=relation_pbf,
        boundary_geojson=boundary_geojson,
        city_pbf=city_pbf,
        geometry_type=geometry_type,
    )
