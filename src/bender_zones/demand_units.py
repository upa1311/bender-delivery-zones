"""Unique delivery demand units identified by OSM id (Stage 06).

A *delivery unit* is a thing that can receive an order. It is identified by its
OSM type+id so it occurs exactly once:

* ``addressed_residential_building`` — residential building carrying an address;
* ``standalone_address_node``        — an ``addr:housenumber`` node that is NOT
  on/in a residential building;
* ``unaddressed_residential_building`` — residential building without an address,
  kept as LOWER-CONFIDENCE evidence.

An address node sitting on/in its building is merged into that building, so the
same doorway is never counted twice. Building counts are never reported as
"addresses".
"""

from __future__ import annotations

from dataclasses import dataclass

UNIT_ADDRESSED_BUILDING = "addressed_residential_building"
UNIT_ADDRESS_NODE = "standalone_address_node"
UNIT_UNADDRESSED_BUILDING = "unaddressed_residential_building"

UNIT_TYPES = (UNIT_ADDRESSED_BUILDING, UNIT_ADDRESS_NODE, UNIT_UNADDRESSED_BUILDING)

# Confidence multiplier applied to the demand weight.
UNIT_CONFIDENCE = {
    UNIT_ADDRESSED_BUILDING: 1.0,
    UNIT_ADDRESS_NODE: 1.0,
    UNIT_UNADDRESSED_BUILDING: 0.5,   # lower-confidence evidence
}


@dataclass
class DemandUnit:
    """One unique, addressable delivery target."""

    osm_type: str          # "n" | "w"
    osm_id: int
    unit_type: str
    point: object          # shapely Point in the metric plane
    lon: float = 0.0
    lat: float = 0.0
    street: str | None = None
    settlement: str | None = None
    housenumber: str | None = None
    tier: str | None = None

    @property
    def uid(self) -> str:
        return f"{self.osm_type}{self.osm_id}"

    @property
    def confidence(self) -> float:
        return UNIT_CONFIDENCE[self.unit_type]

    @property
    def is_address(self) -> bool:
        """True only for real addresses — never for a bare building footprint."""
        return self.unit_type in (UNIT_ADDRESSED_BUILDING, UNIT_ADDRESS_NODE)


def deduplicate_address_nodes(building_units, address_node_units, building_polys):
    """Drop address nodes that sit on/in one of *building_polys*.

    Returns ``(kept_address_nodes, merged_count)``. The building keeps the
    demand; the coincident node is a duplicate of the same doorway.
    """
    if not building_polys or not address_node_units:
        return list(address_node_units), 0
    from shapely.strtree import STRtree

    tree = STRtree(building_polys)
    kept, merged = [], 0
    for unit in address_node_units:
        hit = False
        for idx in tree.query(unit.point):
            if building_polys[int(idx)].covers(unit.point):
                hit = True
                break
        if hit:
            merged += 1
        else:
            kept.append(unit)
    return kept, merged


def reject_addresses_in_nonresidential(address_units, nonresidential_polys):
    """Drop address nodes that sit inside/on a confirmed NON-residential building.

    A warehouse, industrial hall, shop, garage, school or hospital may legally
    carry a house number, but that address is not a residential delivery unit.
    Returns ``(kept, rejected)`` where each rejected entry records the class of
    the building it fell inside.
    """
    if not address_units or not nonresidential_polys:
        return list(address_units), []
    from shapely.strtree import STRtree

    polys = [p for p, _cls in nonresidential_polys]
    classes = [cls for _p, cls in nonresidential_polys]
    tree = STRtree(polys)
    kept, rejected = [], []
    for unit in address_units:
        hit_cls = None
        for idx in tree.query(unit.point):
            i = int(idx)
            if polys[i].covers(unit.point):
                hit_cls = classes[i]
                break
        if hit_cls is None:
            kept.append(unit)
        else:
            rejected.append({"uid": unit.uid, "osm_type": unit.osm_type,
                             "osm_id": unit.osm_id, "lon": unit.lon, "lat": unit.lat,
                             "building_class": hit_cls,
                             "reason": "address_inside_nonresidential_building"})
    return kept, rejected


def unit_weight(unit: DemandUnit, tier_weight: float) -> float:
    """Demand weight = street tier weight x unit confidence."""
    return round(tier_weight * unit.confidence, 4)


def summarise(units) -> dict:
    """Counts per unit type, plus an address/building split that never conflates."""
    by_type = {t: 0 for t in UNIT_TYPES}
    for u in units:
        by_type[u.unit_type] += 1
    return {
        "unique_units": len(units),
        "by_type": by_type,
        "address_units": sum(1 for u in units if u.is_address),
        "residential_building_objects_without_address":
            by_type[UNIT_UNADDRESSED_BUILDING],
    }
