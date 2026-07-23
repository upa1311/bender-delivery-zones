"""Exact-extraction guardrails: never silently fall back to a bounding box."""

from __future__ import annotations

import pytest

from bender_zones import extract
from bender_zones.errors import SpatialAuditUnavailableError


def test_missing_osmium_tool_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(extract, "osmium_tool_path", lambda: None)
    with pytest.raises(SpatialAuditUnavailableError) as exc:
        extract.extract_boundary("whatever.pbf", 944727, tmp_path)
    assert "osmium-tool" in str(exc.value).lower() or "osmium" in str(exc.value).lower()


def test_missing_subcommand_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(extract, "osmium_tool_path", lambda: "osmium")

    def fake_run(*args, **kwargs):
        class P:
            returncode = 1
            stdout = ""
            stderr = "unknown command"

        return P()

    monkeypatch.setattr(extract.subprocess, "run", fake_run)
    with pytest.raises(SpatialAuditUnavailableError):
        extract.extract_boundary("whatever.pbf", 944727, tmp_path)


def test_osmium_version_none_when_absent(monkeypatch):
    monkeypatch.setattr(extract, "osmium_tool_path", lambda: None)
    assert extract.osmium_version() is None
