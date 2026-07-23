"""Residential delivery-demand classification (Stage 04).

Stage 03 wrongly treated every ``building=*`` object as delivery demand, which
counted sheds, garages, greenhouses, warehouses, industrial halls, ruins and
construction sites as customers. This module fixes that by classifying each
building and grading each street into a demand tier.

Nothing here creates zones, tariffs or routing. Tier C is explicitly excluded
from shaping candidate polygons, zone centres and standard tariffs.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- building classes -------------------------------------------------------
CONFIRMED_RESIDENTIAL = "confirmed_residential"
PROBABLE_RESIDENTIAL = "probable_residential"
NON_RESIDENTIAL = "non_residential"
OUTBUILDING = "outbuilding"
ABANDONED_OR_RUIN = "abandoned_or_ruin"
CONSTRUCTION = "construction"
UNKNOWN = "unknown"

BUILDING_CLASSES = (CONFIRMED_RESIDENTIAL, PROBABLE_RESIDENTIAL, NON_RESIDENTIAL,
                    OUTBUILDING, ABANDONED_OR_RUIN, CONSTRUCTION, UNKNOWN)

# Strong residential building values (owner-specified).
STRONG_RESIDENTIAL_VALUES = frozenset({
    "apartments", "house", "residential", "detached", "semidetached_house",
    "terrace", "dormitory", "bungalow",
})

# Apartment-style buildings: a single one is strong demand evidence.
APARTMENT_VALUES = frozenset({"apartments", "dormitory"})

# Never usable as demand anchors (owner-specified).
OUTBUILDING_VALUES = frozenset({
    "shed", "garage", "garages", "barn", "farm_auxiliary", "greenhouse",
    "carport", "hut", "cabin", "roof", "stable", "sty", "cowshed",
    "allotment_house", "shelter",
})

NON_RESIDENTIAL_VALUES = frozenset({
    "warehouse", "industrial", "commercial", "retail", "office", "school",
    "kindergarten", "college", "university", "hospital", "clinic", "church",
    "chapel", "synagogue", "mosque", "temple", "public", "civic", "government",
    "train_station", "transportation", "hangar", "kiosk", "service", "toilets",
    "fire_station", "sports_hall", "sports_centre", "stadium", "supermarket",
    "manufacture", "silo", "storage_tank", "water_tower", "bunker", "gatehouse",
    "military", "farm",
})

CONSTRUCTION_VALUES = frozenset({"construction"})
RUIN_VALUES = frozenset({"ruins", "ruin", "abandoned", "collapsed"})

# Weak evidence: shapes a dense block but never counts as one customer.
WEAK_RESIDENTIAL_VALUES = frozenset({"yes"})

# Classes that may shape candidate geometry (weak evidence included).
ANCHOR_CLASSES = frozenset({CONFIRMED_RESIDENTIAL, PROBABLE_RESIDENTIAL})
# Classes that may be counted as actual demand (customers).
CUSTOMER_CLASSES = frozenset({CONFIRMED_RESIDENTIAL})


def _has_lifecycle_prefix(tags: dict) -> bool:
    for key in tags:
        if key.startswith("abandoned:") or key.startswith("disused:"):
            return True
    return False


def classify_building(tags: dict) -> str:
    """Classify one OSM building object into a demand class.

    Order matters: life-cycle state (abandoned/disused/ruins/construction) wins
    over the building value, and explicit non-residential / outbuilding values
    win over any address, so an addressed warehouse never becomes demand.
    """
    value = tags.get("building")
    if value is None:
        return UNKNOWN

    if _has_lifecycle_prefix(tags):
        return ABANDONED_OR_RUIN
    for key in ("abandoned", "disused", "ruins"):
        raw = tags.get(key)
        if raw and raw != "no":
            return ABANDONED_OR_RUIN
    if value in RUIN_VALUES:
        return ABANDONED_OR_RUIN

    if value in CONSTRUCTION_VALUES or tags.get("construction"):
        return CONSTRUCTION
    if value in OUTBUILDING_VALUES:
        return OUTBUILDING
    if value in NON_RESIDENTIAL_VALUES:
        return NON_RESIDENTIAL
    if value in STRONG_RESIDENTIAL_VALUES:
        return CONFIRMED_RESIDENTIAL

    if value in WEAK_RESIDENTIAL_VALUES:
        # building=yes: an address makes it a confirmed residential address;
        # without one it is weak evidence that may only shape a dense block.
        if tags.get("addr:housenumber"):
            return CONFIRMED_RESIDENTIAL
        return PROBABLE_RESIDENTIAL

    return UNKNOWN


def is_apartment_building(tags: dict) -> bool:
    return (tags.get("building") in APARTMENT_VALUES
            and classify_building(tags) == CONFIRMED_RESIDENTIAL)


def is_demand_anchor(building_class: str) -> bool:
    """May this building shape the candidate polygon?"""
    return building_class in ANCHOR_CLASSES


def counts_as_customer(building_class: str) -> bool:
    """May this building be counted as actual delivery demand?"""
    return building_class in CUSTOMER_CLASSES


# --- demand tiers -----------------------------------------------------------

TIER_A = "A"
TIER_B = "B"
TIER_C = "C"

TIER_WEIGHT = {TIER_A: 1.0, TIER_B: 0.3, TIER_C: 0.0}
# Owner decision: Tier C fringe locations (1-2 isolated probable residences) are
# NOT serviceable. They are excluded from the service area, from zone centres,
# from K clustering and from distance percentiles, and get no surcharge and no
# manual-delivery option. They stay visible only as a QA layer.
TIER_SERVICE_STATUS = {
    TIER_A: "standard",
    TIER_B: "low_density",
    TIER_C: "no_delivery",
}


def is_serviceable(tier: str) -> bool:
    """Tier C is not served at all; A and B are."""
    return tier in (TIER_A, TIER_B)


@dataclass
class StreetDemand:
    """Per-street demand evidence gathered from the local OSM extract."""

    confirmed_addresses: int = 0
    confirmed_residential_buildings: int = 0
    probable_residential_buildings: int = 0
    apartment_buildings: int = 0
    nonresidential_buildings: int = 0
    outbuildings: int = 0
    abandoned_or_ruin: int = 0
    official_web_evidence: bool = False
    civic_or_commercial_pois: int = 0
    connected_to_core: bool = False

    @property
    def residential_evidence(self) -> int:
        """Buildings that are plausibly residential (confirmed + weak)."""
        return self.confirmed_residential_buildings + self.probable_residential_buildings


@dataclass(frozen=True)
class TierThresholds:
    tier_a_residential_buildings: int = 8
    tier_a_confirmed_addresses: int = 5
    tier_b_min_residential: int = 3
    tier_b_max_residential: int = 7
    tier_c_max_residential: int = 2


def assign_tier(demand: StreetDemand,
                thresholds: TierThresholds | None = None) -> tuple[str, str]:
    """Grade a street into demand tier A / B / C with a machine-readable reason.

    A — standard: >=8 plausibly residential buildings, or >=5 confirmed
        addresses, or an apartment building, or verified external (postal /
        election / owner) evidence, or an active civic/commercial POI.
    B — low density: 3-7 plausibly residential buildings AND connected to the core.
    C — manual/fringe: <=2 isolated probable residences, or uncertain /
        abandoned / disconnected evidence.
    """
    t = thresholds or TierThresholds()

    if demand.apartment_buildings >= 1:
        return TIER_A, "apartment_building"
    if demand.confirmed_addresses >= t.tier_a_confirmed_addresses:
        return TIER_A, f"confirmed_addresses>={t.tier_a_confirmed_addresses}"
    if demand.residential_evidence >= t.tier_a_residential_buildings:
        return TIER_A, f"residential_buildings>={t.tier_a_residential_buildings}"
    if demand.official_web_evidence:
        return TIER_A, "verified_external_evidence"
    if demand.civic_or_commercial_pois >= 1:
        return TIER_A, "active_civic_or_commercial_poi"

    if (t.tier_b_min_residential <= demand.residential_evidence <= t.tier_b_max_residential
            and demand.connected_to_core):
        return TIER_B, "low_density_connected_to_core"

    if demand.residential_evidence <= t.tier_c_max_residential:
        return TIER_C, "at_most_2_probable_residences"
    return TIER_C, "uncertain_or_disconnected_evidence"


def affects_zone_pricing(tier: str) -> bool:
    """Tier C never shapes polygons, zone centres or standard tariffs."""
    return tier in (TIER_A, TIER_B)


def service_status(tier: str) -> str:
    return TIER_SERVICE_STATUS.get(tier, "manual_review")


def tier_weight(tier: str) -> float:
    """Statistical weight: A full, B low, C none."""
    return TIER_WEIGHT.get(tier, 0.0)
