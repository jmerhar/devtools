#!/usr/bin/env bats
# shellcheck disable=SC2016  # stub bodies are written literally, to expand when the stub runs
# fetch/devtools-fetch.sh, against file:// stand-ins for jmerhar/devtools and jmerhar/coverage.

load test_helper

setup() {
  setup_repo
  UPSTREAM="$BATS_TEST_TMPDIR/upstream"
  export DEVTOOLS_URL="file://$UPSTREAM/devtools"
  export COVERAGE_URL="file://$UPSTREAM/coverage"
  export DEVTOOLS_FETCH_RETRIES=0
  export STUB_LOG="$BATS_TEST_TMPDIR/calls"
  STUBS="$BATS_TEST_TMPDIR/stubs"
}

# Writes a curl stand-in with the given body; it logs its arguments to $STUB_LOG first.
stub_curl() {
  make_stub "$STUBS/curl" "$@"
}

# Fails if a temporary download was left behind anywhere under .devtools/.
no_partial_files() {
  [ -z "$(find .devtools -name '*.part*' 2>/dev/null)" ]
}

# Publishes a file in the stand-in for jmerhar/devtools at a ref.
# Arguments: ref, path, content.
publish() {
  mkdir -p "$(dirname "$UPSTREAM/devtools/$1/$2")"
  printf '%s\n' "$3" > "$UPSTREAM/devtools/$1/$2"
}

publish_coverage() {
  mkdir -p "$UPSTREAM/coverage"
  printf 'report\n' > "$UPSTREAM/coverage/coverage-report.py"
  printf 'kcov\n' > "$UPSTREAM/coverage/run-kcov.sh"
}

@test "fetches each listed file to its path under .devtools, with the config reader" {
  publish v1 make/devtools.mk "mk"
  publish v1 bin/ci-ruff.sh "ruff"
  publish v1 bin/devtools-config.py "reader"
  cat > devtools.toml <<'EOF'
[fetch]
ref = "v1"
files = ["make/devtools.mk", "bin/ci-ruff.sh"]
EOF
  run_script fetch/devtools-fetch.sh
  [ "$status" -eq 0 ]
  [ "$(cat .devtools/make/devtools.mk)" = "mk" ]
  [ "$(cat .devtools/bin/ci-ruff.sh)" = "ruff" ]
  [ "$(cat .devtools/bin/devtools-config.py)" = "reader" ]
  [[ "$output" == *"3 files current in .devtools/"* ]]
}

@test "makes fetched scripts executable and leaves other files alone" {
  publish v1 bin/ci-ruff.sh "ruff"
  publish v1 bin/devtools-config.py "reader"
  publish v1 config/ruff.toml "toml"
  printf '[fetch]\nref = "v1"\nfiles = ["bin/ci-ruff.sh", "config/ruff.toml"]\n' > devtools.toml
  run_script fetch/devtools-fetch.sh
  [ "$status" -eq 0 ]
  [ -x .devtools/bin/ci-ruff.sh ]
  [ -x .devtools/bin/devtools-config.py ]
  [ ! -x .devtools/config/ruff.toml ]
}

@test "fetches from the ref devtools.toml pins" {
  publish v1 bin/devtools-config.py "v1 reader"
  publish v1.2.0 bin/devtools-config.py "pinned reader"
  printf '[fetch]\nref = "v1.2.0"\nfiles = ["bin/devtools-config.py"]\n' > devtools.toml
  run_script fetch/devtools-fetch.sh
  [ "$status" -eq 0 ]
  [ "$(cat .devtools/bin/devtools-config.py)" = "pinned reader" ]
  [[ "$output" == *"1 files current"* ]]
}

@test "the directory ignores itself" {
  printf '[fetch]\n' > devtools.toml
  run_script fetch/devtools-fetch.sh
  [ "$status" -eq 0 ]
  [ "$(cat .devtools/.gitignore)" = "*" ]
  [[ "$output" == *"0 files current"* ]]
}

@test "fetches the coverage tooling side by side" {
  publish_coverage
  printf '[fetch]\ncoverage = true\n' > devtools.toml
  run_script fetch/devtools-fetch.sh
  [ "$status" -eq 0 ]
  [ "$(cat .devtools/coverage/coverage-report.py)" = "report" ]
  [ "$(cat .devtools/coverage/run-kcov.sh)" = "kcov" ]
  [ -x .devtools/coverage/run-kcov.sh ]
  [[ "$output" == *"2 files current"* ]]
}

@test "replaces the copy on disk, whatever its age" {
  publish v1 bin/devtools-config.py "new"
  mkdir -p .devtools/bin
  printf 'old\n' > .devtools/bin/devtools-config.py
  # Newer than the published file: v1 can move to an older commit.
  touch -t 203001010000 .devtools/bin/devtools-config.py
  printf '[fetch]\nref = "v1"\nfiles = ["bin/devtools-config.py"]\n' > devtools.toml
  run_script fetch/devtools-fetch.sh
  [ "$status" -eq 0 ]
  [ "$(cat .devtools/bin/devtools-config.py)" = "new" ]
  no_partial_files
}

@test "keeps the copy on disk, with a warning, when the network fails" {
  mkdir -p .devtools/bin
  printf 'kept\n' > .devtools/bin/devtools-config.py
  stub_curl 'exit 7'
  printf '[fetch]\nref = "v1"\nfiles = ["bin/devtools-config.py"]\n' > devtools.toml
  CURL="$STUBS/curl" run_script fetch/devtools-fetch.sh
  [ "$status" -eq 0 ]
  [ "$(cat .devtools/bin/devtools-config.py)" = "kept" ]
  [[ "$output" == *"warning: could not reach $DEVTOOLS_URL/v1/bin/devtools-config.py; using the copy"* ]]
  [[ "$output" == *"1 files in .devtools/, 1 of them kept from disk"* ]]
  no_partial_files
}

@test "an interrupted download leaves the copy on disk intact" {
  mkdir -p .devtools/bin
  printf 'kept\n' > .devtools/bin/devtools-config.py
  # Writes part of a file where -o points, then fails as a connection reset does.
  stub_curl 'while [ $# -gt 0 ]; do [ "$1" = -o ] && printf partial > "$2"; shift; done' 'exit 56'
  printf '[fetch]\nref = "v1"\nfiles = ["bin/devtools-config.py"]\n' > devtools.toml
  CURL="$STUBS/curl" run_script fetch/devtools-fetch.sh
  [ "$status" -eq 0 ]
  [ "$(cat .devtools/bin/devtools-config.py)" = "kept" ]
  [[ "$output" == *"warning: could not reach"* ]]
  no_partial_files
}

@test "fails when the network fails and there is no copy" {
  stub_curl 'exit 6'
  printf '[fetch]\nref = "v1"\nfiles = ["bin/devtools-config.py"]\n' > devtools.toml
  CURL="$STUBS/curl" run_script fetch/devtools-fetch.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"could not reach $DEVTOOLS_URL/v1/bin/devtools-config.py, and there is no copy"* ]]
  [[ "$output" == *"1 of 1 files failed"* ]]
}

@test "fails on a file the server does not have, even with a copy on disk" {
  mkdir -p .devtools/bin
  printf 'stale\n' > .devtools/bin/devtools-config.py
  printf '[fetch]\nref = "v9-typo"\nfiles = ["bin/devtools-config.py"]\n' > devtools.toml
  run_script fetch/devtools-fetch.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"could not fetch $DEVTOOLS_URL/v9-typo/bin/devtools-config.py (curl exit 37)"* ]]
  [ "$(cat .devtools/bin/devtools-config.py)" = "stale" ]
}

@test "treats an HTTP error as a failure rather than as being offline" {
  mkdir -p .devtools/bin
  printf 'stale\n' > .devtools/bin/devtools-config.py
  stub_curl 'exit 22'
  printf '[fetch]\nref = "v1"\nfiles = ["bin/devtools-config.py"]\n' > devtools.toml
  CURL="$STUBS/curl" run_script fetch/devtools-fetch.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"(curl exit 22)"* ]]
}

@test "tries every other file before failing, and backdates the makefile so make retries" {
  publish v1 make/devtools.mk "mk"
  publish v1 bin/devtools-config.py "reader"
  publish_coverage
  printf '[fetch]\nref = "v1"\nfiles = ["make/devtools.mk", "bin/missing.sh"]\ncoverage = true\n' > devtools.toml
  run_script fetch/devtools-fetch.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"could not fetch $DEVTOOLS_URL/v1/bin/missing.sh"* ]]
  [[ "$output" == *"1 of 5 files failed"* ]]
  [ "$(cat .devtools/bin/devtools-config.py)" = "reader" ]
  [ -f .devtools/coverage/run-kcov.sh ]
  [ ! -e .devtools/bin/missing.sh ]
  [ devtools.toml -nt .devtools/make/devtools.mk ]
}

@test "fails on an empty download" {
  mkdir -p "$UPSTREAM/devtools/v1/bin"
  : > "$UPSTREAM/devtools/v1/bin/devtools-config.py"
  printf '[fetch]\nref = "v1"\nfiles = ["bin/devtools-config.py"]\n' > devtools.toml
  run_script fetch/devtools-fetch.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"bin/devtools-config.py is empty"* ]]
  [ ! -e .devtools/bin/devtools-config.py ]
  no_partial_files
}

@test "fails when a fetched file cannot be moved into place" {
  publish v1 bin/devtools-config.py "reader"
  make_stub "$STUBS/mv" 'exit 1'
  printf '[fetch]\nref = "v1"\nfiles = ["bin/devtools-config.py"]\n' > devtools.toml
  PATH="$STUBS:$PATH" run_script fetch/devtools-fetch.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"1 of 1 files failed"* ]]
  [ ! -e .devtools/bin/devtools-config.py ]
  no_partial_files
}

@test "passes the retry count and the time limit to curl" {
  stub_curl 'exit 7'
  printf '[fetch]\nref = "v1"\nfiles = ["bin/devtools-config.py"]\n' > devtools.toml
  DEVTOOLS_FETCH_RETRIES=3 DEVTOOLS_FETCH_TIMEOUT=5 CURL="$STUBS/curl" run_script fetch/devtools-fetch.sh
  [[ "$(cat "$STUB_LOG")" == *"--max-time 5 --retry 3 "* ]]
}

@test "refuses a config dated in the future" {
  printf '[fetch]\n' > devtools.toml
  touch -t 203001010000 devtools.toml
  run_script fetch/devtools-fetch.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"devtools.toml is dated in the future"* ]]
}

@test "reads the config with a Python a module in the repository cannot hijack" {
  printf 'raise SystemExit("hijacked")\n' > tomllib.py
  printf '[fetch]\n' > devtools.toml
  run_script fetch/devtools-fetch.sh
  [ "$status" -eq 0 ]
  [[ "$output" != *"hijacked"* ]]
}

@test "refuses to run outside a repository root" {
  run_script fetch/devtools-fetch.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"no devtools.toml in $REPO; run this from the repository root"* ]]
  [ ! -e .devtools ]
}

@test "rejects a config that is not TOML" {
  printf '[fetch\n' > devtools.toml
  run_script fetch/devtools-fetch.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"devtools.toml is not valid TOML"* ]]
  [[ "$output" == *"cannot read devtools.toml"* ]]
}

@test "rejects a config without a [fetch] table" {
  printf '[compose]\nstacks = []\n' > devtools.toml
  run_script fetch/devtools-fetch.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"devtools.toml has no [fetch] table"* ]]
}

@test "rejects unknown keys in [fetch]" {
  printf '[fetch]\nref = "v1"\nfile = ["bin/dev.sh"]\n' > devtools.toml
  run_script fetch/devtools-fetch.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"[fetch] in devtools.toml has unknown keys: file"* ]]
}

@test "rejects files that are not a list of strings" {
  printf '[fetch]\nref = "v1"\nfiles = "bin/dev.sh"\n' > devtools.toml
  run_script fetch/devtools-fetch.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"[fetch] files in devtools.toml must be a list of paths"* ]]
}

@test "rejects a path that would leave .devtools" {
  for bad in "../escape.sh" "/etc/passwd" "bin/../../x" "bin//x" "bin/x y"; do
    printf '[fetch]\nref = "v1"\nfiles = ["%s"]\n' "$bad" > devtools.toml
    run_script fetch/devtools-fetch.sh
    [ "$status" -eq 1 ]
    [[ "$output" == *"[fetch] files in devtools.toml has an invalid path"* ]]
  done
}

@test "rejects a coverage flag that is not a boolean" {
  printf '[fetch]\ncoverage = "yes"\n' > devtools.toml
  run_script fetch/devtools-fetch.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"[fetch] coverage in devtools.toml must be true or false"* ]]
}

@test "requires a ref when files are listed" {
  printf '[fetch]\nfiles = ["bin/dev.sh"]\n' > devtools.toml
  run_script fetch/devtools-fetch.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"[fetch] in devtools.toml lists files but sets no ref"* ]]
}

@test "rejects a ref that is not a plain git ref" {
  for bad in '"../main"' '"v1/../main"' '"-v1"' '1' '"v1 x"'; do
    printf '[fetch]\nref = %s\nfiles = ["bin/dev.sh"]\n' "$bad" > devtools.toml
    run_script fetch/devtools-fetch.sh
    [ "$status" -eq 1 ]
    [[ "$output" == *"[fetch] ref in devtools.toml is not a valid git ref"* ]]
  done
}
