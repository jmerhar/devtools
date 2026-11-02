#!/usr/bin/env bats
# make/devtools.mk, included by a scratch repository through the bootstrap rule the README gives,
# with the fetcher fetching from a file:// stand-in for jmerhar/devtools.

load test_helper

setup() {
  setup_repo
  UPSTREAM="$BATS_TEST_TMPDIR/upstream"
  export DEVTOOLS_URL="file://$UPSTREAM/devtools"
  export COVERAGE_URL="file://$UPSTREAM/coverage"
  export DEVTOOLS_FETCH_RETRIES=0
  mkdir -p "$UPSTREAM/devtools/v1/make" "$UPSTREAM/devtools/v1/bin" "$UPSTREAM/coverage" bin
  cp "$DEVTOOLS_ROOT/make/devtools.mk" "$UPSTREAM/devtools/v1/make/"
  cp "$DEVTOOLS_ROOT/bin/devtools-config.py" "$UPSTREAM/devtools/v1/bin/"
  printf 'report\n' > "$UPSTREAM/coverage/coverage-report.py"
  printf 'kcov\n' > "$UPSTREAM/coverage/run-kcov.sh"
  cp "$DEVTOOLS_ROOT/fetch/devtools-fetch.sh" bin/
  printf '[fetch]\nref = "v1"\nfiles = ["make/devtools.mk"]\ncoverage = true\n' > devtools.toml
  # The README's bootstrap, followed by targets of the repository's own.
  cat > Makefile <<'MAKE'
.DEFAULT_GOAL := help
include .devtools/make/devtools.mk
.devtools/make/devtools.mk: devtools.toml bin/devtools-fetch.sh
	bin/devtools-fetch.sh

##@ Testing

test: ## Run the suite
	@echo testing

test-e2e.v2: ## Run the end-to-end suite
	@echo e2e

show-tooling:
	@echo $(COVERAGE_TOOLING)
MAKE
  # Older than anything fetched, so make's view of what is current does not hang on the clock.
  touch -t 202001010000 devtools.toml bin/devtools-fetch.sh Makefile
}

@test "the first make fetches the tooling, then shows help by default" {
  run make
  [ "$status" -eq 0 ]
  [[ "$output" == *"devtools-fetch: 4 files current in .devtools/"* ]]
  [ -f .devtools/make/devtools.mk ]
  [[ "$output" == *"Testing"* ]]
  [[ "$output" == *"make test"*"Run the suite"* ]]
  [[ "$output" == *"make test-e2e.v2"*"Run the end-to-end suite"* ]]
  [[ "$output" == *"Shared tooling"* ]]
  [[ "$output" == *"make devtools-update"*"Fetch the shared tooling"* ]]
  [[ "$output" == *"make coverage-tooling"* ]]
  [[ "$output" != *"show-tooling"* ]]
}

@test "a later make does not fetch again" {
  make >/dev/null
  run make help
  [ "$status" -eq 0 ]
  [[ "$output" != *"devtools-fetch"* ]]
  [[ "$output" == *"make test"* ]]
}

@test "changing devtools.toml fetches again" {
  make >/dev/null
  # An edit dated after the fetched copy. Dates in the past, because make 4 keeps refetching a
  # makefile that a fetch cannot make newer than its future-dated prerequisite.
  touch -t 202101010000 .devtools/make/devtools.mk
  touch -t 202201010000 devtools.toml
  run make test
  [ "$status" -eq 0 ]
  [[ "$output" == *"devtools-fetch: 4 files current"* ]]
  [[ "$output" == *"testing"* ]]
}

@test "devtools-update and coverage-tooling run the fetcher" {
  make >/dev/null
  run make devtools-update
  [ "$status" -eq 0 ]
  [[ "$output" == *"devtools-fetch: 4 files current"* ]]
  rm -rf .devtools/coverage
  run make coverage-tooling
  [ "$status" -eq 0 ]
  [ "$(cat .devtools/coverage/run-kcov.sh)" = "kcov" ]
}

@test "COVERAGE_TOOLING names the fetched coverage tooling" {
  make >/dev/null
  run make show-tooling
  [ "$status" -eq 0 ]
  [ "$output" = ".devtools/coverage" ]
}

@test "a failed fetch is retried on the next make" {
  mv "$UPSTREAM/coverage" "$UPSTREAM/coverage-away"
  run make test
  [ "$status" -ne 0 ]
  [[ "$output" == *"2 of 4 files failed"* ]]
  mv "$UPSTREAM/coverage-away" "$UPSTREAM/coverage"
  run make test
  [ "$status" -eq 0 ]
  [[ "$output" == *"devtools-fetch: 4 files current"* ]]
  [[ "$output" == *"testing"* ]]
}
