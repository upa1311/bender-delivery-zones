"""Stage 10B — graph semantics: oneway/access from TAGS, and a true Dijkstra."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from stage10b_graph import CarGraph, car_allowed, haversine_m, oneway_flags  # noqa: E402

# --- direction comes from tags, never from a distance difference -------------

def test_oneway_yes_is_forward_only():
    assert oneway_flags({"oneway": "yes"}) == (True, False)


def test_oneway_minus_one_is_backward_only():
    assert oneway_flags({"oneway": "-1"}) == (False, True)


def test_oneway_no_is_bidirectional():
    assert oneway_flags({"oneway": "no"}) == (True, True)


def test_roundabout_implies_oneway():
    assert oneway_flags({"junction": "roundabout"}) == (True, False)


def test_motor_vehicle_oneway_overrides_generic():
    assert oneway_flags({"oneway": "no", "oneway:motor_vehicle": "yes"}) == (True, False)


def test_untagged_street_is_bidirectional():
    assert oneway_flags({"highway": "residential"}) == (True, True)


# --- access from tags, most specific key wins --------------------------------

def test_private_access_blocks_cars():
    assert car_allowed({"access": "private"}) is False


def test_motor_vehicle_yes_overrides_private_access():
    assert car_allowed({"access": "private", "motor_vehicle": "yes"}) is True


def test_plain_residential_allows_cars():
    assert car_allowed({"highway": "residential"}) is True


# --- Dijkstra really returns the global distance minimum ---------------------

def _toy_graph():
    # 1 --100m-- 2 --100m-- 3   (upper path, 200 m total)
    #  \______________300m____/ (direct but longer)
    coords = {1: (29.0, 46.0), 2: (29.001, 46.0), 3: (29.002, 46.0)}
    adj = {
        1: [(2, 100.0, 10), (3, 300.0, 30)],
        2: [(1, 100.0, 10), (3, 100.0, 20)],
        3: [(2, 100.0, 20), (1, 300.0, 30)],
    }
    return CarGraph(coords, adj, {10: {}, 20: {}, 30: {}}, (28.9, 45.9, 29.1, 46.1), 0)


def test_dijkstra_picks_the_globally_shortest_not_the_direct_edge():
    g = _toy_graph()
    dist, pn, pw = g.dijkstra(1, targets={3})
    assert dist[3] == 200.0  # via node 2, not the 300 m direct edge
    p = g.path(1, 3, pn, pw)
    assert p["nodes"] == [1, 2, 3]
    assert p["way_ids"] == [10, 20]  # actual traversed OSM ways, in order


def test_path_reports_traversed_way_ids_in_order():
    g = _toy_graph()
    _d, pn, pw = g.dijkstra(1, targets={3})
    assert g.path(1, 3, pn, pw)["way_ids"] == [10, 20]


def test_haversine_is_metres():
    assert 1100 < haversine_m(46.82, 29.48, 46.83, 29.48) < 1200
