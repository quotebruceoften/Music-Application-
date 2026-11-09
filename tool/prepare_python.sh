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

REQS="$(grep -vE '^\s*(#|$)' "$SRC/requirements.txt" | paste -sd, -)"
cd "$ROOT/mobile"
echo "Packaging engine for $PLATFORM with: $REQS"
dart run serious_python:main package python --platform "$PLATFORM" --requirements "$REQS"
ls -la app/
