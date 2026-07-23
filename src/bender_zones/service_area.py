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

    Priority: ``name:ru`` -> ``official_name:ru`` -> ``alt_name:ru`` -> verified
    local table (keyed by original ``name``) -> otherwise no confirmed RU name.

    Returns ``(display, source, status)``. When no confirmed Russian name exists
    the display falls back to the original ``name`` (shown as-is, never
    transliterated) and the status is ``needs_ru_review``.
    """
    local_table = local_table or {}
    for key in RU_TAG_PRIORITY:
        value = tags.get(key)
        if value and value.strip():
            return value.strip(), key, STATUS_OK

    original = (tags.get("name") or "").strip()
    if original and original in local_table:
        override = local_table[original].strip()
        if override:
            return override, "local_table", STATUS_OK

    return original, "none", STATUS_NEEDS_REVIEW


def street_record(osm_type: str, osm_id: int, tags: dict, settlement_key: str,
                  local_table: dict[str, str] | None = None) -> dict:
    """Build one street record with resolved RU name and all preserved fields."""
    display, source, status = resolve_ru_name(tags, local_table)
    record = {
        "osm_type": osm_type,
        "osm_id": osm_id,
        "settlement": settlement_key,
        "ru_display": display,
        "ru_source": source,
        "ru_status": status,
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
