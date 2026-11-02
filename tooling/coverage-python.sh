#!/usr/bin/env bash
# Run the pytest suite under coverage.py and write the reports coverage.toml's python suite reads.
#
# Called by `make coverage` and by CI, so both measure the same way. The shell suite is measured
# separately, under kcov, by jmerhar/coverage's run-kcov.sh.
#
#   PYTHON      the interpreter with pytest and coverage installed (default: .venv/bin/python)
#   JUNIT_DIR   also write a JUnit report there, for Codecov's test analytics
set -euo pipefail

cd "$(dirname "$0")/.."

python="${PYTHON:-.venv/bin/python}"
junit=()
[ -n "${JUNIT_DIR:-}" ] && junit=(--junitxml="$JUNIT_DIR/python.xml")

rm -rf coverage/python .coverage
"$python" -m coverage run --include='bin/*.py' -m pytest -q -p no:cacheprovider "${junit[@]}" test/python
"$python" -m coverage json -q -o coverage/python/coverage.json
"$python" -m coverage html -q -d coverage/python/htmlcov
"$python" -m coverage xml -q -o coverage/python/coverage.xml
"$python" -m coverage report --precision=1
