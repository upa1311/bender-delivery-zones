"""Typed exceptions for the audit toolkit."""

from __future__ import annotations


class BenderZonesError(Exception):
    """Base class for all toolkit errors."""


class ConfigError(BenderZonesError):
    """Raised when a configuration file is missing or malformed."""


class MissingRelationError(BenderZonesError):
    """Raised when a required candidate relation is absent from the PBF."""


class ProvenanceError(BenderZonesError):
    """Raised when an existing file cannot be trusted against its manifest.

    Covers a missing manifest, or a SHA-256 mismatch between the file on disk
    and the manifest that claims to describe it. The caller is told to pass
    ``--force`` to deliberately re-download.
    """


class SpatialAuditUnavailableError(BenderZonesError):
    """Raised when an *exact* boundary extraction cannot be performed.

    This is raised instead of silently falling back to an inexact
    bounding-box approximation. See ``docs/decisions`` and the audit report
    limitations section.
    """
