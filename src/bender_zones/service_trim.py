"""Housing-density trimming: derive a CANDIDATE working service area.

Stage 03. The source OSM administrative boundaries stay untouched and are kept
as a separate reference layer. Here we derive a *candidate* working area from
actual residential fabric:

* residential / addressed building footprints (buffered),
* relevant named residential streets (buffered),
* dissolved, small gaps closed, small isolated components dropped,
* clipped to the source boundary and to owner-named limit streets.

Explicitly NOT done here: no delivery zones, no tariffs, no routing, no merging
into one production polygon, no convex hull of an administrative polygon, and no
buffering of a whole settlement.

Every geometry helper works in a *local metric* plane (metres) so buffers are
real distances; callers project WGS84 -> metres via :func:`local_projection`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import split, transform, unary_union
from shapely.strtree import STRtree

# --- inclusion / exclusion reason vocabulary (kept in sync with the report) ---
REASON_DENSE = "dense_residential_buildings"
REASON_ADDRESSED = "addressed_buildings"
REASON_STREET = "residential_street"
REASON_ACCESS = "required_access_road"
REASON_OWNER = "owner_named_boundary"
INCLUSION_REASONS = (REASON_DENSE, REASON_ADDRESSED, REASON_STREET,
                     REASON_ACCESS, REASON_OWNER)

EXCL_FARMLAND = "farmland"
EXCL_FOREST_PARK = "forest_or_park"
EXCL_EMPTY = "empty_land"
EXCL_SPARSE = "sparse_buildings"
EXCL_OWNER_LIMIT = "outside_owner_named_limit"
EXCLUSION_REASONS = (EXCL_FARMLAND, EXCL_FOREST_PARK, EXCL_EMPTY,
                     EXCL_SPARSE, EXCL_OWNER_LIMIT)


@dataclass(frozen=True)
class TrimParams:
    """Tunable, config-driven trimming parameters (all distances in metres)."""

    building_buffer_m: float = 25.0
    street_buffer_m: float = 18.0
    closing_gap_m: float = 25.0
    street_building_radius_m: float = 60.0
    min_buildings_near_street: int = 6
    min_addressed_buildings_near_street: int = 3
    min_component_buildings: int = 5
    min_excluded_area_m2: float = 20000.0
    min_empty_land_area_m2: float = 50000.0
    simplify_tolerance_m: float = 2.0


# --- local metric projection ------------------------------------------------

@dataclass(frozen=True)
class LocalProjection:
    """Equirectangular local projection. Accurate to well under a metre at the
    scale of one settlement, which is all the 15-60 m buffers require."""

    lat0: float
    lon0: float

    @property
    def _mx(self) -> float:
        return 111320.0 * math.cos(math.radians(self.lat0))

    @property
    def _my(self) -> float:
        return 110540.0

    def to_m(self, lon: float, lat: float) -> tuple[float, float]:
        return ((lon - self.lon0) * self._mx, (lat - self.lat0) * self._my)

    def to_deg(self, x: float, y: float) -> tuple[float, float]:
        return (x / self._mx + self.lon0, y / self._my + self.lat0)


def local_projection(lat0: float, lon0: float) -> LocalProjection:
    return LocalProjection(lat0=lat0, lon0=lon0)


def to_metres(geom, proj: LocalProjection):
    return transform(lambda x, y, z=None: proj.to_m(x, y), geom)


def to_degrees(geom, proj: LocalProjection):
    return transform(lambda x, y, z=None: proj.to_deg(x, y), geom)


# --- street relevance -------------------------------------------------------

def street_is_relevant(buildings_near: int, addressed_near: int,
                       is_access_road: bool, params: TrimParams) -> tuple[bool, str | None]:
    """Decide whether a named street is delivery-relevant, with the reason.

    There is no traffic/popularity data, so relevance is proxied by residential
    fabric: enough buildings nearby, enough addressed buildings, or the street
    being a required access road to an included cluster. A short street with
    houses on it is kept -- length alone never disqualifies a street.
    """
    if buildings_near >= params.min_buildings_near_street:
        return True, REASON_DENSE
    if addressed_near >= params.min_addressed_buildings_near_street:
        return True, REASON_ADDRESSED
    if is_access_road:
        return True, REASON_ACCESS
    return False, None


# --- candidate geometry -----------------------------------------------------

def build_candidate_geometry(building_geoms, street_geoms, params: TrimParams):
    """Buffer + dissolve + close small gaps. All inputs already in metres.

    Never buffers a whole settlement: only building footprints and *relevant*
    street centrelines are buffered.
    """
    parts = []
    if building_geoms:
        parts.append(unary_union([g.buffer(params.building_buffer_m) for g in building_geoms]))
    if street_geoms:
        parts.append(unary_union([g.buffer(params.street_buffer_m) for g in street_geoms]))
    if not parts:
        return Polygon()
    geom = unary_union(parts)
    if params.closing_gap_m > 0:
        # Morphological closing: bridges narrow gaps between adjacent blocks
        # without inventing area between distant clusters.
        geom = geom.buffer(params.closing_gap_m).buffer(-params.closing_gap_m)
    return geom


def polygon_components(geom) -> list[Polygon]:
    """Split a (Multi)Polygon into its connected polygon components."""
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]


def points_within(polygon, points: list[Point]) -> list[Point]:
    """Points covered by *polygon* (STRtree-accelerated, order preserved)."""
    if not points or polygon.is_empty:
        return []
    tree = STRtree(points)
    idxs = sorted(int(i) for i in tree.query(polygon))
    return [points[i] for i in idxs if polygon.covers(points[i])]


def count_points_within(polygon, points: list[Point]) -> int:
    return len(points_within(polygon, points))


def drop_small_components(geom, building_points: list[Point], params: TrimParams):
    """Split into components; keep those with enough buildings.

    Returns ``(kept_geometry, sparse_components)`` where ``sparse_components`` is
    a list of ``(polygon, building_count)`` for isolated groups below the
    threshold. Those are never silently deleted -- callers publish them as the
    ``sparse_building_review`` QA layer.
    """
    kept, sparse = [], []
    for poly in polygon_components(geom):
        n = count_points_within(poly, building_points)
        if n >= params.min_component_buildings:
            kept.append(poly)
        else:
            sparse.append((poly, n))
    kept_geom = unary_union(kept) if kept else Polygon()
    return kept_geom, sparse


# --- owner-named limit streets ---------------------------------------------

def side_of_line(line: LineString, point: Point) -> float:
    """Signed side of *point* relative to the line's overall chord (+1/-1)."""
    (ax, ay), (bx, by) = line.coords[0], line.coords[-1]
    cross = (bx - ax) * (point.y - ay) - (by - ay) * (point.x - ax)
    return math.copysign(1.0, cross) if cross != 0 else 0.0


def extend_line(line: LineString, distance: float) -> LineString:
    """Extend a line at both ends so it fully crosses a polygon when splitting."""
    coords = list(line.coords)
    (x0, y0), (x1, y1) = coords[0], coords[1]
    d0 = math.hypot(x0 - x1, y0 - y1) or 1.0
    start = (x0 + (x0 - x1) / d0 * distance, y0 + (y0 - y1) / d0 * distance)
    (xa, ya), (xb, yb) = coords[-1], coords[-2]
    d1 = math.hypot(xa - xb, ya - yb) or 1.0
    end = (xa + (xa - xb) / d1 * distance, ya + (ya - yb) / d1 * distance)
    return LineString([start, *coords, end])


def clip_to_side(polygon, line: LineString, keep_point: Point,
                 extend_m: float = 10000.0):
    """Keep only the part of *polygon* on the same side of *line* as *keep_point*.

    Returns ``(geometry, applied)``. ``applied`` is False when the split could
    not be performed (the line does not divide the polygon) -- callers must then
    record a boundary question rather than silently pretending the owner's limit
    was enforced.
    """
    if polygon.is_empty or line.is_empty:
        return polygon, False
    extended = extend_line(line, extend_m)
    try:
        pieces = split(polygon, extended)
    except Exception:  # pragma: no cover - shapely split edge cases
        return polygon, False
    target = side_of_line(line, keep_point)
    if target == 0.0:
        return polygon, False
    kept = [g for g in pieces.geoms
            if isinstance(g, Polygon) and side_of_line(line, g.representative_point()) == target]
    if not kept or len(list(pieces.geoms)) < 2:
        return polygon, False
    return unary_union(kept), True


def clip_direction(polygon, boundary_geom, anchor: Point, direction: str):
    """Drop the part of *polygon* strictly beyond *anchor* in a compass direction.

    Used for the owner's "exclude the fields to the right of Kavkaz" style of
    instruction. Returns ``(geometry, removed_geometry)``.
    """
    minx, miny, maxx, maxy = boundary_geom.bounds
    pad = 1000.0
    if direction == "east":
        box = Polygon([(anchor.x, miny - pad), (maxx + pad, miny - pad),
                       (maxx + pad, maxy + pad), (anchor.x, maxy + pad)])
    elif direction == "west":
        box = Polygon([(minx - pad, miny - pad), (anchor.x, miny - pad),
                       (anchor.x, maxy + pad), (minx - pad, maxy + pad)])
    elif direction == "north":
        box = Polygon([(minx - pad, anchor.y), (maxx + pad, anchor.y),
                       (maxx + pad, maxy + pad), (minx - pad, maxy + pad)])
    else:  # south
        box = Polygon([(minx - pad, miny - pad), (maxx + pad, miny - pad),
                       (maxx + pad, anchor.y), (minx - pad, anchor.y)])
    removed = polygon.intersection(box)
    return polygon.difference(box), removed


# --- measurement ------------------------------------------------------------

def area_m2(geom) -> float:
    """Area in square metres (geometry must already be in the metric plane)."""
    return float(geom.area) if not geom.is_empty else 0.0


def reduction_pct(source_area: float, candidate_area: float) -> float:
    if source_area <= 0:
        return 0.0
    return round((1.0 - candidate_area / source_area) * 100.0, 2)
