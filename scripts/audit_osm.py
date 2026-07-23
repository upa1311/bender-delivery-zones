#!/usr/bin/env python
"""Audit an OSM PBF for candidate Bender boundaries (inspection only).

For each candidate relation this reports its real tags, member counts, and a
preliminary set of address/road coverage metrics computed over an *exact* city
extract. It never selects a boundary and never approximates coverage with a
bounding box: if exact extraction is impossible it stops with a clear error.

Usage::

    uv run python scripts/audit_osm.py --pbf data/raw/moldova-latest.osm.pbf
    uv run python scripts/audit_osm.py --pbf X.pbf --candidate-relation 9581354 \
        --candidate-relation 944727
    uv run python scripts/audit_osm.py --pbf X.pbf --no-spatial   # tags/members only
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from bender_zones import report as report_mod
from bender_zones.config import (
    CandidateConfig,
    load_audit,
    load_candidates,
    load_sources,
)
from bender_zones.errors import SpatialAuditUnavailableError
from bender_zones.extract import extract_boundary
from bender_zones.metrics import compute_metrics
from bender_zones.relations import find_relations, validate_relation
from bender_zones.versions import tool_versions


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pbf", default=None,
                        help="path to the OSM PBF (default: sources.yml destination)")
    parser.add_argument("--output-dir", default=None,
                        help="report output dir (default: audit.yml report_dir)")
    parser.add_argument("--candidate-relation", type=int, action="append", default=None,
                        metavar="ID", help="candidate relation id (repeatable); "
                                           "overrides boundary-candidates.yml")
    parser.add_argument("--sources-config", default="config/sources.yml")
    parser.add_argument("--candidates-config", default="config/boundary-candidates.yml")
    parser.add_argument("--audit-config", default="config/audit.yml")
    parser.add_argument("--source", default="osm_moldova",
                        help="named source used to resolve the default --pbf")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--no-spatial", action="store_true",
                        help="only inspect tags/members; skip exact metric extraction")
    return parser.parse_args(argv)


def _resolve_candidates(args: argparse.Namespace) -> list[CandidateConfig]:
    if args.candidate_relation:
        return [
            CandidateConfig(id=rid, label=f"relation {rid} (from --candidate-relation)")
            for rid in args.candidate_relation
        ]
    return load_candidates(args.candidates_config)


def _load_pbf_manifest(repo_root: Path, pbf_rel: str) -> dict | None:
    """Return the most recent manifest whose local_path matches *pbf_rel*."""
    manifest_dir = repo_root / "data" / "manifests"
    best: dict | None = None
    for path in sorted(glob.glob(str(manifest_dir / "*.json"))):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(data.get("local_path", "")).replace("\\", "/") == pbf_rel.replace("\\", "/"):
            best = data  # sorted() → last match is newest by timestamped filename
    return best


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root)

    sources = load_sources(args.sources_config)
    audit_cfg = load_audit(args.audit_config)

    pbf_rel = args.pbf or sources[args.source].destination
    pbf_path = repo_root / pbf_rel
    if not pbf_path.is_file():
        print(f"error: PBF not found: {pbf_path}", file=sys.stderr)
        print("hint: run scripts/download_osm.py first (not run in CI).", file=sys.stderr)
        return 2

    output_dir = args.output_dir or audit_cfg.report_dir
    candidates = _resolve_candidates(args)
    warnings: list[str] = []

    # 1. Verify the PBF is readable and 2-3. discover + validate candidate relations.
    try:
        infos = find_relations(pbf_path, [c.id for c in candidates])
    except RuntimeError as exc:  # pyosmium raises on unreadable input
        print(f"error: cannot read PBF {pbf_path}: {exc}", file=sys.stderr)
        return 2

    spatial_failed = False
    entries: list[dict] = []
    for cand in candidates:
        info = validate_relation(infos[cand.id], cand.expected)
        if info.warnings:
            warnings.extend(f"relation {cand.id}: {w}" for w in info.warnings)

        metrics = None
        if not info.found:
            status, reason = "skipped", "relation not present in PBF"
        elif args.no_spatial:
            status, reason = "skipped", "--no-spatial requested"
        else:
            try:
                extract = extract_boundary(
                    pbf_path, cand.id, repo_root / audit_cfg.workdir,
                    strategy=audit_cfg.osmium_strategy,
                )
                metrics = compute_metrics(extract.city_pbf, audit_cfg.car_highway_values)
                status, reason = "ok", None
            except SpatialAuditUnavailableError as exc:
                spatial_failed = True
                status, reason = "unavailable", str(exc)
                warnings.append(f"relation {cand.id}: spatial audit unavailable: {exc}")

        entries.append(
            report_mod.candidate_entry(info, cand.label, cand.note, metrics, status, reason)
        )

    pbf_manifest = _load_pbf_manifest(repo_root, pbf_rel)
    if pbf_manifest is None:
        warnings.append(
            f"no manifest found in data/manifests for {pbf_rel}; provenance unrecorded"
        )

    report = report_mod.build_report(
        generated_at=_utc_now_iso(),
        pbf_manifest=pbf_manifest,
        tool_versions=tool_versions(),
        candidates=entries,
        warnings=warnings,
    )
    json_path, md_path = report_mod.write_report(report, repo_root / output_dir)
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    print("boundary_selected: false")

    if spatial_failed and not args.no_spatial:
        print(
            "error: exact boundary extraction was unavailable for at least one "
            "candidate; bounding-box fallback is not permitted. Install osmium-tool "
            "and re-run, or use --no-spatial for a tags-only audit.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
