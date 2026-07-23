"""Deterministic JSON serialization helpers.

Every JSON artifact this toolkit writes (manifests, audit reports) goes through
:func:`dumps` so that re-running with identical inputs produces byte-identical
output. Determinism is guaranteed by ``sort_keys=True`` plus a fixed indent and
a trailing newline.
"""

from __future__ import annotations

import json
from typing import Any


def dumps(obj: Any) -> str:
    """Serialize *obj* to a deterministic, human-readable JSON string.

    Keys are sorted, non-ASCII characters are preserved (Cyrillic street names
    stay readable), and the output ends with a single trailing newline.
    """
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write(path, obj) -> None:
    """Write *obj* as deterministic JSON to *path* (UTF-8, LF newlines)."""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(dumps(obj))
