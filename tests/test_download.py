"""Atomic download behavior via a mock HTTP transport (no network)."""

from __future__ import annotations

import hashlib

import httpx
import pytest

from bender_zones.config import SourceConfig
from bender_zones.download import run_download

PAYLOAD = b"fake-pbf-bytes-" * 1000


def _source(dest: str = "data/raw/x.osm.pbf") -> SourceConfig:
    return SourceConfig(
        name="x",
        source_url="https://example.org/x.osm.pbf",
        destination=dest,
        user_agent="test-agent/1.0",
        timeout_seconds=5,
        max_retries=1,
    )


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_download_writes_file_and_hashes(tmp_path):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["ua"] = request.headers.get("user-agent")
        return httpx.Response(
            200, content=PAYLOAD,
            headers={"etag": '"v1"', "last-modified": "Mon, 21 Jul 2026 00:00:00 GMT"},
        )

    with _client(handler) as client:
        manifest, downloaded = run_download(
            _source(), client=client, downloaded_at="2026-07-23T00:00:00Z",
            repo_root=tmp_path,
        )

    dest = tmp_path / "data/raw/x.osm.pbf"
    assert downloaded is True
    assert dest.read_bytes() == PAYLOAD
    assert manifest.sha256 == hashlib.sha256(PAYLOAD).hexdigest()
    assert manifest.content_length == len(PAYLOAD)
    assert manifest.etag == '"v1"'
    assert manifest.last_modified == "Mon, 21 Jul 2026 00:00:00 GMT"
    assert manifest.local_path == "data/raw/x.osm.pbf"
    assert seen["ua"] == "test-agent/1.0"


def test_no_part_file_left_behind(tmp_path):
    def handler(request):
        return httpx.Response(200, content=PAYLOAD)

    with _client(handler) as client:
        run_download(_source(), client=client, downloaded_at="t", repo_root=tmp_path)

    assert not (tmp_path / "data/raw/x.osm.pbf.part").exists()


def test_existing_file_kept_without_force(tmp_path):
    dest = tmp_path / "data/raw/x.osm.pbf"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"original")

    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, content=PAYLOAD)

    with _client(handler) as client:
        manifest, downloaded = run_download(
            _source(), client=client, downloaded_at="t", repo_root=tmp_path,
        )

    assert downloaded is False
    assert dest.read_bytes() == b"original"  # not overwritten
    assert calls["n"] == 0  # no HTTP request made
    assert manifest.sha256 == hashlib.sha256(b"original").hexdigest()


def test_force_overwrites_existing(tmp_path):
    dest = tmp_path / "data/raw/x.osm.pbf"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"original")

    def handler(request):
        return httpx.Response(200, content=PAYLOAD)

    with _client(handler) as client:
        _, downloaded = run_download(
            _source(), client=client, downloaded_at="t", repo_root=tmp_path, force=True,
        )

    assert downloaded is True
    assert dest.read_bytes() == PAYLOAD


def test_http_error_leaves_no_destination(tmp_path):
    def handler(request):
        return httpx.Response(500)

    with _client(handler) as client:  # noqa: SIM117
        with pytest.raises(httpx.HTTPStatusError):
            run_download(_source(), client=client, downloaded_at="t", repo_root=tmp_path)

    assert not (tmp_path / "data/raw/x.osm.pbf").exists()
    assert not (tmp_path / "data/raw/x.osm.pbf.part").exists()
