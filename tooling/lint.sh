#!/usr/bin/env bash
# Lint everything: ShellCheck over the shell and the bats suites, ruff over the Python.
#
# Called by `make lint` and by CI. Uses the virtualenv's ruff locally and the runner's in CI, where
# RUFF names it.
set -euo pipefail

cd "$(dirname "$0")/.."

ruff="${RUFF:-.venv/bin/ruff}"
shopt -s nullglob
scripts=(bin/*.sh fetch/*.sh tooling/*.sh)
shellcheck "${scripts[@]}"
# The bats files are bash with bats's own syntax on top; -s bash checks the bash, and the helper
# is checked through the suites that load it.
shellcheck -s bash -x test/*.bats test/test_helper.bash
"$ruff" check .
"$ruff" format --check .
echo "lint passed"
