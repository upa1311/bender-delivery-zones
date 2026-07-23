"""Metric aggregation over the minimal integration fixture."""

from __future__ import annotations

from bender_zones.config import load_audit
from bender_zones.metrics import compute_metrics

# From audit.yml; kept explicit so the test documents the classification.
CAR_VALUES = {"residential", "primary", "secondary", "tertiary", "service"}


def test_metrics_match_expected(mini_osm):
    m = compute_metrics(mini_osm, CAR_VALUES)

    assert m.highway_ways == 1
    assert m.car_highway_ways == 1  # residential
    assert m.named_highway_ways == 1
    assert m.unique_road_names == 1
    assert m.buildings == 1
    assert m.buildings_with_housenumber == 1
    # nodes 11, 12, 14 carry addr:housenumber and are not buildings
    assert m.address_nodes == 3
    # nodes 11, 12 and building way 21
    assert m.objects_with_addr_street == 3
    assert m.objects_with_addr_place == 1  # node 13
    # way 20 (name:ru) + node 11 (name:ru)
    assert m.objects_with_name_ru == 2
    assert m.objects_with_name_ro == 1  # way 20
    assert m.objects_with_alt_name == 1  # way 21
    assert m.objects_with_old_name == 1  # way 20
    assert m.address_objects_without_housenumber == 1  # node 13 (addr:place only)
    assert m.housenumber_without_street_or_place == 1  # node 14
    # nodes 11 & 12 normalize to the same (street, housenumber) pair
    assert m.duplicate_address_groups == 1
    assert m.duplicate_address_objects == 1


def test_metrics_serialize_to_plain_dict(mini_osm):
    m = compute_metrics(mini_osm, CAR_VALUES)
    d = m.to_dict()
    assert d["highway_ways"] == 1
    assert set(d) == set(vars(m))


def test_audit_config_car_values_load(repo_root):
    cfg = load_audit(repo_root / "config" / "audit.yml")
    assert "residential" in cfg.car_highway_values
    assert "footway" not in cfg.car_highway_values
