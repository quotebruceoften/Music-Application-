#!/usr/bin/env bash
# Package the beat engine + its Python packages for one platform (serious_python 6).
# Usage: tool/prepare_python.sh Android|iOS|Windows|macOS|Linux
set -euo pipefail
PLATFORM="${1:-Android}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/mobile/python"
# serious_python 6 stages the packages and the app here; the Flutter build reads the same variables
export SERIOUS_PYTHON_SITE_PACKAGES="${SERIOUS_PYTHON_SITE_PACKAGES:-$ROOT/mobile/build/site-packages}"
export SERIOUS_PYTHON_APP="${SERIOUS_PYTHON_APP:-$ROOT/mobile/build/python-app}"

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
echo "Packages: $SERIOUS_PYTHON_SITE_PACKAGES"
echo "App:      $SERIOUS_PYTHON_APP"
ls "$SERIOUS_PYTHON_APP"
