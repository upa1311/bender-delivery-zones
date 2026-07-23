"""Atomic download behavior via a mock HTTP transport (no network)."""

from __future__ import annotations

import hashlib

import httpx
import pytest

from bender_zones.config import SourceConfig
from bender_zones.download import run_download
from bender_zones.errors import ProvenanceError
from bender_zones.manifest import DownloadManifest

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


def _write_existing(tmp_path, content: bytes = b"original"):
    dest = tmp_path / "data/raw/x.osm.pbf"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(content)
    return dest


def _write_manifest(tmp_path, sha: str, *, downloaded_at="2026-07-20T00:00:00Z"):
    mdir = tmp_path / "data/manifests"
    mdir.mkdir(parents=True, exist_ok=True)
    manifest = DownloadManifest(
        source_url="https://example.org/x.osm.pbf",
        resolved_url="https://example.org/x.osm.pbf",
        downloaded_at=downloaded_at,
        content_length=8,
        sha256=sha,
        etag=None,
        last_modified=None,
        local_path="data/raw/x.osm.pbf",
    )
    (mdir / "x-20260720T000000Z.json").write_text(manifest.to_json(), encoding="utf-8")
    return manifest


def _no_call_client():
    def handler(request):  # pragma: no cover - must never be called
        raise AssertionError("HTTP request must not be made for an existing file")

    return _client(handler)


def test_existing_file_with_matching_manifest_is_reused(tmp_path):
    dest = _write_existing(tmp_path)
    original = _write_manifest(tmp_path, hashlib.sha256(b"original").hexdigest())

    with _no_call_client() as client:
        manifest, downloaded = run_download(
            _source(), client=client, downloaded_at="2026-07-23T00:00:00Z",
            repo_root=tmp_path,
        )

    assert downloaded is False
    assert dest.read_bytes() == b"original"
    # reuses the ORIGINAL manifest, not a fabricated fresh one
    assert manifest.downloaded_at == original.downloaded_at
    assert manifest.downloaded_at != "2026-07-23T00:00:00Z"
    assert manifest.sha256 == original.sha256


def test_existing_file_without_manifest_raises(tmp_path):
    _write_existing(tmp_path)  # no manifest written

    with _no_call_client() as client, pytest.raises(ProvenanceError) as exc:
        run_download(_source(), client=client, downloaded_at="t", repo_root=tmp_path)
    assert "--force" in str(exc.value)


def test_existing_file_sha_mismatch_raises(tmp_path):
    _write_existing(tmp_path, b"original")
    _write_manifest(tmp_path, "deadbeef" * 8)  # wrong sha

    with _no_call_client() as client, pytest.raises(ProvenanceError) as exc:
        run_download(_source(), client=client, downloaded_at="t", repo_root=tmp_path)
    assert "SHA-256" in str(exc.value)
    assert "--force" in str(exc.value)


def test_force_replaces_file_and_makes_fresh_manifest(tmp_path):
    dest = _write_existing(tmp_path)
    _write_manifest(tmp_path, hashlib.sha256(b"original").hexdigest())

    def handler(request):
        return httpx.Response(200, content=PAYLOAD, headers={"etag": '"v2"'})

    with _client(handler) as client:
        manifest, downloaded = run_download(
            _source(), client=client, downloaded_at="2026-07-23T09:09:09Z",
            repo_root=tmp_path, force=True,
        )

    assert downloaded is True
    assert dest.read_bytes() == PAYLOAD
    # fresh manifest reflects THIS run
    assert manifest.downloaded_at == "2026-07-23T09:09:09Z"
    assert manifest.sha256 == hashlib.sha256(PAYLOAD).hexdigest()
    assert manifest.etag == '"v2"'


def test_http_error_leaves_no_destination(tmp_path):
    def handler(request):
        return httpx.Response(500)

    with _client(handler) as client:  # noqa: SIM117
        with pytest.raises(httpx.HTTPStatusError):
            run_download(_source(), client=client, downloaded_at="t", repo_root=tmp_path)

    assert not (tmp_path / "data/raw/x.osm.pbf").exists()
    assert not (tmp_path / "data/raw/x.osm.pbf.part").exists()
