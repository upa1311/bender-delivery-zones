#!/usr/bin/env python
"""Stage 10C — OSRM build manifest (source SHA, commands, hashes, versions).

Records the provenance of the OSRM graph that answers routing queries: the source
PBF SHA-256, the extract/partition/customize commands used to build it, the OSRM
binary version, the car-profile SHA-256, and the SHA-256 of every .osrm output.
Where a value is recorded from the EXISTING build rather than observed during a
fresh rebuild, it is labelled as such — nothing is presented as more than it is.

Read-only. No OSM edit, no immutable release, no Direct, no price, no zone.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OSRM_DIR = REPO / "data/interim/osrm"
RAW = REPO / "data/raw/moldova-latest.osm.pbf"
BUILD_SH = REPO / "scripts/build_osrm.sh"
BIN = REPO / ".osrm/bin/osrm-routed.exe"


def sha(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    version = None
    if BIN.exists():
        try:
            out = subprocess.run([str(BIN), "--version"], capture_output=True,
                                 text=True, timeout=30)
            version = (out.stdout or out.stderr).strip().splitlines()[:2]
        except (OSError, subprocess.SubprocessError):
            version = None

    profile = next((p for p in [REPO / "vendor/osrm/profiles/car.lua",
                                REPO / "vendor/osrm/car.lua"] if p.exists()), None)
    cmds = []
    if BUILD_SH.exists():
        for line in BUILD_SH.read_text("utf-8", errors="replace").splitlines():
            s = line.strip()
            if any(t in s for t in ("osrm-extract", "osrm-partition", "osrm-customize")):
                cmds.append(s)

    outputs = []
    for p in sorted(OSRM_DIR.glob("moldova.osrm*")):
        st = p.stat()
        outputs.append({"name": p.name, "bytes": st.st_size, "sha256": sha(p),
                        "mtime_utc": datetime.fromtimestamp(st.st_mtime, UTC)
                        .strftime("%Y-%m-%dT%H:%M:%SZ")})

    manifest = {
        "recorded_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "provenance_mode": "recorded from the EXISTING build (no destructive rebuild "
                           "was performed on the live graph)",
        "source_pbf": {"path": str(RAW.relative_to(REPO)), "sha256": sha(RAW),
                       "bytes": RAW.stat().st_size if RAW.exists() else 0},
        "osrm_version": version,
        "osrm_profile": {"path": str(profile.relative_to(REPO)) if profile else None,
                         "sha256": sha(profile) if profile else None},
        "build_commands_from_script": cmds,
        "outputs": outputs,
        "output_count": len(outputs),
        "owner_review_required": True,
    }
    out = REPO / "docs/data/stage10c-osrm-build-manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                   encoding="utf-8", newline="\n")
    print("source pbf sha256:", manifest["source_pbf"]["sha256"])
    print("osrm version:", version)
    print("profile:", manifest["osrm_profile"])
    print("outputs hashed:", len(outputs))
    for c in cmds:
        print("  cmd:", c[:110])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
