#!/usr/bin/env bash
# Build the Lambda bundle for the backend (task 5.3).
#
#   scripts/build_backend.sh            -> backend/build/lambda/
#
# Python 3.12 on arm64 (Graviton, cheaper per GB-second). Dependencies are installed as Linux
# arm64 wheels with uv, so no Docker is needed. boto3 comes with the Lambda runtime and is
# not bundled. Only runtime code and the two data files are copied: no tests, no .venv, no .env.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/backend/build/lambda"
PY_VERSION="3.12"
PLATFORM="aarch64-manylinux2014"

rm -rf "$OUT"
mkdir -p "$OUT/backend" "$OUT/data"

uv pip install --quiet \
  --target "$OUT" \
  --python-version "$PY_VERSION" \
  --python-platform "$PLATFORM" \
  --only-binary :all: \
  aws-lambda-powertools jsonschema defusedxml

cp "$ROOT/backend/__init__.py" "$OUT/backend/__init__.py"
rsync -a --exclude '__pycache__' --exclude '*.pyc' "$ROOT/backend/src/" "$OUT/backend/src/"
cp "$ROOT/data/case_studies.json" "$OUT/data/"

# Remove what Lambda does not need.
find "$OUT" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "$OUT" -mindepth 2 -type d -name 'tests' -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf "$OUT/bin"

echo "Built $(du -sh "$OUT" | cut -f1) Lambda bundle in ${OUT#$ROOT/}"
