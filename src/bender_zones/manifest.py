"""Download manifest model.

A manifest is a small, self-describing JSON record produced for every
downloaded source file. It records provenance so an audit run is reproducible
and auditable without keeping the (git-ignored) PBF in version control.
"""

from __future__ import annotations

import glob
import json
from dataclasses import dataclass
from pathlib import Path

from . import jsonutil


@dataclass(frozen=True)
class DownloadManifest:
    """Provenance record for one downloaded source artifact."""

    source_url: str
    resolved_url: str
    downloaded_at: str  # ISO-8601 UTC, e.g. "2026-07-23T10:11:12Z"
    content_length: int | None
    sha256: str
    etag: str | None
    last_modified: str | None
    local_path: str  # repository-relative path

    def to_dict(self) -> dict:
        """Return an ordered plain-dict view (keys are sorted on serialization)."""
        return {
            "source_url": self.source_url,
            "resolved_url": self.resolved_url,
            "downloaded_at": self.downloaded_at,
            "content_length": self.content_length,
            "sha256": self.sha256,
            "etag": self.etag,
            "last_modified": self.last_modified,
            "local_path": self.local_path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DownloadManifest:
        """Reconstruct a manifest from a parsed dict."""
        return cls(
            source_url=data["source_url"],
            resolved_url=data["resolved_url"],
            downloaded_at=data["downloaded_at"],
            content_length=data.get("content_length"),
            sha256=data["sha256"],
            etag=data.get("etag"),
            last_modified=data.get("last_modified"),
            local_path=data["local_path"],
        )

    def to_json(self) -> str:
        """Serialize deterministically."""
        return jsonutil.dumps(self.to_dict())


def _normalize(path: str) -> str:
    return str(path).replace("\\", "/")


def find_latest_manifest(manifests_dir: str | Path, local_path: str) -> dict | None:
    """Return the newest manifest dict describing *local_path*, or ``None``.

    Manifest filenames are timestamped, so lexical sort ascending means the last
    match is the most recent. Unreadable files are skipped.
    """
    target = _normalize(local_path)
    best: dict | None = None
    for candidate in sorted(glob.glob(str(Path(manifests_dir) / "*.json"))):
        try:
            data = json.loads(Path(candidate).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and _normalize(data.get("local_path", "")) == target:
            best = data
    return best
