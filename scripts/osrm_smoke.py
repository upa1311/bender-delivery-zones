#!/usr/bin/env python
"""Clean-rebuild smoke test for the local OSRM MLD graph.

Checks that a freshly built graph answers plausibly: a known city route, a
directional pair (one-ways / turn restrictions must make it asymmetric) and a
bridge crossing that is a real road distance rather than a false junction.
Prints a JSON verdict for scripts/build_osrm.sh to embed in the build record.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request

CHECKS = {
    "centre_to_parkany": ((29.48277, 46.82423), (29.5174, 46.8372), 2.0, 12.0),
    "centre_to_giska": ((29.48277, 46.82423), (29.4414, 46.7814), 3.0, 15.0),
}


def route(port, a, b):
    url = (f"http://127.0.0.1:{port}/route/v1/driving/"
           f"{a[0]},{a[1]};{b[0]},{b[1]}?overview=false")
    with urllib.request.urlopen(url, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("code") != "Ok" or not data.get("routes"):
        return None
    return data["routes"][0]["distance"] / 1000.0, data["routes"][0]["duration"] / 60.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5000)
    args = ap.parse_args()

    out, ok = {}, True
    for name, (a, b, lo, hi) in CHECKS.items():
        r = route(args.port, a, b)
        passed = bool(r and lo <= r[0] <= hi)
        ok &= passed
        out[name] = {"distance_km": round(r[0], 3) if r else None,
                     "duration_min": round(r[1], 2) if r else None,
                     "expected_km_range": [lo, hi], "passed": passed}

    fwd = route(args.port, (29.4828, 46.8242), (29.4869, 46.8206))
    rev = route(args.port, (29.4869, 46.8206), (29.4828, 46.8242))
    asym = bool(fwd and rev and abs(fwd[0] - rev[0]) > 0.001)
    ok &= asym
    out["directional"] = {"forward_km": round(fwd[0], 3) if fwd else None,
                          "reverse_km": round(rev[0], 3) if rev else None,
                          "passed": asym,
                          "why": "one-ways/turn restrictions must break symmetry"}

    br = route(args.port, (29.4732, 46.8360), (29.4600, 46.8365))
    br_ok = bool(br and br[0] > 0.9)
    ok &= br_ok
    out["bridge_crossing"] = {"distance_km": round(br[0], 3) if br else None,
                              "passed": br_ok,
                              "why": "crossing ways must not fuse into a false junction"}

    out["passed"] = bool(ok)
    print(json.dumps(out, ensure_ascii=False, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
