#!/usr/bin/env bash
# Run every suite once, without measuring coverage: the bats suites, then pytest.
#
# Called by `make test`. Arguments pass through to pytest.
set -euo pipefail

cd "$(dirname "$0")/.."

python="${PYTHON:-.venv/bin/python}"
bats test/
"$python" -m pytest -q -p no:cacheprovider test/python "$@"
