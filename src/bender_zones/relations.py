"""Discover and validate candidate boundary relations inside a PBF.

This module answers, per candidate relation id:

* is the relation present in the extract?
* what are its *real, current* tags (not what a prompt claimed)?
* how many members does it have, broken down by member type?
* do its tags look like a plausible administrative boundary, or should the
  human reviewer be warned about an unexpected ``type`` / ``boundary`` /
  ``admin_level`` / missing name?

It never ranks or selects a "winner".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import osmium


@dataclass
class RelationInfo:
    """Audit result for a single candidate relation."""

    id: int
    found: bool
    tags: dict[str, str] = field(default_factory=dict)
    member_count: int = 0
    member_type_counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "found": self.found,
            "tags": self.tags,
            "member_count": self.member_count,
            "member_type_counts": self.member_type_counts,
            "warnings": self.warnings,
        }


def find_relations(pbf_path: str | Path, relation_ids: list[int]) -> dict[int, RelationInfo]:
    """Return a :class:`RelationInfo` for each requested id.

    Only the relation section of the file is scanned (via an entity filter),
    so this is inexpensive even on a full-country extract.
    """
    wanted = set(relation_ids)
    discovered: dict[int, RelationInfo] = {}

    for obj in osmium.FileProcessor(str(pbf_path), osmium.osm.RELATION):
        if obj.id not in wanted:
            continue
        member_type_counts: dict[str, int] = {}
        for member in obj.members:
            member_type_counts[member.type] = member_type_counts.get(member.type, 0) + 1
        discovered[obj.id] = RelationInfo(
            id=obj.id,
            found=True,
            tags={k: v for k, v in obj.tags},
            member_count=len(obj.members),
            member_type_counts=member_type_counts,
        )

    result: dict[int, RelationInfo] = {}
    for rid in relation_ids:
        if rid in discovered:
            result[rid] = discovered[rid]
        else:
            result[rid] = RelationInfo(
                id=rid,
                found=False,
                warnings=[f"relation {rid} not present in this PBF extract"],
            )
    return result


def validate_relation(info: RelationInfo, expected: dict) -> RelationInfo:
    """Attach warnings for tags that deviate from a plausible admin boundary.

    ``expected`` is heuristic, not authoritative: it flags values worth a human
    second look, not "the one true answer". Recognised keys:

    * ``type``            — exact expected value (default ``"boundary"``)
    * ``boundary``        — exact expected value (default ``"administrative"``)
    * ``admin_level_in``  — list of acceptable ``admin_level`` strings
    """
    if not info.found:
        return info

    tags = info.tags
    expected_type = expected.get("type", "boundary")
    expected_boundary = expected.get("boundary", "administrative")
    admin_level_in = [str(v) for v in expected.get("admin_level_in", [])]

    if tags.get("type") != expected_type:
        info.warnings.append(
            f"unexpected type={tags.get('type')!r} (expected {expected_type!r})"
        )
    if tags.get("boundary") != expected_boundary:
        info.warnings.append(
            f"unexpected boundary={tags.get('boundary')!r} (expected {expected_boundary!r})"
        )
    admin_level = tags.get("admin_level")
    if admin_level is None:
        info.warnings.append("missing admin_level tag")
    elif admin_level_in and admin_level not in admin_level_in:
        info.warnings.append(
            f"admin_level={admin_level!r} outside expected set {admin_level_in}"
        )
    if not tags.get("name"):
        info.warnings.append("missing name tag")
    return info
