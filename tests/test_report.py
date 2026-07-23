"""Report assembly: deterministic JSON, boundary_selected false, differences."""

from __future__ import annotations

from bender_zones import jsonutil
from bender_zones.metrics import AddressMetrics
from bender_zones.relations import RelationInfo
from bender_zones.report import build_report, candidate_entry, render_markdown


def _report():
    info_a = RelationInfo(
        id=9581354, found=True,
        tags={"type": "boundary", "boundary": "administrative", "admin_level": "6",
              "name": "Bender"},
        member_count=5, member_type_counts={"w": 5},
    )
    info_b = RelationInfo(
        id=944727, found=True,
        tags={"type": "boundary", "boundary": "administrative", "admin_level": "8",
              "name": "Bender"},
        member_count=3, member_type_counts={"w": 3},
    )
    m_a = AddressMetrics(highway_ways=100, buildings=2000)
    m_b = AddressMetrics(highway_ways=80, buildings=1500)
    candidates = [
        candidate_entry(info_a, "official", "note a", m_a, "ok", None),
        candidate_entry(info_b, "de-facto", "note b", m_b, "ok", None),
    ]
    return build_report(
        generated_at="2026-07-23T00:00:00Z",
        pbf_manifest={"sha256": "x", "local_path": "data/raw/moldova-latest.osm.pbf"},
        tool_versions={"python": "3.12.10", "pyosmium": "4.3.1"},
        candidates=candidates,
        warnings=["some warning"],
    )


def test_boundary_never_selected():
    assert _report()["boundary_selected"] is False


def test_deterministic_json_ordering():
    a = jsonutil.dumps(_report())
    b = jsonutil.dumps(_report())
    assert a == b


def test_differences_include_delta():
    diffs = _report()["differences"]
    assert diffs["highway_ways"]["by_candidate"]["9581354"] == 100
    assert diffs["highway_ways"]["by_candidate"]["944727"] == 80
    assert diffs["highway_ways"]["delta"] == 80 - 100


def test_limitations_present_and_non_empty():
    rep = _report()
    assert rep["limitations"]
    assert any("not complete" in lim.lower() for lim in rep["limitations"])


def test_markdown_renders_without_error():
    md = render_markdown(_report())
    assert "boundary_selected" in md.lower() or "Boundary selected" in md
    assert "relation 9581354" in md
    assert "relation 944727" in md
