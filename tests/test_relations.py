"""Relation discovery, missing-relation handling, and tag validation warnings."""

from __future__ import annotations

from bender_zones.errors import MissingRelationError
from bender_zones.relations import RelationInfo, find_relations, validate_relation


def test_finds_present_relation_with_real_tags(mini_osm):
    infos = find_relations(mini_osm, [944727])
    info = infos[944727]
    assert info.found is True
    assert info.tags["type"] == "boundary"
    assert info.tags["boundary"] == "administrative"
    assert info.tags["admin_level"] == "8"
    assert info.tags["name"] == "Bender"
    assert info.member_count == 1
    assert info.member_type_counts == {"w": 1}


def test_missing_relation_reported_not_crashing(mini_osm):
    infos = find_relations(mini_osm, [9581354])
    info = infos[9581354]
    assert info.found is False
    assert info.member_count == 0
    assert any("not present" in w for w in info.warnings)


def test_missing_relation_error_helper():
    # A caller that requires presence can raise a typed error.
    info = RelationInfo(id=123, found=False)

    def require(info: RelationInfo) -> None:
        if not info.found:
            raise MissingRelationError(f"relation {info.id} missing")

    try:
        require(info)
    except MissingRelationError as exc:
        assert "123" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected MissingRelationError")


def test_validate_flags_unexpected_tags(mini_osm):
    infos = find_relations(mini_osm, [944727])
    expected = {
        "type": "boundary",
        "boundary": "administrative",
        "admin_level_in": ["6"],  # 8 is deliberately outside → should warn
    }
    info = validate_relation(infos[944727], expected)
    assert any("admin_level" in w for w in info.warnings)


def test_validate_no_warning_when_in_expected_set(mini_osm):
    infos = find_relations(mini_osm, [944727])
    expected = {
        "type": "boundary",
        "boundary": "administrative",
        "admin_level_in": ["6", "7", "8"],
    }
    info = validate_relation(infos[944727], expected)
    assert info.warnings == []
