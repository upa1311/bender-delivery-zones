"""Reproducible OpenStreetMap source-audit toolkit for the Bender delivery-zone project.

This package is a *pre-modeling* scaffold. It downloads and inspects an OSM
source extract and reports raw address/road coverage metrics for candidate
administrative boundaries. It deliberately does **not** select a working
boundary, build delivery zones, draw polygons, compute tariffs, or produce any
routing artifact. See ``README.md`` and ``docs/decisions/`` for scope.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
