# shellcheck shell=bash disable=SC2016  # stub bodies are written literally, to expand when the stub runs
# Shared setup for the bats suites.
#
# Each test runs in a scratch repository under $BATS_TEST_TMPDIR, because every script acts on the
# current directory. run_script runs a script from this repository there, under kcov when
# $COVERAGE_DIR is set: tooling/measure.sh runs the suites that way for the coverage report, and
# kcov has to be applied per invocation because it collects nothing from a script bats runs in a
# grandchild process.

DEVTOOLS_ROOT="$(cd "$BATS_TEST_DIRNAME/.." && pwd)"
export DEVTOOLS_ROOT

# Creates the scratch repository and changes into it.
setup_repo() {
  REPO="$BATS_TEST_TMPDIR/repo"
  mkdir -p "$REPO"
  cd "$REPO" || return 1
}

# Runs a script from this repository with bats's `run`, traced by kcov when measuring.
# Arguments: the script's path relative to the repository root, then its arguments.
run_script() {
  local script="$DEVTOOLS_ROOT/$1"
  shift
  if [ -n "${COVERAGE_DIR:-}" ]; then
    # The Python in bin/ is measured by coverage.py; kcov would read it as bash that never ran.
    run kcov --include-path="$DEVTOOLS_ROOT/bin,$DEVTOOLS_ROOT/fetch" --exclude-pattern=.py \
      "$COVERAGE_DIR" "$script" "$@"
  else
    run "$script" "$@"
  fi
}

# Writes an executable stub that appends its arguments, one invocation per line, to $STUB_LOG and
# then runs the rest of its body.
# Arguments: the stub's path, then optional shell lines for its body.
make_stub() {
  local path="$1"
  shift
  mkdir -p "$(dirname "$path")"
  {
    printf '#!/usr/bin/env bash\n'
    printf 'echo "$(basename "$0") $*" >> "%s"\n' "$STUB_LOG"
    printf '%s\n' "$@"
  } > "$path"
  chmod +x "$path"
}
