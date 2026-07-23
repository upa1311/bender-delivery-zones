"""Typed loaders for the YAML configuration files.

Config files are intentionally declarative and version-controlled:

* ``config/sources.yml``            — download sources
* ``config/boundary-candidates.yml`` — candidate relations to *inspect only*
* ``config/audit.yml``              — audit knobs (car highway values, dirs)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .errors import ConfigError


def _load_yaml(path: str | Path) -> dict:
    p = Path(path)
    if not p.is_file():
        raise ConfigError(f"config file not found: {p}")
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        raise ConfigError(f"invalid YAML in {p}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"expected a mapping at the top level of {p}")
    return data


@dataclass(frozen=True)
class SourceConfig:
    """One downloadable source described in ``sources.yml``."""

    name: str
    source_url: str
    destination: str
    user_agent: str
    info_url: str | None = None
    timeout_seconds: float = 60.0
    max_retries: int = 3


def load_sources(path: str | Path) -> dict[str, SourceConfig]:
    """Load all named sources from ``sources.yml``."""
    data = _load_yaml(path)
    sources = data.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise ConfigError(f"{path}: 'sources' must be a non-empty mapping")
    out: dict[str, SourceConfig] = {}
    for name, spec in sources.items():
        if not isinstance(spec, dict):
            raise ConfigError(f"{path}: source '{name}' must be a mapping")
        try:
            out[name] = SourceConfig(
                name=name,
                source_url=spec["source_url"],
                destination=spec["destination"],
                user_agent=spec["user_agent"],
                info_url=spec.get("info_url"),
                timeout_seconds=float(spec.get("timeout_seconds", 60.0)),
                max_retries=int(spec.get("max_retries", 3)),
            )
        except KeyError as exc:
            raise ConfigError(f"{path}: source '{name}' missing key {exc}") from exc
    return out


@dataclass(frozen=True)
class CandidateConfig:
    """One boundary relation to inspect. Never auto-selected."""

    id: int
    label: str
    note: str = ""
    expected: dict = field(default_factory=dict)


def load_candidates(path: str | Path) -> list[CandidateConfig]:
    """Load candidate boundary relations from ``boundary-candidates.yml``."""
    data = _load_yaml(path)
    raw = data.get("candidates")
    if not isinstance(raw, list) or not raw:
        raise ConfigError(f"{path}: 'candidates' must be a non-empty list")
    candidates: list[CandidateConfig] = []
    for item in raw:
        if not isinstance(item, dict) or "id" not in item:
            raise ConfigError(f"{path}: each candidate needs at least an 'id'")
        candidates.append(
            CandidateConfig(
                id=int(item["id"]),
                label=str(item.get("label", f"relation {item['id']}")),
                note=str(item.get("note", "")),
                expected=dict(item.get("expected", {})),
            )
        )
    return candidates


@dataclass(frozen=True)
class AuditConfig:
    """Knobs from ``audit.yml``."""

    car_highway_values: frozenset[str]
    osmium_strategy: str
    workdir: str
    report_dir: str


def load_audit(path: str | Path) -> AuditConfig:
    """Load audit configuration."""
    data = _load_yaml(path)
    car = data.get("car_highway_values")
    if not isinstance(car, list) or not car:
        raise ConfigError(f"{path}: 'car_highway_values' must be a non-empty list")
    extraction = data.get("extraction", {})
    return AuditConfig(
        car_highway_values=frozenset(str(v) for v in car),
        osmium_strategy=str(extraction.get("osmium_strategy", "smart")),
        workdir=str(extraction.get("workdir", "data/interim")),
        report_dir=str(data.get("report_dir", "reports/stage-01")),
    )
