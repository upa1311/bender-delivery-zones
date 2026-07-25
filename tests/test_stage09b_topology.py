"""Stage 09B — road/rail crossing classification unit tests (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from stage09b_topology import car_access_ok, classify_crossing  # noqa: E402


def _way(refs, **tags):
    return {"refs": refs, "tags": tags}


def test_shared_level_crossing_node_is_level_crossing():
    car = _way([1, 2, 3], highway="residential")
    rail = _way([9, 2, 8], railway="rail")  # shares node 2
    assert classify_crossing(car, rail, level_nodes={2}) == "LEVEL_CROSSING"


def test_shared_node_not_level_and_access_blocked_is_broken():
    car = _way([1, 2, 3], highway="service", access="private")
    rail = _way([9, 2, 8], railway="rail")
    assert classify_crossing(car, rail, level_nodes={2}) == "BROKEN_CONNECTIVITY"


def test_bridge_grade_separation_no_shared_node():
    car = _way([1, 2, 3], highway="primary", bridge="yes")
    rail = _way([7, 8, 9], railway="rail")  # no shared node
    assert classify_crossing(car, rail, level_nodes=set()) == "BRIDGE"


def test_geometry_only_when_no_shared_node_and_no_grade():
    car = _way([1, 2, 3], highway="residential")
    rail = _way([7, 8, 9], railway="rail")  # cross on the map only
    assert classify_crossing(car, rail, level_nodes=set()) == "GEOMETRY_ONLY_NO_CONNECTION"


def test_car_access_ok():
    assert car_access_ok({"highway": "residential"}) is True
    assert car_access_ok({"access": "private"}) is False
    assert car_access_ok({"motor_vehicle": "no"}) is False
