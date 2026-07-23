#!/usr/bin/env python
"""Download an OSM source extract described in ``config/sources.yml``.

Never commits the downloaded file (see ``.gitignore``). Writes a provenance
manifest to ``data/manifests/``. Refuses to overwrite an existing file unless
``--force`` is given.

Usage::

    uv run python scripts/download_osm.py --source osm_moldova
    uv run python scripts/download_osm.py --source osm_moldova --force
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

from bender_zones import jsonutil
from bender_zones.config import load_sources
from bender_zones.download import run_download


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _manifest_filename(source_name: str, downloaded_at: str) -> str:
    stamp = downloaded_at.replace(":", "").replace("-", "")
    return f"{source_name}-{stamp}.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="config/sources.yml",
                        help="path to sources.yml (default: %(default)s)")
    parser.add_argument("--source", default="osm_moldova",
                        help="named source in sources.yml (default: %(default)s)")
    parser.add_argument("--repo-root", default=".",
                        help="repository root for relative paths (default: %(default)s)")
    parser.add_argument("--force", action="store_true",
                        help="overwrite an existing destination file")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    sources = load_sources(args.config)
    if args.source not in sources:
        print(f"error: source '{args.source}' not in {args.config}", file=sys.stderr)
        return 2
    source = sources[args.source]
    downloaded_at = _utc_now_iso()

    transport = httpx.HTTPTransport(retries=max(0, source.max_retries))
    last_error: Exception | None = None
    with httpx.Client(
        follow_redirects=True,
        timeout=source.timeout_seconds,
        transport=transport,
    ) as client:
        for attempt in range(1, source.max_retries + 2):
            try:
                manifest, downloaded = run_download(
                    source,
                    client=client,
                    downloaded_at=downloaded_at,
                    repo_root=args.repo_root,
                    force=args.force,
                )
                break
            except httpx.HTTPError as exc:  # network / status errors
                last_error = exc
                print(f"attempt {attempt} failed: {exc}", file=sys.stderr)
        else:
            print(f"error: download failed after retries: {last_error}", file=sys.stderr)
            return 1

    manifest_dir = Path(args.repo_root) / "data" / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / _manifest_filename(source.name, downloaded_at)
    jsonutil.write(manifest_path, manifest.to_dict())

    action = "downloaded" if downloaded else "kept existing (use --force to refresh)"
    print(f"{action}: {manifest.local_path}")
    print(f"  sha256: {manifest.sha256}")
    print(f"  bytes:  {manifest.content_length}")
    print(f"  manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
