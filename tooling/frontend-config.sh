#!/usr/bin/env bash
# Install @jmerhar/frontend-config's development dependencies when they are missing, then check
# its types, lint it with its own configuration, and run its tests with coverage.
#
# Called by `make check` and `make coverage`; CI runs the same steps as the frontend-config suite.
# The install goes through whatever registry this machine's npm reaches, never rewriting the
# lockfile.
set -euo pipefail

cd "$(dirname "$0")/../frontend-config"
if [ ! -d node_modules ] || [ package-lock.json -nt node_modules ]; then
  npm ci --no-audit --no-fund --registry="$(cd / && npm config get registry)"
fi
npm run check
npm run lint
npm run coverage
