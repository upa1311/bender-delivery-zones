#!/usr/bin/env python
"""Verify the published OSRM provenance against the vendored, pinned profile.

Runs in CI without building the graph: it only checks that the results in the
repository were produced by the engine and profile the repository pins.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main() -> int:
    pin = json.loads((ROOT / "vendor/osrm/OSRM_PIN.json").read_text(encoding="utf-8"))
    rec = json.loads((ROOT / "reports/stage-06/osrm-build.json").read_text(encoding="utf-8"))
    errors = []

    for line in (ROOT / "vendor/osrm/CHECKSUMS.sha256").read_text(encoding="utf-8").splitlines():
        want, _, name = line.partition("  ")
        if not name:
            continue
        got = hashlib.sha256((ROOT / "vendor/osrm" / name).read_bytes()).hexdigest()
        if got != want:
            errors.append(f"vendored file changed without updating the checksum: {name}")

    if rec["engine"]["version"] != pin["version"]:
        errors.append(f"build record engine {rec['engine']['version']} != pin {pin['version']}")

    vendored = hashlib.sha256(
        (ROOT / "vendor/osrm/profiles/car.lua").read_bytes()).hexdigest()
    if rec["profile"]["sha256"] != vendored:
        errors.append("build record car.lua sha does not match the vendored profile")

    if not rec.get("smoke_test", {}).get("passed"):
        errors.append("the recorded clean-rebuild smoke test did not pass")

    joined = " ".join(rec["commands"])
    for step in ("osrm-extract", "osrm-partition", "osrm-customize", "osrm-routed"):
        if step not in joined:
            errors.append(f"build record is missing the {step} command")
    if "--algorithm mld" not in joined:
        errors.append("build record does not use the MLD algorithm")

    for platform in ("linux-x64", "win32-x64"):
        url = pin["binaries"].get(platform, "")
        if not url.startswith("https://github.com/Project-OSRM/osrm-backend/releases/download/"):
            errors.append(f"pin for {platform} is not an exact OSRM release URL")

    if errors:
        print("PROVENANCE FAILED:")
        for e in errors:
            print(" -", e)
        return 1
    print(f"OSRM provenance OK: {rec['engine']['version']} / car.lua {vendored[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
