#!/usr/bin/env python
"""Stage 10B — prove the ACTIVE routing graph really is the full Moldova PBF.

Stage 10 only compared file sizes, which proves nothing. This proves it three
ways and records the evidence:

  1. SHA-256 of `data/raw/moldova-latest.osm.pbf` and of the PBF the OSRM graph
     was built from (`data/interim/osrm/moldova.osm.pbf`) — identical hash means
     the graph input IS the full download, not a re-cut extract.
  2. OSRM build metadata actually on disk: the `.osrm.*` file inventory, the
     timestamp/fingerprint files, and their sizes/mtimes.
  3. The COMMAND LINE of the live `osrm-routed` process (PID + argv), which shows
     exactly which `.osrm` dataset the answering server is serving.

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
RAW = REPO / "data/raw/moldova-latest.osm.pbf"
OSRM_INPUT = REPO / "data/interim/osrm/moldova.osm.pbf"
OSRM_DIR = REPO / "data/interim/osrm"


def sha256(path: Path, chunk: int = 1 << 20) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def osrm_routed_processes() -> list[dict]:
    """PID + full command line of every live osrm-routed process (Windows)."""
    ps = (
        "Get-CimInstance Win32_Process -Filter \"Name like 'osrm-routed%'\" | "
        "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=60,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return []
    if not out:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    return [{"pid": d.get("ProcessId"), "command_line": d.get("CommandLine")} for d in data]


def build_metadata() -> dict:
    files = []
    if OSRM_DIR.exists():
        for p in sorted(OSRM_DIR.glob("moldova.osrm*")):
            st = p.stat()
            files.append({
                "name": p.name, "bytes": st.st_size,
                "mtime_utc": datetime.fromtimestamp(st.st_mtime, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),  # noqa: E501
            })
    ts = OSRM_DIR / "moldova.osrm.timestamp"
    fp = OSRM_DIR / "moldova.osrm.fileIndex"
    return {
        "osrm_files": files,
        "osrm_file_count": len(files),
        "timestamp_file_text": ts.read_text("utf-8", errors="replace").strip()[:200] if ts.exists() else None,  # noqa: E501
        "has_fileindex": fp.exists(),
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    raw_hash = sha256(RAW)
    input_hash = sha256(OSRM_INPUT)
    procs = osrm_routed_processes()
    meta = build_metadata()

    serving = [p for p in procs if p.get("command_line") and "moldova.osrm" in p["command_line"]]
    proof = {
        "raw_moldova_pbf": {"path": str(RAW.relative_to(REPO)),
                            "bytes": RAW.stat().st_size if RAW.exists() else 0,
                            "sha256": raw_hash},
        "osrm_graph_input_pbf": {"path": str(OSRM_INPUT.relative_to(REPO)),
                                 "bytes": OSRM_INPUT.stat().st_size if OSRM_INPUT.exists() else 0,
                                 "sha256": input_hash},
        "input_sha256_equals_raw_sha256": bool(raw_hash and raw_hash == input_hash),
        "osrm_build_metadata": meta,
        "live_osrm_routed_processes": procs,
        "live_process_serves_moldova_osrm": bool(serving),
        "verdict": (
            "FULL_MOLDOVA_PBF_CONFIRMED"
            if (raw_hash and raw_hash == input_hash and serving and meta["osrm_file_count"] > 5)
            else "UNPROVEN"
        ),
        "method": "SHA-256 identity of the graph input vs the raw Geofabrik download, "
                  "on-disk .osrm build inventory, and the argv of the answering "
                  "osrm-routed process. File size alone is NOT used as proof.",
        "owner_review_required": True,
    }
    out = REPO / "docs/data/stage10b-graph-proof.json"
    out.write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print("raw    sha256:", raw_hash)
    print("input  sha256:", input_hash)
    print("identical    :", proof["input_sha256_equals_raw_sha256"])
    print("osrm files   :", meta["osrm_file_count"])
    for p in procs:
        print(f"pid {p['pid']}: {p['command_line']}")
    print("VERDICT:", proof["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
