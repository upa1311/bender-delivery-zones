"""Preliminary address/road coverage metrics over an OSM file.

The metrics are computed by streaming a single OSM file with pyosmium. When
used as part of the boundary audit, that file is an *exact* city extract
produced by :mod:`bender_zones.extract` (never a bounding-box approximation).
The same function is also used directly in tests against a tiny fixture, where
the fixture itself plays the role of the extract.

Every counter is a raw coverage signal. None of them implies address coverage
is complete.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import osmium

from .normalize import address_key


@dataclass
class AddressMetrics:
    """Raw per-boundary coverage counters."""

    highway_ways: int = 0
    car_highway_ways: int = 0
    named_highway_ways: int = 0
    unique_road_names: int = 0
    buildings: int = 0
    buildings_with_housenumber: int = 0
    address_nodes: int = 0
    objects_with_addr_street: int = 0
    objects_with_addr_place: int = 0
    objects_with_name_ru: int = 0
    objects_with_name_ro: int = 0
    objects_with_alt_name: int = 0
    objects_with_old_name: int = 0
    address_objects_without_housenumber: int = 0
    housenumber_without_street_or_place: int = 0
    duplicate_address_groups: int = 0
    duplicate_address_objects: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def compute_metrics(osm_path: str | Path, car_highway_values) -> AddressMetrics:
    """Stream *osm_path* and return :class:`AddressMetrics`.

    Counting rules (deliberately simple and documented):

    * ``highway_ways``            — ways carrying any ``highway`` tag
    * ``car_highway_ways``        — subset whose ``highway`` value is in
                                    ``car_highway_values``
    * ``named_highway_ways``      — highway ways with a ``name`` tag
    * ``unique_road_names``       — distinct raw ``name`` values on highway ways
    * ``buildings``               — objects with a ``building`` tag
    * ``address_nodes``           — nodes with ``addr:housenumber`` that are not
                                    themselves buildings
    * ``address_objects_without_housenumber`` — objects with some ``addr:*`` tag
                                    but no ``addr:housenumber``
    * ``housenumber_without_street_or_place`` — objects with ``addr:housenumber``
                                    but neither ``addr:street`` nor ``addr:place``
    * duplicate counters use the conservative ``(addr:street, addr:housenumber)``
      normalized key from :mod:`bender_zones.normalize`.
    """
    car_values = set(car_highway_values)
    road_names: set[str] = set()
    address_pairs: dict[tuple[str, str], int] = {}
    m = AddressMetrics()

    for obj in osmium.FileProcessor(str(osm_path)):
        kind = obj.type_str()  # 'n', 'w', 'r'
        tags = obj.tags
        get = tags.get

        highway = get("highway")
        if kind == "w" and highway is not None:
            m.highway_ways += 1
            if highway in car_values:
                m.car_highway_ways += 1
            name = get("name")
            if name:
                m.named_highway_ways += 1
                road_names.add(name)

        is_building = get("building") is not None
        if is_building:
            m.buildings += 1
            if get("addr:housenumber") is not None:
                m.buildings_with_housenumber += 1

        housenumber = get("addr:housenumber")
        if kind == "n" and housenumber is not None and not is_building:
            m.address_nodes += 1

        if get("addr:street") is not None:
            m.objects_with_addr_street += 1
        if get("addr:place") is not None:
            m.objects_with_addr_place += 1
        if get("name:ru") is not None:
            m.objects_with_name_ru += 1
        if get("name:ro") is not None:
            m.objects_with_name_ro += 1
        if get("alt_name") is not None:
            m.objects_with_alt_name += 1
        if get("old_name") is not None:
            m.objects_with_old_name += 1

        has_addr = any(k.startswith("addr:") for k, _ in tags)
        if has_addr and housenumber is None:
            m.address_objects_without_housenumber += 1
        if (
            housenumber is not None
            and get("addr:street") is None
            and get("addr:place") is None
        ):
            m.housenumber_without_street_or_place += 1

        street = get("addr:street")
        if housenumber is not None and street is not None:
            key = address_key(street, housenumber)
            address_pairs[key] = address_pairs.get(key, 0) + 1

    m.unique_road_names = len(road_names)
    m.duplicate_address_groups = sum(1 for c in address_pairs.values() if c > 1)
    m.duplicate_address_objects = sum(c - 1 for c in address_pairs.values() if c > 1)
    return m
