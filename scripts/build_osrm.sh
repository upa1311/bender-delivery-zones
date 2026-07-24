#!/usr/bin/env bash
# Deterministic local OSRM MLD build for the Bender delivery audit.
#
#   osrm-extract -p car.lua  ->  osrm-partition  ->  osrm-customize  ->  osrm-routed
#
# Records full provenance (OSRM version, binary + car.lua checksums, source PBF
# SHA-256, exact commands, timestamp) to reports/stage-06/osrm-build.json so the
# routing results can be reproduced and audited. Creates no tariffs and no
# Direct integration.
#
# Usage:  scripts/build_osrm.sh [--serve] [--smoke]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Repo-local by default so a clean clone works without an unknown $HOME install.
OSRM_HOME="${OSRM_HOME:-$REPO_ROOT/.osrm}"
OSRM_BIN="${OSRM_BIN:-$OSRM_HOME/bin}"
PROFILE="${OSRM_PROFILE:-$REPO_ROOT/vendor/osrm/profiles/car.lua}"
PBF="${PBF:-$REPO_ROOT/data/raw/moldova-latest.osm.pbf}"
WORK="$REPO_ROOT/data/interim/osrm"
PORT="${OSRM_PORT:-5000}"
BASENAME="moldova"

SERVE=0; SMOKE=0
for arg in "$@"; do
  case "$arg" in
    --serve) SERVE=1 ;;
    --smoke) SMOKE=1 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

command -v "$OSRM_BIN/osrm-extract.exe" >/dev/null 2>&1 || \
  command -v "$OSRM_BIN/osrm-extract" >/dev/null 2>&1 || {
    echo "error: OSRM binaries not found in $OSRM_BIN" >&2; exit 2; }

exe() { if [ -x "$OSRM_BIN/$1.exe" ]; then echo "$OSRM_BIN/$1.exe"; else echo "$OSRM_BIN/$1"; fi; }
sha() { python -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$1"; }

[ -f "$PBF" ] || { echo "error: source PBF not found: $PBF" >&2; exit 2; }

# A running server memory-maps the graph and would block a clean rebuild.
stop_routed() {
  if command -v taskkill >/dev/null 2>&1; then
    taskkill //F //IM osrm-routed.exe >/dev/null 2>&1 || true
  fi
  pkill -f "osrm-routed" >/dev/null 2>&1 || true
  sleep 2
}
stop_routed

mkdir -p "$WORK"
rm -f "$WORK/$BASENAME.osrm"* 2>/dev/null || true
cp -f "$PBF" "$WORK/$BASENAME.osm.pbf"

OSRM_VERSION="$("$(exe osrm-extract)" --version 2>&1 | head -1 | tr -d '\r')"
EXTRACT_SHA="$(sha "$(exe osrm-extract)")"
PROFILE_SHA="$(sha "$PROFILE")"
PBF_SHA="$(sha "$PBF")"
STARTED="$(python -c "import datetime;print(datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%dT%H:%M:%SZ'))")"

CMD_EXTRACT="osrm-extract -p car.lua $BASENAME.osm.pbf"
CMD_PARTITION="osrm-partition $BASENAME"
CMD_CUSTOMIZE="osrm-customize $BASENAME"
CMD_ROUTED="osrm-routed --algorithm mld --port $PORT --max-table-size 20000 $BASENAME.osrm"

echo "==> osrm-extract";   ( cd "$WORK" && "$(exe osrm-extract)"   -p "$PROFILE" "$BASENAME.osm.pbf" >/dev/null )
echo "==> osrm-partition"; ( cd "$WORK" && "$(exe osrm-partition)" "$BASENAME"   >/dev/null )
echo "==> osrm-customize"; ( cd "$WORK" && "$(exe osrm-customize)" "$BASENAME"   >/dev/null )

FINISHED="$(python -c "import datetime;print(datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%dT%H:%M:%SZ'))")"

if [ "$SERVE" = "1" ] || [ "$SMOKE" = "1" ]; then
  stop_routed
  ( cd "$WORK" && "$(exe osrm-routed)" --algorithm mld --port "$PORT" \
      --max-table-size 20000 "$BASENAME.osrm" >/tmp/osrm-routed.log 2>&1 & )
  for _ in $(seq 1 30); do
    sleep 1
    curl -sf "http://127.0.0.1:$PORT/route/v1/driving/29.4828,46.8242;29.4869,46.8206?overview=false" >/dev/null && break
  done
fi

SMOKE_JSON="null"
if [ "$SMOKE" = "1" ]; then
  echo "==> smoke test"
  SMOKE_JSON="$(cd "$REPO_ROOT" && python scripts/osrm_smoke.py --port "$PORT")"
fi

mkdir -p "$REPO_ROOT/reports/stage-06"
cd "$REPO_ROOT"
python - "reports/stage-06/osrm-build.json" <<PYEOF
import json, sys
doc = {
  "schema": "bender-osrm-build/1",
  "generated_at": "$FINISHED",
  "started_at": "$STARTED",
  "engine": {
    "name": "OSRM",
    "algorithm": "MLD",
    "version": "$OSRM_VERSION",
    "binary_sha256": "$EXTRACT_SHA",
    "binary_source": json.load(open("vendor/osrm/OSRM_PIN.json", encoding="utf-8"))["binaries"],
    "pin": json.load(open("vendor/osrm/OSRM_PIN.json", encoding="utf-8")),
    "container_image_digest": None,
  },
  "profile": {"path": "vendor/osrm/profiles/car.lua", "sha256": "$PROFILE_SHA", "vendored": True},
  "source_pbf": {"path": "data/raw/moldova-latest.osm.pbf", "sha256": "$PBF_SHA"},
  "commands": ["$CMD_EXTRACT", "$CMD_PARTITION", "$CMD_CUSTOMIZE", "$CMD_ROUTED"],
  "smoke_test": json.loads('''$SMOKE_JSON'''),
  "notes": [
    "Deterministic: same PBF + same car.lua + same OSRM version reproduce the graph.",
    "Creates no tariffs, no prices and no Direct integration.",
  ],
}
with open(sys.argv[1], "w", encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
print("wrote reports/stage-06/osrm-build.json")
PYEOF
