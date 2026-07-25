#!/usr/bin/env bash
# Rebuild the OSRM graph and emit its provenance manifest ATOMICALLY as part of
# the same run: source PBF SHA-256, profile SHA-256, the exact commands, OSRM
# version, timestamps and the SHA-256 of every .osrm output. The manifest is
# written to a temp file and moved into place only after customize succeeds, so a
# manifest can never describe a build that did not complete.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="${OSRM_HOME:-$REPO/.osrm}/bin"
PROFILE="${OSRM_PROFILE:-$REPO/vendor/osrm/profiles/car.lua}"
WORK="${1:-$REPO/data/interim/osrm}"
BASE="moldova"
OUT="$REPO/docs/data/stage10d-osrm-build-manifest.json"
sha() { python -c "import hashlib,sys;h=hashlib.sha256();f=open(sys.argv[1],'rb')
[h.update(c) for c in iter(lambda:f.read(1<<20),b'')];print(h.hexdigest())" "$1"; }

PBF_SHA="$(sha "$WORK/$BASE.osm.pbf")"
PROFILE_SHA="$(sha "$PROFILE")"
VERSION="$("$BIN/osrm-extract" --version 2>&1 | head -1 | tr -d '\r')"
T0="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
( cd "$WORK" && "$BIN/osrm-extract"   -p "$PROFILE" "$BASE.osm.pbf" )
( cd "$WORK" && "$BIN/osrm-partition" "$BASE" )
( cd "$WORK" && "$BIN/osrm-customize" "$BASE" )
T1="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

TMP="$(mktemp)"
{
  printf '{\n  "status": "VERIFIED_AT_BUILD_TIME",\n'
  printf '  "started_utc": "%s",\n  "finished_utc": "%s",\n' "$T0" "$T1"
  printf '  "source_pbf_sha256": "%s",\n' "$PBF_SHA"
  printf '  "profile": {"path": "%s", "sha256": "%s"},\n' "${PROFILE#$REPO/}" "$PROFILE_SHA"
  printf '  "osrm_version": "%s",\n' "$VERSION"
  printf '  "commands": ["osrm-extract -p car.lua %s.osm.pbf", "osrm-partition %s", "osrm-customize %s"],\n' "$BASE" "$BASE" "$BASE"
  printf '  "outputs": ['
  first=1
  for f in "$WORK/$BASE".osrm*; do
    [ $first -eq 1 ] || printf ','
    first=0
    printf '\n    {"name": "%s", "sha256": "%s", "bytes": %s}' \
      "$(basename "$f")" "$(sha "$f")" "$(stat -c%s "$f")"
  done
  printf '\n  ]\n}\n'
} > "$TMP"
mv -f "$TMP" "$OUT"
echo "==> atomic manifest written: ${OUT#$REPO/}"
