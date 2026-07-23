"""Report the versions of the tools that produced an audit."""

from __future__ import annotations

import sys

from . import extract


def tool_versions() -> dict[str, str | None]:
    """Return Python / pyosmium / libosmium / osmium-tool versions."""
    import osmium.version as ov

    return {
        "python": sys.version.split()[0],
        "pyosmium": ov.pyosmium_release,
        "libosmium": ov.libosmium_version,
        "osmium_tool": extract.osmium_version(),
    }
