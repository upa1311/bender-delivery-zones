"""Exact-extraction guardrails: fail-closed, never fall back to a bounding box.

All osmium-tool interaction is mocked; these tests never invoke the real binary
and never touch the network.
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from bender_zones import extract
from bender_zones.errors import SpatialAuditUnavailableError

VALID_FC = (
    '{"type":"FeatureCollection","features":['
    '{"type":"Feature","properties":{},'
    '"geometry":{"type":"MultiPolygon","coordinates":[[[[0,0],[0,1],[1,1],[0,0]]]]}}]}'
)
EMPTY_FC = '{"type":"FeatureCollection","features":[]}'
WRONG_TYPE_FC = (
    '{"type":"FeatureCollection","features":['
    '{"type":"Feature","properties":{},'
    '"geometry":{"type":"LineString","coordinates":[[0,0],[1,1]]}}]}'
)
CORRUPT = "{not valid json"
TWO_POLYGONS_FC = (
    '{"type":"FeatureCollection","features":['
    '{"type":"Feature","properties":{},"geometry":{"type":"Polygon","coordinates":[[[0,0],[0,1],[1,1],[0,0]]]}},'
    '{"type":"Feature","properties":{},"geometry":{"type":"Polygon","coordinates":[[[2,2],[2,3],[3,3],[2,2]]]}}]}'
)


def _output_path(argv: list[str]) -> str | None:
    if "-o" in argv:
        return argv[argv.index("-o") + 1]
    return None


def make_fake_run(records: list[list[str]], *, export_payload: str = VALID_FC,
                  fail_on: str | None = None):
    """Return a fake ``subprocess.run`` recording argv and simulating osmium."""

    def fake_run(cmd, *args, **kwargs):
        argv = list(cmd[1:])  # drop the exe
        records.append(argv)
        subcommand = argv[0] if argv else ""
        if subcommand == "export" and fail_on != "export":
            out = _output_path(argv)
            if out is not None:
                Path(out).write_text(export_payload, encoding="utf-8")
        rc = 1 if subcommand == fail_on else 0
        return types.SimpleNamespace(returncode=rc, stdout="", stderr=f"boom:{subcommand}")

    return fake_run


def _subcommands(records: list[list[str]]) -> list[str]:
    return [argv[0] for argv in records if argv]


# --- success path -----------------------------------------------------------

def test_success_path_runs_exact_command_sequence(monkeypatch, tmp_path):
    monkeypatch.setattr(extract, "osmium_tool_path", lambda: "osmium")
    records: list[list[str]] = []
    monkeypatch.setattr(extract.subprocess, "run", make_fake_run(records))

    result = extract.extract_boundary("moldova.osm.pbf", 944727, tmp_path)

    # exact operation order: getid -> export -> extract
    assert _subcommands(records) == ["getid", "export", "extract"]

    getid, export, clip = records
    # 1. getid recursive, referenced members
    assert getid[0] == "getid" and "-r" in getid and "-t" in getid and "r944727" in getid
    # 2. export is fail-closed and polygon-only
    assert export[0] == "export"
    assert "--stop-on-error" in export
    assert "--geometry-types=polygon" in export
    # 3. extract clips by the exported polygon
    assert clip[0] == "extract" and "--polygon" in clip
    assert result.geometry_type == "MultiPolygon"
    assert result.city_pbf.name == "city-extract-944727.osm.pbf"


# --- geometry validation failures (extract must NOT run) --------------------

@pytest.mark.parametrize(
    "payload, needle",
    [
        (EMPTY_FC, "empty FeatureCollection"),
        (WRONG_TYPE_FC, "no Polygon/MultiPolygon"),
        (CORRUPT, "corrupt"),
        (TWO_POLYGONS_FC, "ambiguous"),
    ],
)
def test_invalid_geometry_fails_closed(monkeypatch, tmp_path, payload, needle):
    monkeypatch.setattr(extract, "osmium_tool_path", lambda: "osmium")
    records: list[list[str]] = []
    monkeypatch.setattr(
        extract.subprocess, "run", make_fake_run(records, export_payload=payload)
    )

    with pytest.raises(SpatialAuditUnavailableError) as exc:
        extract.extract_boundary("moldova.osm.pbf", 944727, tmp_path)

    assert needle in str(exc.value)
    # export ran, but the clip must never be attempted
    assert "export" in _subcommands(records)
    assert "extract" not in _subcommands(records)


def test_missing_geojson_file_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(extract, "osmium_tool_path", lambda: "osmium")
    records: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        argv = list(cmd[1:])
        records.append(argv)
        # deliberately do NOT write the export output file
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(extract.subprocess, "run", fake_run)
    with pytest.raises(SpatialAuditUnavailableError):
        extract.extract_boundary("moldova.osm.pbf", 944727, tmp_path)
    assert "extract" not in _subcommands(records)


# --- osmium command failures ------------------------------------------------

@pytest.mark.parametrize("failing", ["getid", "export", "extract"])
def test_command_failure_fails_closed(monkeypatch, tmp_path, failing):
    monkeypatch.setattr(extract, "osmium_tool_path", lambda: "osmium")
    records: list[list[str]] = []
    monkeypatch.setattr(
        extract.subprocess, "run", make_fake_run(records, fail_on=failing)
    )

    with pytest.raises(SpatialAuditUnavailableError) as exc:
        extract.extract_boundary("moldova.osm.pbf", 944727, tmp_path)
    assert failing in str(exc.value)

    run_subcommands = _subcommands(records)
    if failing == "getid":
        assert run_subcommands == ["getid"]  # stops immediately
    elif failing == "export":
        assert run_subcommands == ["getid", "export"]
        assert "extract" not in run_subcommands
    else:  # extract itself fails, but only after everything before it succeeded
        assert run_subcommands == ["getid", "export", "extract"]


# --- tool availability ------------------------------------------------------

def test_missing_osmium_tool_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(extract, "osmium_tool_path", lambda: None)
    with pytest.raises(SpatialAuditUnavailableError) as exc:
        extract.extract_boundary("whatever.pbf", 944727, tmp_path)
    assert "osmium" in str(exc.value).lower()


def test_osmium_version_none_when_absent(monkeypatch):
    monkeypatch.setattr(extract, "osmium_tool_path", lambda: None)
    assert extract.osmium_version() is None
