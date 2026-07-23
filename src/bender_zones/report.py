"""Assemble the stage-01 source-audit report (JSON + Markdown).

The report is descriptive only. It always carries ``boundary_selected: false``
and an explicit limitations section. It compares the two candidate boundaries
but never declares one the winner.
"""

from __future__ import annotations

from pathlib import Path

from . import jsonutil
from .metrics import AddressMetrics
from .relations import RelationInfo

SCHEMA = "bender-source-audit/1"

_STANDING_LIMITATIONS = [
    "Address coverage in OpenStreetMap is community-contributed and is NOT complete.",
    "No working boundary has been selected; both candidates are reported side by side.",
    "Duplicate metric is a preliminary signal only (NFKC/trim/collapse/casefold); "
    "no transliteration or fuzzy matching is applied.",
    "Metrics are counts of raw OSM objects, not validated postal addresses.",
    "This stage produces no delivery zones, tariffs, routing graph, or address database.",
]


def _candidate_entry(
    info: RelationInfo,
    label: str,
    note: str,
    metrics: AddressMetrics | None,
    spatial_status: str,
    spatial_reason: str | None,
) -> dict:
    return {
        "id": info.id,
        "label": label,
        "note": note,
        "relation": info.to_dict(),
        "spatial_audit": {"status": spatial_status, "reason": spatial_reason},
        "metrics": metrics.to_dict() if metrics is not None else None,
    }


def _differences(candidates: list[dict]) -> dict:
    """Per-metric side-by-side values plus a delta when exactly two are present."""
    with_metrics = [c for c in candidates if c["metrics"] is not None]
    if not with_metrics:
        return {}
    metric_names = list(with_metrics[0]["metrics"].keys())
    diffs: dict[str, dict] = {}
    for name in metric_names:
        values = {str(c["id"]): c["metrics"][name] for c in with_metrics}
        entry: dict = {"by_candidate": values}
        if len(with_metrics) == 2:
            a, b = (c["metrics"][name] for c in with_metrics)
            entry["delta"] = b - a
        diffs[name] = entry
    return diffs


def build_report(
    *,
    generated_at: str,
    pbf_manifest: dict | None,
    tool_versions: dict,
    candidates: list[dict],
    warnings: list[str],
) -> dict:
    """Return the full audit report dictionary."""
    return {
        "schema": SCHEMA,
        "generated_at": generated_at,
        "boundary_selected": False,
        "pbf_manifest": pbf_manifest,
        "tool_versions": tool_versions,
        "candidates": candidates,
        "differences": _differences(candidates),
        "warnings": warnings,
        "limitations": list(_STANDING_LIMITATIONS),
    }


def candidate_entry(
    info: RelationInfo,
    label: str,
    note: str,
    metrics: AddressMetrics | None,
    spatial_status: str,
    spatial_reason: str | None,
) -> dict:
    """Public wrapper used by the CLI."""
    return _candidate_entry(info, label, note, metrics, spatial_status, spatial_reason)


def render_markdown(report: dict) -> str:
    """Render a human-readable Markdown view of *report*."""
    lines: list[str] = []
    lines.append("# Bender OSM source audit — stage 01")
    lines.append("")
    lines.append(f"- Generated at (UTC): `{report['generated_at']}`")
    lines.append(f"- Boundary selected: **{report['boundary_selected']}**")
    lines.append("")

    lines.append("## Tool versions")
    lines.append("")
    for key, value in sorted(report["tool_versions"].items()):
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Source PBF manifest")
    lines.append("")
    manifest = report["pbf_manifest"]
    if manifest is None:
        lines.append("_No manifest recorded for this run._")
    else:
        for key in sorted(manifest):
            lines.append(f"- {key}: `{manifest[key]}`")
    lines.append("")

    lines.append("## Candidate boundaries")
    lines.append("")
    lines.append(
        "> Two candidates are inspected. Neither is selected. A human must review "
        "the tags and metrics below before any boundary is chosen."
    )
    lines.append("")
    for cand in report["candidates"]:
        rel = cand["relation"]
        lines.append(f"### relation {cand['id']} — {cand['label']}")
        lines.append("")
        if cand["note"]:
            lines.append(f"_{cand['note']}_")
            lines.append("")
        lines.append(f"- found: **{rel['found']}**")
        if rel["found"]:
            lines.append(f"- member count: {rel['member_count']}")
            lines.append(f"- member type counts: `{rel['member_type_counts']}`")
            lines.append("- tags:")
            for key in sorted(rel["tags"]):
                lines.append(f"  - `{key}` = `{rel['tags'][key]}`")
        spatial = cand["spatial_audit"]
        lines.append(f"- spatial audit: **{spatial['status']}**")
        if spatial["reason"]:
            lines.append(f"  - reason: {spatial['reason']}")
        if rel["warnings"]:
            lines.append("- warnings:")
            for warn in rel["warnings"]:
                lines.append(f"  - {warn}")
        lines.append("")
        metrics = cand["metrics"]
        if metrics is None:
            lines.append("_No metrics (spatial audit not completed)._")
        else:
            lines.append("| metric | value |")
            lines.append("| --- | ---: |")
            for key in sorted(metrics):
                lines.append(f"| {key} | {metrics[key]} |")
        lines.append("")

    diffs = report["differences"]
    if diffs:
        lines.append("## Differences between boundaries")
        lines.append("")
        ids = sorted({cid for d in diffs.values() for cid in d["by_candidate"]})
        header = "| metric | " + " | ".join(ids) + " | delta |"
        lines.append(header)
        lines.append("| --- |" + " ---: |" * (len(ids) + 1))
        for name in sorted(diffs):
            row = diffs[name]
            cells = [str(row["by_candidate"].get(cid, "")) for cid in ids]
            delta = row.get("delta", "")
            lines.append(f"| {name} | " + " | ".join(cells) + f" | {delta} |")
        lines.append("")

    if report["warnings"]:
        lines.append("## Warnings")
        lines.append("")
        for warn in report["warnings"]:
            lines.append(f"- {warn}")
        lines.append("")

    lines.append("## Limitations")
    lines.append("")
    for lim in report["limitations"]:
        lines.append(f"- {lim}")
    lines.append("")

    return "\n".join(lines)


def write_report(report: dict, output_dir: str | Path) -> tuple[Path, Path]:
    """Write ``source-audit.json`` and ``source-audit.md`` into *output_dir*."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "source-audit.json"
    md_path = out / "source-audit.md"
    jsonutil.write(json_path, report)
    md_path.write_text(render_markdown(report) + "\n", encoding="utf-8", newline="\n")
    return json_path, md_path
