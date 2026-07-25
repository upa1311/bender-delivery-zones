"""Stage 09 engine unit tests — geometry math + provisional cost, no network."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from stage09_engine import (  # noqa: E402
    ORIGINS,
    OUTSIDE_MULTIPLIER,
    equivalent_city_km,
    haversine_km,
    line_km,
    nearest_osm_place,
    segment_in_out_city,
)


def test_outside_multiplier_is_10_over_6():
    assert abs(OUTSIDE_MULTIPLIER - (10 / 6)) < 1e-9


def test_equivalent_city_km_upweights_outside_km():
    # 2 km in-city + 2 km outside -> 2 + 2*1.6667 = 5.3333
    assert abs(equivalent_city_km(2.0, 2.0) - (2 + 2 * (10 / 6))) < 1e-3
    # pure in-city is unchanged
    assert equivalent_city_km(3.0, 0.0) == 3.0


def test_haversine_and_line_km():
    # ~1.11 km per 0.01 deg latitude
    d = haversine_km(46.82, 29.48, 46.83, 29.48)
    assert 1.0 < d < 1.2
    assert abs(line_km([[29.48, 46.82], [29.48, 46.83]]) - d) < 1e-6


def test_origins_weights_sum_to_one():
    assert abs(sum(o["weight"] for o in ORIGINS) - 1.0) < 1e-9


def test_segment_split_uses_boundary():
    from shapely.geometry import Polygon

    # square "city"; a DENSE line (as real OSRM geometry is) crossing the east
    # edge — split is by each segment's midpoint, so vertices must be close.
    city = Polygon([(29.0, 46.0), (29.01, 46.0), (29.01, 46.01), (29.0, 46.01)])
    line = [
        [29.002, 46.005], [29.005, 46.005], [29.008, 46.005],
        [29.0105, 46.005], [29.015, 46.005], [29.02, 46.005],
    ]
    seg = segment_in_out_city(line, city)
    assert seg["in_city_km"] > 0
    assert seg["outside_city_km"] > 0
    assert seg["crosses_boundary"] is True


def test_nearest_osm_place_returns_known_district():
    name, km = nearest_osm_place(46.839237, 29.465056)  # Borisovka node
    assert name == "Борисовка"
    assert km < 0.05
