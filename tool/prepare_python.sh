#!/usr/bin/env bash
# Bundle the beat engine + Python packages into mobile/app/app.zip for one platform.
# Usage: tool/prepare_python.sh Android|iOS|Windows|macOS|Linux
set -euo pipefail
PLATFORM="${1:-Android}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/mobile/python"

rm -rf "$SRC/beatengine" "$SRC/server.py"
cp -r "$ROOT/beatengine" "$SRC/"
cp "$ROOT/server.py" "$SRC/"
find "$SRC" -name "__pycache__" -prune -exec rm -rf {} +

# serious_python takes one -r per requirement (it does not split on commas)
REQ_ARGS=()
while IFS= read -r line; do
  line="${line%%#*}"; line="$(echo "$line" | xargs)"
  if [ -n "$line" ]; then REQ_ARGS+=(-r "$line"); fi
done < "$SRC/requirements.txt"
cd "$ROOT/mobile"
echo "Packaging engine for $PLATFORM with: ${REQ_ARGS[*]}"
dart run serious_python:main package python --platform "$PLATFORM" "${REQ_ARGS[@]}"
ls -la app/
