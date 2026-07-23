"""Service-area QA logic: settlement allowlist, RU name resolution, features.

This is Stage 02: a *data-QA* layer over the local OSM extract. It does NOT
create delivery zones, tariffs, routing graphs, or any production polygon. It:

* loads the fixed allowlist of four territories (Varnița is excluded);
* resolves a display Russian street name by a strict priority, never inventing
  or transliterating;
* builds settlement GeoJSON features from *real* OSM geometry, and — when a
  boundary is genuinely absent — emits a point marker with status
  ``boundary_missing`` instead of fabricating a buffer.

All functions here are pure and offline; the PBF-driven pipeline lives in
``scripts/build_service_area.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .errors import ConfigError

# Street tag fields we always preserve for review, in a fixed order.
STREET_FIELDS = ["name", "name:ru", "name:ro", "official_name", "alt_name", "old_name"]

# Russian-name resolution priority (confirmed OSM tags), highest first.
RU_TAG_PRIORITY = ["name:ru", "official_name:ru", "alt_name:ru"]

STATUS_OK = "ok"
STATUS_NEEDS_REVIEW = "needs_ru_review"
BOUNDARY_FOUND = "boundary_found"
BOUNDARY_MISSING = "boundary_missing"

# --- road classification vocabulary ----------------------------------------
# Intercity / through-roads: not addressable neighbourhood streets.
INTERCITY_HIGHWAY = frozenset({
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
})
# Ordinary addressable urban streets.
ADDRESS_HIGHWAY = frozenset({
    "residential", "living_street", "unclassified", "tertiary", "tertiary_link",
    "secondary", "secondary_link", "road", "pedestrian",
})
SERVICE_HIGHWAY = frozenset({"service"})
TRACK_HIGHWAY = frozenset({"track"})
PATH_HIGHWAY = frozenset({"footway", "path", "cycleway", "steps", "bridleway"})

# Tokens that mark a *named bridge structure* (its own feature, not an address street).
BRIDGE_NAME_TOKENS = ("мост", "podul", "bridge")
# Tokens that mark a genuine street name (used to rescue mis-tagged paths and to
# protect streets whose name merely contains a bridge word).
STREET_WORD_TOKENS = frozenset({
    "улица", "ул", "переулок", "пер", "бульвар", "бул", "проспект", "пр", "шоссе",
    "тупик", "площадь", "пл", "проезд", "аллея", "набережная",
    "strada", "str", "stradela", "stradă", "bulevardul", "soseaua", "șoseaua",
    "street", "road", "alley", "lane",
})

ROAD_CLASS_ADDRESS = "address_street"
ROAD_CLASS_INTERCITY = "intercity"
ROAD_CLASS_BRIDGE = "bridge"
ROAD_CLASS_SERVICE = "service"
ROAD_CLASS_TRACK = "track"
ROAD_CLASS_PATH = "path"
ROAD_CLASS_INFORMAL = "informal"
ROAD_CLASS_OTHER = "other"

_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def _name_tokens(name: str) -> list[str]:
    return _WORD_RE.findall(name.lower())


def _has_street_word(name: str) -> bool:
    return any(tok in STREET_WORD_TOKENS for tok in _name_tokens(name))


def _looks_informal(name: str) -> bool:
    """A placeholder/description rather than a street name.

    e.g. ``Горка (с ручником)`` (parenthetical note) or ``начало пути``
    (all-lowercase description).
    """
    text = name.strip()
    if "(" in text or ")" in text:
        return True
    if any(c.isalpha() for c in text) and text == text.lower():
        return True
    return False


def classify_road(tags: dict) -> tuple[str, bool, bool]:
    """Classify a named highway way.

    Returns ``(road_class, is_address_street, needs_name_classification_review)``.

    Only real neighbourhood streets get ``is_address_street=True`` and are counted
    in the ``unique_streets`` statistic. Intercity roads, named bridge structures,
    service/track ways, and informal placeholder names are excluded. Genuinely
    ambiguous cases (service/track/informal names, or a street word on a path)
    set the review flag so a human can reclassify — they are never silently
    turned into address streets except when the evidence (a real street word) is
    strong, and even then the review flag is set.
    """
    name = (tags.get("name") or "").strip()
    highway = tags.get("highway") or ""
    lowered = name.lower()

    # Named bridge structures (but not streets that merely contain a bridge word).
    if any(tok in lowered for tok in BRIDGE_NAME_TOKENS) and not _has_street_word(name):
        return ROAD_CLASS_BRIDGE, False, False

    if highway in INTERCITY_HIGHWAY:
        return ROAD_CLASS_INTERCITY, False, False

    if _looks_informal(name):
        return ROAD_CLASS_INFORMAL, False, True

    if highway in SERVICE_HIGHWAY:
        return ROAD_CLASS_SERVICE, False, True
    if highway in TRACK_HIGHWAY:
        return ROAD_CLASS_TRACK, False, True

    if highway in PATH_HIGHWAY:
        if _has_street_word(name):
            # A real street name on a path-class way: keep it, but flag for review.
            return ROAD_CLASS_ADDRESS, True, True
        return ROAD_CLASS_PATH, False, False

    if highway in ADDRESS_HIGHWAY:
        return ROAD_CLASS_ADDRESS, True, False

    return ROAD_CLASS_OTHER, False, True


@dataclass(frozen=True)
class SettlementEntry:
    key: str
    display_ru: str
    osm_type: str
    osm_id: int
    place_node: int | None = None
    microdistricts_ru: tuple[str, ...] = ()


@dataclass(frozen=True)
class ServiceAreaConfig:
    allowed: tuple[SettlementEntry, ...]
    excluded: tuple[tuple[str, str], ...]  # (key, reason)
    tiles: dict
    start_view: dict

    def allowed_keys(self) -> frozenset[str]:
        return frozenset(s.key for s in self.allowed)

    def excluded_keys(self) -> frozenset[str]:
        return frozenset(k for k, _ in self.excluded)


def _load_yaml(path: str | Path) -> dict:
    p = Path(path)
    if not p.is_file():
        raise ConfigError(f"config file not found: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigError(f"expected a mapping at the top level of {p}")
    return data


def load_service_area(path: str | Path) -> ServiceAreaConfig:
    """Load and validate ``service-area.yml``."""
    data = _load_yaml(path)
    raw_allowed = data.get("allowed_settlements")
    if not isinstance(raw_allowed, list) or not raw_allowed:
        raise ConfigError(f"{path}: 'allowed_settlements' must be a non-empty list")

    allowed: list[SettlementEntry] = []
    for item in raw_allowed:
        try:
            allowed.append(
                SettlementEntry(
                    key=str(item["key"]),
                    display_ru=str(item["display_ru"]),
                    osm_type=str(item["osm_type"]),
                    osm_id=int(item["osm_id"]),
                    place_node=(int(item["place_node"]) if item.get("place_node") else None),
                    microdistricts_ru=tuple(item.get("microdistricts_ru", [])),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigError(f"{path}: invalid allowed settlement {item!r}: {exc}") from exc

    excluded = tuple(
        (str(e["key"]), str(e.get("reason", "")))
        for e in data.get("excluded_settlements", [])
    )
    excluded_keys = {k for k, _ in excluded}
    for entry in allowed:
        if entry.key in excluded_keys:
            raise ConfigError(f"{path}: '{entry.key}' is both allowed and excluded")

    return ServiceAreaConfig(
        allowed=tuple(allowed),
        excluded=excluded,
        tiles=dict(data.get("tiles", {})),
        start_view=dict(data.get("start_view", {})),
    )


def load_local_ru_table(path: str | Path) -> dict[str, str]:
    """Load the verified local RU street-name overrides (may be empty)."""
    data = _load_yaml(path)
    verified = data.get("verified") or {}
    if not isinstance(verified, dict):
        raise ConfigError(f"{path}: 'verified' must be a mapping")
    return {str(k): str(v) for k, v in verified.items()}


def resolve_ru_name(tags: dict, local_table: dict[str, str] | None = None) -> tuple[str, str, str]:
    """Resolve the display Russian street name.

    Priority:

    1. verified local override table (human-confirmed correction, authoritative);
    2. ``name:ru``;
    3. ``official_name:ru``;
    4. ``alt_name:ru``;
    5. otherwise: no confirmed Russian name.

    The verified table wins over OSM tags because it is a curated human
    correction (some OSM segments carry inconsistent or partial ``name:ru``). It
    is used only for names explicitly listed there; every other street keeps the
    OSM-tag priority. Returns ``(display, source, status)``. When no confirmed
    Russian name exists the display falls back to the original ``name`` (shown
    as-is, never transliterated) and the status is ``needs_ru_review``.
    """
    local_table = local_table or {}
    original = (tags.get("name") or "").strip()

    if original and original in local_table:
        override = local_table[original].strip()
        if override:
            return override, "local_table", STATUS_OK

    for key in RU_TAG_PRIORITY:
        value = tags.get(key)
        if value and value.strip():
            return value.strip(), key, STATUS_OK

    return original, "none", STATUS_NEEDS_REVIEW


def street_record(osm_type: str, osm_id: int, tags: dict, settlement_key: str,
                  local_table: dict[str, str] | None = None) -> dict:
    """Build one street record: resolved RU name, road class, preserved fields."""
    display, source, status = resolve_ru_name(tags, local_table)
    road_class, is_address_street, needs_class_review = classify_road(tags)
    record = {
        "osm_type": osm_type,
        "osm_id": osm_id,
        "settlement": settlement_key,
        "ru_display": display,
        "ru_source": source,
        "ru_status": status,
        "road_class": road_class,
        "is_address_street": is_address_street,
        "needs_name_classification_review": needs_class_review,
    }
    for field_name in STREET_FIELDS:
        record[field_name] = tags.get(field_name)
    return record


def _settlement_properties(entry: SettlementEntry, tags: dict, status: str) -> dict:
    props = {
        "key": entry.key,
        "display_ru": entry.display_ru,
        "osm_type": entry.osm_type,
        "osm_id": entry.osm_id,
        "status": status,
        "microdistricts_ru": list(entry.microdistricts_ru),
    }
    for field_name in ("name", "name:ru", "name:ro", "official_name", "alt_name", "old_name"):
        props[field_name] = tags.get(field_name)
    return props


def build_settlement_feature(entry: SettlementEntry, tags: dict, *,
                             geometry: dict | None,
                             marker_lonlat: tuple[float, float] | None = None) -> dict:
    """Build a settlement GeoJSON feature from REAL geometry, or a missing marker.

    If ``geometry`` is a Polygon/MultiPolygon dict, status is ``boundary_found``
    and that exact geometry is used. If ``geometry`` is ``None`` the boundary is
    genuinely absent: the feature is a **Point** marker (from the place node)
    with status ``boundary_missing``. No buffer/approximate polygon is ever
    synthesized for a missing boundary.
    """
    if geometry is not None:
        if geometry.get("type") not in ("Polygon", "MultiPolygon"):
            raise ValueError(f"settlement geometry must be a polygon, got {geometry.get('type')}")
        return {
            "type": "Feature",
            "properties": _settlement_properties(entry, tags, BOUNDARY_FOUND),
            "geometry": geometry,
        }

    props = _settlement_properties(entry, tags, BOUNDARY_MISSING)
    point = None
    if marker_lonlat is not None:
        point = {"type": "Point", "coordinates": [marker_lonlat[0], marker_lonlat[1]]}
    return {"type": "Feature", "properties": props, "geometry": point}


def round_coords(obj, ndigits: int = 5):
    """Recursively round all numeric coordinates for deterministic output."""
    if isinstance(obj, float):
        return round(obj, ndigits)
    if isinstance(obj, list):
        return [round_coords(x, ndigits) for x in obj]
    if isinstance(obj, dict):
        return {k: round_coords(v, ndigits) for k, v in obj.items()}
    return obj


@dataclass
class StreetStats:
    unique_streets: int = 0
    with_name_ru: int = 0
    needs_ru_review: int = 0
    fields: dict = field(default_factory=dict)
