"""The .gitignore must exclude every large/generated geodata format."""

from __future__ import annotations

REQUIRED_PATTERNS = [
    "*.osm.pbf",
    "*.pbf",
    "*.gpkg",
    "*.sqlite",
    "*.mbtiles",
    "*.geojson",
    "*.osrm",
    "*.poly",
    "*.o5m",
    "data/raw/*",
    "data/interim/*",
    "data/processed/*",
    "reports/stage-01/*",
]


def test_gitignore_covers_generated_formats(repo_root):
    text = (repo_root / ".gitignore").read_text(encoding="utf-8")
    lines = {line.strip() for line in text.splitlines()}
    missing = [p for p in REQUIRED_PATTERNS if p not in lines]
    assert not missing, f".gitignore missing patterns: {missing}"


def test_gitignore_keeps_folders_but_allows_manifests(repo_root):
    text = (repo_root / ".gitignore").read_text(encoding="utf-8")
    assert "!data/**/.gitkeep" in text
    assert "!data/manifests/*.json" in text
