#!/usr/bin/env bash
# Run the bats suites, for the shell coverage measurement.
#
# The `command` of the shell suite in coverage.toml: jmerhar/coverage's run-kcov.sh runs it with
# COVERAGE_DIR set, locally or in the kcov container, and test/test_helper.bash applies kcov to
# each script the suites run.
#
# Usage: tooling/measure.sh
#   JUNIT_DIR   also write bats's JUnit report there, for Codecov's test analytics
set -euo pipefail

cd "$(dirname "$0")/.."
report=()
if [ -n "${JUNIT_DIR:-}" ]; then
  mkdir -p "$JUNIT_DIR"
  report=(--report-formatter junit --output "$JUNIT_DIR")
fi
bats "${report[@]}" test/
