"""Reproducible, resumable-safe source download with a provenance manifest.

The HTTP boundary is a caller-supplied :class:`httpx.Client`, so tests exercise
the full download/hash/atomic-rename/manifest path against an in-memory
``httpx.MockTransport`` with no network access.

Safety properties:

* stream to a temporary ``*.part`` file in the destination directory;
* compute SHA-256 while streaming (no second read);
* rename atomically with :func:`os.replace` only after a complete download;
* never overwrite an existing destination unless ``force=True``.

Provenance rule for an existing file (no ``--force``): the file is only accepted
if a manifest for its path exists **and** the file's SHA-256 matches it. A
missing manifest or a mismatch is a :class:`ProvenanceError`, not a silent pass.
We never mint a fresh manifest (with a fresh ``downloaded_at``) for a file that
was not actually downloaded in this run.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import httpx

from .config import SourceConfig
from .errors import ProvenanceError
from .manifest import DownloadManifest, find_latest_manifest

_CHUNK = 1 << 20  # 1 MiB


def _stream_to_file(client: httpx.Client, url: str, user_agent: str, tmp_path: Path):
    """Stream *url* to *tmp_path*, returning (resolved_url, length, sha256, etag, last_modified)."""
    hasher = hashlib.sha256()
    written = 0
    headers = {"User-Agent": user_agent}
    with client.stream("GET", url, headers=headers) as response:
        response.raise_for_status()
        with open(tmp_path, "wb") as fh:
            for chunk in response.iter_bytes(_CHUNK):
                fh.write(chunk)
                hasher.update(chunk)
                written += len(chunk)
        resolved_url = str(response.url)
        etag = response.headers.get("etag")
        last_modified = response.headers.get("last-modified")
    return resolved_url, written, hasher.hexdigest(), etag, last_modified


def run_download(
    source: SourceConfig,
    *,
    client: httpx.Client,
    downloaded_at: str,
    repo_root: str | Path = ".",
    force: bool = False,
) -> tuple[DownloadManifest, bool]:
    """Download *source* to its configured destination.

    Returns ``(manifest, downloaded)`` where ``downloaded`` is ``False`` when an
    existing file was kept (no ``force``). ``downloaded_at`` is injected by the
    caller so behaviour is deterministic and testable.
    """
    root = Path(repo_root)
    dest = root / source.destination
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and not force:
        # Do NOT trust the file blindly and do NOT fabricate a new manifest.
        # Verify it against the manifest that recorded its original download.
        manifests_dir = root / "data" / "manifests"
        recorded = find_latest_manifest(manifests_dir, source.destination)
        if recorded is None:
            raise ProvenanceError(
                f"{source.destination} exists but no manifest describes it in "
                f"{manifests_dir}; cannot verify provenance. Re-download with "
                "--force, or remove the untrusted file."
            )
        actual_sha = _sha256_file(dest)
        recorded_sha = str(recorded.get("sha256", ""))
        if actual_sha != recorded_sha:
            raise ProvenanceError(
                f"{source.destination} SHA-256 does not match its manifest "
                f"(file={actual_sha}, manifest={recorded_sha}); the file may be "
                "stale or corrupt. Re-download with --force to replace it."
            )
        # Trusted existing file: reuse its ORIGINAL manifest unchanged (its real
        # downloaded_at), and signal that nothing was downloaded this run.
        return DownloadManifest.from_dict(recorded), False

    tmp_path = dest.with_name(dest.name + ".part")
    if tmp_path.exists():
        tmp_path.unlink()
    try:
        resolved_url, length, sha256, etag, last_modified = _stream_to_file(
            client, source.source_url, source.user_agent, tmp_path
        )
        os.replace(tmp_path, dest)  # atomic on the same filesystem
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    manifest = DownloadManifest(
        source_url=source.source_url,
        resolved_url=resolved_url,
        downloaded_at=downloaded_at,
        content_length=length,
        sha256=sha256,
        etag=etag,
        last_modified=last_modified,
        local_path=source.destination,
    )
    return manifest, True


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
