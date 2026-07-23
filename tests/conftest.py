"""Shared pytest fixtures. No test in this suite touches the network."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def mini_osm() -> Path:
    """Path to the tiny hand-written OSM fixture."""
    return FIXTURES / "mini.osm"


@pytest.fixture
def repo_root() -> Path:
    """Repository root (the directory containing pyproject.toml)."""
    return Path(__file__).resolve().parents[1]
