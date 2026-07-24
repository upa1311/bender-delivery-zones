#!/usr/bin/env bash
# Fetch the PINNED OSRM release into ./.osrm so a clean clone needs no
# pre-existing $HOME installation. Reads vendor/osrm/OSRM_PIN.json.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${OSRM_HOME:-$REPO_ROOT/.osrm}"
PIN="$REPO_ROOT/vendor/osrm/OSRM_PIN.json"

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) KEY=win32-x64 ;;
  Darwin) KEY=darwin-arm64 ;;
  *) KEY=linux-x64 ;;
esac

URL="$(python -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8'))['binaries']['$KEY'])" "$PIN")"
VERSION="$(python -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8'))['version'])" "$PIN")"
echo "==> OSRM $VERSION ($KEY)"
echo "    $URL"

mkdir -p "$DEST/bin" "$DEST/tmp"
curl -sL -o "$DEST/tmp/osrm.tar.gz" "$URL"
tar -xzf "$DEST/tmp/osrm.tar.gz" -C "$DEST/tmp"
find "$DEST/tmp" -type f \( -name "osrm-*" -o -name "*.dll" \) -exec cp -f {} "$DEST/bin/" \;
rm -rf "$DEST/tmp"
chmod +x "$DEST"/bin/osrm-* 2>/dev/null || true
echo "==> installed into $DEST/bin"
ls "$DEST/bin" | head -10
