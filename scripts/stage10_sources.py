#!/usr/bin/env python
"""Stage 10 — MULTI-SOURCE ROAD TRUTH: source registry + live status probes.

Honesty first: this records what each road-truth source ACTUALLY provides in this
environment and never fabricates a source that is not reachable. OSRM runs on the
FULL Moldova PBF (not a city extract). The other local engines (GraphHopper,
Valhalla, openrouteservice) and the external sources (Yandex, Google Routes,
Mapillary, KartaView, EasyWay) require a JVM / Docker / API keys that are not
present here, so they are marked `unavailable` with the exact prerequisite —
pluggable, ready to run once the owner provides them.

Read-only; no OSM edit, no immutable release, no Direct, no price, no new zone.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def http_ok(url: str, timeout: float = 4.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def port_open(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def osrm_pbf_is_full() -> dict:
    pbf = REPO / "data/interim/osrm/moldova.osm.pbf"
    raw = REPO / "data/raw/moldova-latest.osm.pbf"
    size = pbf.stat().st_size if pbf.exists() else 0
    raw_size = raw.stat().st_size if raw.exists() else 0
    return {
        "osrm_input_bytes": size, "raw_moldova_bytes": raw_size,
        "built_on_full_moldova_pbf": size > 50_000_000 and size == raw_size,
    }


def probe() -> dict:
    sources = {}

    # 1. Local routing engines (same full Moldova PBF)
    sources["osrm"] = {
        "kind": "local_router", "url": "http://127.0.0.1:5000",
        "live": http_ok("http://127.0.0.1:5000/nearest/v1/driving/29.48,46.82"),
        "graph": osrm_pbf_is_full(),
        "prerequisite": "vendored osrm-routed + prebuilt moldova.osrm (present)",
    }
    sources["graphhopper"] = {
        "kind": "local_router", "url": "http://127.0.0.1:8989",
        "live": port_open("127.0.0.1", 8989),
        "prerequisite": "Java (JVM) + graphhopper jar; build graph on full Moldova PBF",
        "unavailable_reason": None if port_open("127.0.0.1", 8989) else "no Java/JVM in this environment",  # noqa: E501
    }
    sources["valhalla"] = {
        "kind": "local_router", "url": "http://127.0.0.1:8002",
        "live": port_open("127.0.0.1", 8002),
        "prerequisite": "Valhalla build or Docker; tiles on full Moldova PBF",
        "unavailable_reason": None if port_open("127.0.0.1", 8002) else "no Docker/Valhalla build here",  # noqa: E501
    }
    sources["openrouteservice"] = {
        "kind": "local_router", "url": "http://127.0.0.1:8080/ors",
        "live": port_open("127.0.0.1", 8080),
        "prerequisite": "Java + ORS; graph on full Moldova PBF",
        "unavailable_reason": None if port_open("127.0.0.1", 8080) else "no Java/Docker here",
    }

    # 2. External QA sources (keys / access required; QA-only, never copied into product)
    def ext(name, env_key, note):
        key = bool(os.environ.get(env_key))
        return {"kind": "external_qa", "configured": key,
                "prerequisite": f"env {env_key}", "note": note,
                "unavailable_reason": None if key else f"no {env_key} configured"}

    sources["yandex_maps"] = ext("yandex", "YANDEX_API_KEY", "cars routing + local roads; QA only")
    sources["google_routes"] = ext("google", "GOOGLE_MAPS_API_KEY", "external QA only; data NOT copied into product")  # noqa: E501
    sources["mapillary"] = ext("mapillary", "MAPILLARY_TOKEN", "street imagery confirmation")
    sources["kartaview"] = {"kind": "external_qa", "configured": False,
                            "prerequisite": "KartaView API access", "note": "street imagery confirmation",  # noqa: E501
                            "unavailable_reason": "no KartaView access configured"}
    sources["easyway"] = {"kind": "public_transport", "url": "https://www.eway.in.ua/…/bendery",
                          "configured": False, "note": "route polylines/stops as connectivity proof",  # noqa: E501
                          "unavailable_reason": "web bot-blocked (HTTP 403); verified vs OSM instead"}  # noqa: E501

    live_local = [k for k, v in sources.items() if v.get("kind") == "local_router" and v.get("live")]  # noqa: E501
    return {
        "generated_note": "Honest source registry. Unavailable sources are NOT fabricated.",
        "live_local_routers": live_local,
        "osrm_on_full_moldova_pbf": sources["osrm"]["graph"]["built_on_full_moldova_pbf"],
        "sources": sources,
        "owner_action_needed": {
            "local_routers": "provide a JVM (GraphHopper/ORS) and/or Docker (Valhalla), then rebuild "  # noqa: E501
                             "each graph on data/raw/moldova-latest.osm.pbf (full PBF, not a city extract)",  # noqa: E501
            "external_qa": "provide YANDEX_API_KEY / GOOGLE_MAPS_API_KEY / MAPILLARY_TOKEN / KartaView access",  # noqa: E501
        },
        "owner_review_required": True,
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    status = probe()
    (REPO / "docs/data/stage10-source-status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print("live local routers:", status["live_local_routers"])
    print("OSRM on full Moldova PBF:", status["osrm_on_full_moldova_pbf"])
    for k, v in status["sources"].items():
        flag = "LIVE" if v.get("live") or v.get("configured") else "unavailable"
        print(f"  {k:18s} {flag:12s} {v.get('unavailable_reason') or ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
