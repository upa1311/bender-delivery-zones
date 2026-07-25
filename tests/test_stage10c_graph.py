"""Stage 10C — edge-valid semantics: delivery access, barriers, turn restrictions."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from stage10c_graph import (  # noqa: E402
    EdgeGraph,
    access_decision,
    barrier_blocks,
    oneway_flags,
)

# --- access profile: a delivery van may use access=delivery ------------------

def test_delivery_access_is_allowed_for_a_delivery_vehicle():
    allowed, reason, _c = access_decision({"access": "delivery"})
    assert allowed is True and "delivery" in reason


def test_private_still_blocks_transit():
    assert access_decision({"access": "private"})[0] is False


def test_customers_still_blocks_transit():
    assert access_decision({"access": "customers"})[0] is False


def test_destination_is_allowed():
    assert access_decision({"access": "destination"})[0] is True


def test_most_specific_key_wins():
    # motorcar=yes beats access=private
    assert access_decision({"access": "private", "motorcar": "yes"})[0] is True


def test_conditional_access_is_flagged():
    assert access_decision({"access": "yes", "access:conditional": "no @ (22:00-06:00)"})[2] is True


# --- barrier nodes -----------------------------------------------------------

def test_bollard_blocks_by_default():
    assert barrier_blocks({"barrier": "bollard"}) is True


def test_gate_is_passable_unless_access_denies():
    assert barrier_blocks({"barrier": "gate"}) is False
    assert barrier_blocks({"barrier": "gate", "access": "private"}) is True


def test_bollard_reopened_by_explicit_access():
    assert barrier_blocks({"barrier": "bollard", "motor_vehicle": "yes"}) is False


def test_no_barrier_tag_never_blocks():
    assert barrier_blocks({"highway": "crossing"}) is False


# --- turn restrictions are ENFORCED, not merely counted ----------------------

def _payload(no_node=None, only_node=None, barriers=None):
    #  edge0: A(1)->B(2) way 10   edge1: B(2)->C(3) way 20   edge2: B(2)->D(4) way 30
    return {
        "edges": [(1, 2, 100.0, 10), (2, 3, 100.0, 20), (2, 4, 100.0, 30)],
        "node_out": {1: [0], 2: [1, 2]},
        "coords": {1: (29.0, 46.0), 2: (29.001, 46.0), 3: (29.002, 46.0), 4: (29.001, 46.001)},
        "way_tags": {10: {}, 20: {}, 30: {}},
        "barrier_nodes": barriers or set(),
        "no_node": no_node or {},
        "only_node": only_node or {},
        "via_way_restr": [],
        "conditional_ways": [],
        "provenance": {},
    }


def test_no_turn_restriction_forbids_that_movement():
    g = EdgeGraph(_payload(no_node={(10, 2): {20}}))
    assert g._turn_allowed(0, 1) is False   # way10 -> way20 banned at node 2
    assert g._turn_allowed(0, 2) is True    # way10 -> way30 still allowed


def test_only_turn_restriction_forbids_every_other_movement():
    g = EdgeGraph(_payload(only_node={(10, 2): 20}))
    assert g._turn_allowed(0, 1) is True    # the mandated continuation
    assert g._turn_allowed(0, 2) is False   # anything else is forbidden


def test_barrier_node_blocks_passage_through_it():
    g = EdgeGraph(_payload(barriers={2}))
    assert g._turn_allowed(0, 1) is False
    assert g._turn_allowed(0, 2) is False


def test_unrestricted_junction_allows_both_movements():
    g = EdgeGraph(_payload())
    assert g._turn_allowed(0, 1) is True
    assert g._turn_allowed(0, 2) is True


# --- edge snapping charges the partial edge length ---------------------------

def test_edge_snap_projects_onto_the_edge_and_reports_off_road():
    g = EdgeGraph(_payload())
    snap = g.snap_edge(29.0005, 46.0002)  # beside the middle of edge0
    assert snap["edge"] in (0, 1, 2)
    assert 0.0 <= snap["t"] <= 1.0
    assert snap["off_road_m"] > 0          # off-road distance kept separate
    assert snap["edge_len_m"] == 100.0


def test_oneway_from_tags_only():
    assert oneway_flags({"oneway": "yes"}) == (True, False)
    assert oneway_flags({"oneway": "-1"}) == (False, True)
    assert oneway_flags({"junction": "roundabout"}) == (True, False)
