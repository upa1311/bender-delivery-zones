"""Regression guardrails for the manual-Yandex router audit."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data/interim"
DOCS = REPO / "docs/data"

SPEC = importlib.util.spec_from_file_location(
    "evaluate_router_against_manual_yandex",
    REPO / "scripts/evaluate_router_against_manual_yandex.py",
)
assert SPEC and SPEC.loader
EVALUATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVALUATOR)

GRAPH_SPEC = importlib.util.spec_from_file_location(
    "stage10d_graph",
    REPO / "scripts/stage10d_graph.py",
)
assert GRAPH_SPEC and GRAPH_SPEC.loader
GRAPH_MODULE = importlib.util.module_from_spec(GRAPH_SPEC)
GRAPH_SPEC.loader.exec_module(GRAPH_MODULE)

PROTECTED_HASHES = {
    "config/bands.yml": "ebec96536b0f68ad8b2d41a9a04874dfd29acab56eec20f42a5e188ad00b6c8e",
    "config/boundary-candidates.yml": (
        "20613af883a1be3787ada1ab48ded0f20628ed1805eda34e21233bd8568c9b53"
    ),
    "docs/data/final-zone-polygons.geojson": (
        "cfc80697a7300890321319845704f1601f9a35317d80c99ec909d4be68e9db00"
    ),
    "docs/data/final-address-zone-catalog.csv": (
        "1a7207a5e5d6b868ba99662f86da99b08ab8dfb7cf215cab5b9f2e8f5dce4c87"
    ),
    "docs/data/tariff-band-metrics.json": (
        "5a15d0086d4f04428e0cc3d8065ae120841040e7c31e707876484b1bf9eefd70"
    ),
    "docs/data/stage10d-graph-provenance.json": (
        "da8e656b6f994d15c7df8f5cd839d79cc3b477955c0fb728ec849327b0de7c60"
    ),
    "vendor/osrm/profiles/car.lua": (
        "48bbb716c2b68ce6803a11a4151fcac050c6ea8240295e7dde111f15f8bd3984"
    ),
}
RELEASES_HASH = "49edbc87a1f65b2a4c038bd395c5e9880038bf57208c98b9701564135704e9b4"


def rows(name: str) -> list[dict[str, str]]:
    with (DATA / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def normalized_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def releases_hash() -> str:
    digest = hashlib.sha256()
    root = REPO / "releases"
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()


def graph_payload(phys, edges, phys_dirs, node_out, coords, classes=None):
    classes = classes or ["public"] * len(phys)
    physical = [(*segment, cls) for segment, cls in zip(phys, classes, strict=True)]
    return {
        "phys": physical,
        "edges": edges,
        "phys_dirs": phys_dirs,
        "node_out": node_out,
        "coords": coords,
        "way_tags": {},
        "barriers": set(),
        "no_node": {},
        "only_node": {},
        "via_way": [],
        "phys_component": {},
        "provenance": {},
    }


def test_all_86_controls_have_unique_evaluator_results():
    result = rows("router-baseline-v1.csv")
    ids = [row["control_id"] for row in result]
    assert len(ids) == len(set(ids)) == 86


def test_no_routable_control_has_an_empty_router_result():
    result = rows("router-baseline-v1.csv")
    assert all(row["current_router_km"] for row in result)
    assert all(float(row["current_router_km"]) > 0 for row in result)


def test_snap_distances_are_bounded_and_large_snaps_are_flagged():
    result = rows("router-baseline-v1.csv")
    assert max(float(row["snap_distance_m"]) for row in result) < 100
    for row in result:
        if float(row["snap_distance_m"]) > EVALUATOR.SNAP_WARNING_M:
            assert row["router_status"] == "SUSPICIOUS_SNAP"


def test_same_street_name_cannot_connect_disconnected_segments():
    payload = graph_payload(
        phys=[(1, 2, 100.0, 10), (3, 4, 100.0, 10)],
        edges=[(1, 2, 100.0, 10, 0), (2, 1, 100.0, 10, 0),
               (3, 4, 100.0, 10, 1), (4, 3, 100.0, 10, 1)],
        phys_dirs=[[0, 1], [2, 3]],
        node_out={1: [0], 2: [1], 3: [2], 4: [3]},
        coords={1: (29.0, 46.0), 2: (29.001, 46.0),
                3: (29.002, 46.0), 4: (29.003, 46.0)},
    )
    assert GRAPH_MODULE.Graph(payload).route_km((29.0, 46.0), (29.003, 46.0)) is None


def test_overpass_geometry_does_not_create_a_false_junction():
    payload = graph_payload(
        phys=[(1, 2, 100.0, 10), (3, 4, 100.0, 20)],
        edges=[(1, 2, 100.0, 10, 0), (2, 1, 100.0, 10, 0),
               (3, 4, 100.0, 20, 1), (4, 3, 100.0, 20, 1)],
        phys_dirs=[[0, 1], [2, 3]],
        node_out={1: [0], 2: [1], 3: [2], 4: [3]},
        coords={1: (29.0, 46.0), 2: (29.002, 46.0),
                3: (29.001, 45.999), 4: (29.001, 46.001)},
    )
    graph = GRAPH_MODULE.Graph(payload)
    assert graph.route_km((29.0, 46.0), (29.001, 46.001)) is None


def test_rail_crossing_requires_a_shared_osm_node():
    disconnected = graph_payload(
        phys=[(1, 2, 100.0, 10), (3, 4, 100.0, 20)],
        edges=[(1, 2, 100.0, 10, 0), (2, 1, 100.0, 10, 0),
               (3, 4, 100.0, 20, 1), (4, 3, 100.0, 20, 1)],
        phys_dirs=[[0, 1], [2, 3]],
        node_out={1: [0], 2: [1], 3: [2], 4: [3]},
        coords={1: (29.0, 46.0), 2: (29.001, 46.0),
                3: (29.0011, 46.0), 4: (29.002, 46.0)},
    )
    assert GRAPH_MODULE.Graph(disconnected).route_km(
        (29.0, 46.0), (29.002, 46.0)
    ) is None

    connected = graph_payload(
        phys=[(1, 2, 100.0, 10), (2, 3, 100.0, 20)],
        edges=[(1, 2, 100.0, 10, 0), (2, 1, 100.0, 10, 0),
               (2, 3, 100.0, 20, 1), (3, 2, 100.0, 20, 1)],
        phys_dirs=[[0, 1], [2, 3]],
        node_out={1: [0], 2: [1, 2], 3: [3]},
        coords={1: (29.0, 46.0), 2: (29.001, 46.0), 3: (29.002, 46.0)},
    )
    assert GRAPH_MODULE.Graph(connected).route_km(
        (29.0, 46.0), (29.002, 46.0)
    ) is not None


def test_oneway_is_respected_by_route_search():
    payload = graph_payload(
        phys=[(1, 2, 100.0, 10)],
        edges=[(1, 2, 100.0, 10, 0)],
        phys_dirs=[[0]],
        node_out={1: [0]},
        coords={1: (29.0, 46.0), 2: (29.001, 46.0)},
    )
    graph = GRAPH_MODULE.Graph(payload)
    assert graph.route_km((29.0, 46.0), (29.001, 46.0)) is not None
    assert graph.route_km((29.001, 46.0), (29.0, 46.0)) is None


def test_endpoint_only_access_is_not_a_transit_shortcut():
    payload = graph_payload(
        phys=[(1, 2, 100.0, 10), (2, 3, 100.0, 20), (3, 4, 100.0, 30)],
        edges=[(1, 2, 100.0, 10, 0), (2, 1, 100.0, 10, 0),
               (2, 3, 100.0, 20, 1), (3, 2, 100.0, 20, 1),
               (3, 4, 100.0, 30, 2), (4, 3, 100.0, 30, 2)],
        phys_dirs=[[0, 1], [2, 3], [4, 5]],
        node_out={1: [0], 2: [1, 2], 3: [3, 4], 4: [5]},
        coords={1: (29.0, 46.0), 2: (29.001, 46.0),
                3: (29.002, 46.0), 4: (29.003, 46.0)},
        classes=["public", "endpoint_only", "public"],
    )
    payload["phys_component"] = {1: 1}
    graph = GRAPH_MODULE.Graph(payload)
    assert graph.route_km((29.0, 46.0), (29.003, 46.0)) is None


def test_evaluator_contains_no_per_control_override_or_street_name_hack():
    source = (REPO / "scripts/evaluate_router_against_manual_yandex.py").read_text("utf-8")
    assert "MY-" not in source
    assert "control_id ==" not in source
    assert "street_override" not in source


def test_completed_manual_yandex_measurements_are_immutable():
    EVALUATOR.assert_golden_inputs()


def test_zone_address_pricing_graph_and_profile_inputs_are_unchanged():
    for relative, expected in PROTECTED_HASHES.items():
        assert normalized_hash(REPO / relative) == expected, relative


def test_immutable_releases_are_unchanged():
    assert releases_hash() == RELEASES_HASH


def test_baseline_is_write_once(tmp_path):
    output = tmp_path / "baseline.csv"
    output.write_text("already exists\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        EVALUATOR.write_csv_once(output, [])


def test_before_after_outputs_are_reproducible_and_regression_free():
    before = rows("router-baseline-v1.csv")
    after = rows("router-after-repair-v1.csv")
    assert before == after
    before_metrics = EVALUATOR.metrics(before)
    after_metrics = EVALUATOR.metrics(after)
    assert after_metrics["gt10"] <= before_metrics["gt10"]
    assert after_metrics["median"] <= before_metrics["median"]
    assert after_metrics["unreachable"] <= before_metrics["unreachable"]


def test_repair_actions_use_only_allowed_dispositions():
    actions = rows("router-repair-actions-v1.csv")
    allowed = {
        "IMPLEMENTED",
        "REJECTED_UNSAFE",
        "ADDRESS_REVIEW_REQUIRED",
        "OWNER_DECISION_REQUIRED",
        "NO_GRAPH_DEFECT_FOUND",
    }
    assert actions
    assert {row["status"] for row in actions} <= allowed
    assert all(row["implemented_change"] == "none" for row in actions)
