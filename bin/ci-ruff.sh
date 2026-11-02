#!/usr/bin/env bash
# Lint and format-check all the Python in the repository with ruff.
#
# One ruff.toml at the root covers every project, its tests and its scripts; it extends the shared
# base, .devtools/config/ruff.toml. CI runs this with the runner's ruff on PATH, and a local run
# names the virtualenv's through RUFF.
#
# Usage: .devtools/bin/ci-ruff.sh    (from the repository root)
#   RUFF   the ruff command (default: ruff)
set -euo pipefail

ruff="${RUFF:-ruff}"
"$ruff" check .
"$ruff" format --check .
