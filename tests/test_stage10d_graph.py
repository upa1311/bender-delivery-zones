"""Stage 10D — bidirectional snapping, endpoint-aware access, ordered via-ways."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from stage10d_graph import Graph, access_class, barrier_blocks, oneway_flags  # noqa: E402

# A(1) --100m-- B(2) --100m-- C(3), all bidirectional, one way id each.
BASE = {
    "phys": [(1, 2, 100.0, 10, "public"), (2, 3, 100.0, 20, "public")],
    "edges": [(1, 2, 100.0, 10, 0), (2, 1, 100.0, 10, 0),
              (2, 3, 100.0, 20, 1), (3, 2, 100.0, 20, 1)],
    "phys_dirs": [[0, 1], [2, 3]],
    "node_out": {1: [0], 2: [1, 2], 3: [3]},
    "coords": {1: (29.0, 46.0), 2: (29.001, 46.0), 3: (29.002, 46.0)},
    "way_tags": {10: {}, 20: {}},
    "barriers": set(), "no_node": {}, "only_node": {}, "via_way": [],
    "phys_component": {}, "provenance": {},
}


def g(**over):
    p = {**BASE, **over}
    return Graph(p)


# --- 1-2: a bidirectional snap yields BOTH directed states ------------------

def test_bidirectional_snap_returns_both_directed_states():
    s = g().snap(29.0005, 46.0)          # middle of segment A-B
    assert s["phys"] == 0
    assert len(s["states"]) == 2          # both directions seeded
    costs = sorted(round(x["cost_to_head"]) for x in s["states"])
    assert costs == [50, 50]              # t·L toward A, (1-t)·L toward B


def test_partial_lengths_follow_the_projection():
    s = g().snap(29.00025, 46.0)          # 25 % along A->B
    costs = sorted(round(x["cost_to_head"]) for x in s["states"])
    assert costs == [25, 75]


def test_oneway_snap_keeps_only_the_legal_direction():
    one = g(edges=[(1, 2, 100.0, 10, 0), (2, 3, 100.0, 20, 1), (3, 2, 100.0, 20, 1)],
            phys_dirs=[[0], [1, 2]], node_out={1: [0], 2: [1], 3: [2]})
    s = one.snap(29.0005, 46.0)
    assert len(s["states"]) == 1


# --- 3: arrival from every legal direction, same-segment both orders --------

def test_same_segment_forward_and_backward():
    gr = g()
    a = gr.snap(29.00025, 46.0)
    b = gr.snap(29.00075, 46.0)
    assert round(gr.same_segment_distance(a, b)) == 50
    assert round(gr.same_segment_distance(b, a)) == 50   # reverse order also legal


def test_route_between_the_two_far_ends():
    r = g().route_km((29.0, 46.0), (29.002, 46.0))
    assert r is not None
    assert abs(r["distance_km"] - 0.2) < 0.02


def test_arrival_accepted_from_either_direction():
    gr = g()
    s = gr.snap(29.0, 46.0)
    best = gr.best_by_edge(gr.dijkstra(s, set()))
    assert gr.arrive(best, gr.snap(29.0015, 46.0)) is not None


# --- 6: endpoint-aware access ------------------------------------------------

def test_endpoint_only_segment_is_not_a_transit_shortcut():
    gr = g(phys=[(1, 2, 100.0, 10, "public"), (2, 3, 100.0, 20, "endpoint_only")],
           phys_component={1: 1})
    assert gr._edge_ok(2, set()) is False        # no transit through it
    assert gr._edge_ok(2, {1}) is True           # allowed when it is our endpoint


def test_public_segment_always_usable():
    assert g()._edge_ok(0, set()) is True


def test_access_class_mapping():
    assert access_class({"access": "delivery"}) == "endpoint_only"
    assert access_class({"access": "destination"}) == "endpoint_only"
    assert access_class({"access": "private"}) == "denied"
    assert access_class({"highway": "residential"}) == "public"
    assert access_class({"access": "private", "motorcar": "yes"}) == "public"


# --- 7: multiple from/to members --------------------------------------------

def test_multiple_to_members_are_all_banned():
    gr = g(no_node={(10, 2): {20, 30}})
    assert gr._turn_ok(0, 2) is False


def test_only_turn_permits_only_listed_to_ways():
    gr = g(only_node={(10, 2): {20}})
    assert gr._turn_ok(0, 2) is True
    gr2 = g(only_node={(10, 2): {30}})
    assert gr2._turn_ok(0, 2) is False


# --- 8-9: ordered via-way progress ------------------------------------------

VIA = [{"kind": "no_left_turn", "from": {10}, "to": {40}, "vias": [20, 30]}]


def test_via_way_progress_advances_in_order():
    gr = g(via_way=VIA)
    st, blocked = gr._via_next(None, 10, 20)
    assert st == (0, 0) and not blocked
    st2, blocked2 = gr._via_next(st, 20, 30)
    assert st2 == (0, 1) and not blocked2


def test_via_way_blocks_only_at_the_end_of_the_sequence():
    gr = g(via_way=VIA)
    # reaching `to` after only the FIRST via way is not the restricted movement
    st, _ = gr._via_next(None, 10, 20)
    _s, blocked_early = gr._via_next(st, 20, 40)
    assert blocked_early is False
    # after the FULL via sequence it is
    st2, _ = gr._via_next(st, 20, 30)
    _s2, blocked_end = gr._via_next(st2, 30, 40)
    assert blocked_end is True


def test_leaving_the_via_sequence_early_clears_the_restriction():
    gr = g(via_way=VIA)
    st, _ = gr._via_next(None, 10, 20)
    st2, blocked = gr._via_next(st, 20, 99)   # unrelated way
    assert st2 is None and blocked is False


def test_only_restriction_blocks_when_sequence_abandoned():
    gr = g(via_way=[{"kind": "only_straight_on", "from": {10}, "to": {40}, "vias": [20]}])
    st, _ = gr._via_next(None, 10, 20)
    _s, blocked = gr._via_next(st, 20, 99)
    assert blocked is True


# --- misc --------------------------------------------------------------------

def test_barrier_and_oneway_helpers():
    assert barrier_blocks({"barrier": "bollard"}) is True
    assert barrier_blocks({"barrier": "gate"}) is False
    assert oneway_flags({"oneway": "-1"}) == (False, True)
