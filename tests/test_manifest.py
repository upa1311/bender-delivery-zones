"""Manifest serialization + deterministic JSON ordering."""

from __future__ import annotations

import json

from bender_zones import jsonutil
from bender_zones.manifest import DownloadManifest


def _sample() -> DownloadManifest:
    return DownloadManifest(
        source_url="https://example.org/moldova-latest.osm.pbf",
        resolved_url="https://cdn.example.org/moldova-latest.osm.pbf",
        downloaded_at="2026-07-23T10:11:12Z",
        content_length=123456,
        sha256="a" * 64,
        etag='"abc123"',
        last_modified="Tue, 22 Jul 2026 00:00:00 GMT",
        local_path="data/raw/moldova-latest.osm.pbf",
    )


def test_roundtrip_dict():
    m = _sample()
    assert DownloadManifest.from_dict(m.to_dict()) == m


def test_all_required_fields_present():
    d = _sample().to_dict()
    for key in (
        "source_url", "resolved_url", "downloaded_at", "content_length",
        "sha256", "etag", "last_modified", "local_path",
    ):
        assert key in d


def test_json_is_deterministic():
    m = _sample()
    assert m.to_json() == m.to_json()


def test_json_keys_are_sorted():
    m = _sample()
    parsed = json.loads(m.to_json())
    dumped_keys = list(json.loads(jsonutil.dumps(parsed)).keys())
    # sort_keys=True → serialized order is alphabetical
    text = m.to_json()
    positions = [text.index(f'"{k}"') for k in sorted(parsed)]
    assert positions == sorted(positions)
    assert dumped_keys == sorted(dumped_keys)


def test_json_preserves_unicode_and_trailing_newline():
    out = jsonutil.dumps({"street": "Ленина"})
    assert "Ленина" in out
    assert out.endswith("\n")
