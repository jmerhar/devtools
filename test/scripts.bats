#!/usr/bin/env bats
# shellcheck disable=SC2016  # stub bodies are written literally, to expand when the stub runs
# The shared scripts in bin/, with docker, npm and ruff replaced by stubs that log their arguments.

load test_helper

setup() {
  setup_repo
  export STUB_LOG="$BATS_TEST_TMPDIR/calls"
  : > "$STUB_LOG"
  STUBS="$BATS_TEST_TMPDIR/stubs"
}

# --- ci-ruff.sh ---

@test "ci-ruff checks lint and formatting with the ruff RUFF names" {
  make_stub "$STUBS/ruff"
  RUFF="$STUBS/ruff" run_script bin/ci-ruff.sh
  [ "$status" -eq 0 ]
  [ "$(cat "$STUB_LOG")" = $'ruff check .\nruff format --check .' ]
}

@test "ci-ruff fails when the lint fails, before checking formatting" {
  make_stub "$STUBS/ruff" 'exit 1'
  RUFF="$STUBS/ruff" run_script bin/ci-ruff.sh
  [ "$status" -eq 1 ]
  [ "$(cat "$STUB_LOG")" = "ruff check ." ]
}

# --- check-compose.sh ---

@test "check-compose validates each stack with its files together" {
  make_stub "$STUBS/docker"
  cat > devtools.toml <<'TOML'
[compose]
stacks = [["docker-compose.yml"], ["docker-compose.yml", "docker-compose.build.yml"]]
TOML
  DOCKER="$STUBS/docker" run_script bin/check-compose.sh
  [ "$status" -eq 0 ]
  [ "$(sed -n 1p "$STUB_LOG")" = "docker compose -f docker-compose.yml config -q" ]
  [ "$(sed -n 2p "$STUB_LOG")" = "docker compose -f docker-compose.yml -f docker-compose.build.yml config -q" ]
  [ "$(wc -l < "$STUB_LOG")" -eq 2 ]
  [[ "$output" == *"check-compose: docker-compose.yml docker-compose.build.yml is valid"* ]]
}

@test "check-compose keeps a file name with spaces in one argument" {
  make_stub "$STUBS/docker" 'printf "<%s>" "$@" >> "$STUB_LOG.args"'
  printf '[compose]\nstacks = [["my stack.yml"]]\n' > devtools.toml
  DOCKER="$STUBS/docker" run_script bin/check-compose.sh
  [ "$status" -eq 0 ]
  [ "$(cat "$STUB_LOG.args")" = "<compose><-f><my stack.yml><config><-q>" ]
}

@test "check-compose fails on the first stack that does not validate" {
  make_stub "$STUBS/docker" 'exit 1'
  printf '[compose]\nstacks = [["a.yml"], ["b.yml"]]\n' > devtools.toml
  DOCKER="$STUBS/docker" run_script bin/check-compose.sh
  [ "$status" -eq 1 ]
  [ "$(cat "$STUB_LOG")" = "docker compose -f a.yml config -q" ]
}

@test "check-compose names the setting when devtools.toml lacks it" {
  make_stub "$STUBS/docker"
  printf '[fetch]\n' > devtools.toml
  DOCKER="$STUBS/docker" run_script bin/check-compose.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"devtools.toml sets no compose.stacks"* ]]
  [ ! -s "$STUB_LOG" ]
}

@test "check-compose refuses a flat list or an empty stack" {
  make_stub "$STUBS/docker"
  for stacks in '["base.yml", "override.yml"]' '[["a.yml"], []]'; do
    printf '[compose]\nstacks = %s\n' "$stacks" > devtools.toml
    DOCKER="$STUBS/docker" run_script bin/check-compose.sh
    [ "$status" -eq 1 ]
    [[ "$output" == *"compose.stacks must be a list of non-empty lists"* ]]
  done
  [ ! -s "$STUB_LOG" ]
}

@test "check-compose refuses an empty list of stacks" {
  make_stub "$STUBS/docker"
  printf '[compose]\nstacks = []\n' > devtools.toml
  DOCKER="$STUBS/docker" run_script bin/check-compose.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"[compose] stacks in devtools.toml is empty"* ]]
  [ ! -s "$STUB_LOG" ]
}

# --- dev.sh ---

@test "dev starts the configured files with the registry npm reports, asked from /" {
  make_stub "$STUBS/docker" 'echo "registry=$NPM_REGISTRY" >> "$STUB_LOG"'
  make_stub "$STUBS/npm" 'echo "cwd=$PWD" >> "$STUB_LOG"' 'echo https://mirror.example/npm/'
  printf '[dev]\ncompose_files = ["docker-compose.yml", "docker-compose.dev.yml"]\n' > devtools.toml
  DOCKER="$STUBS/docker" NPM="$STUBS/npm" run_script bin/dev.sh --remove-orphans
  [ "$status" -eq 0 ]
  [[ "$output" == *"Installing npm packages through: https://mirror.example/npm/"* ]]
  [ "$(cat "$STUB_LOG")" = "npm config get registry
cwd=/
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build --remove-orphans
registry=https://mirror.example/npm/" ]
}

@test "dev leaves a registry set in the environment alone" {
  make_stub "$STUBS/docker" 'echo "registry=$NPM_REGISTRY" >> "$STUB_LOG"'
  make_stub "$STUBS/npm" 'echo https://mirror.example/npm/'
  printf '[dev]\ncompose_files = ["docker-compose.yml"]\n' > devtools.toml
  NPM_REGISTRY=https://chosen.example/ DOCKER="$STUBS/docker" NPM="$STUBS/npm" run_script bin/dev.sh
  [ "$status" -eq 0 ]
  [ "$(cat "$STUB_LOG")" = $'docker compose -f docker-compose.yml up --build\nregistry=https://chosen.example/' ]
}

@test "dev leaves a registry set in .env to compose" {
  make_stub "$STUBS/docker" 'echo "registry=${NPM_REGISTRY:-unset}" >> "$STUB_LOG"'
  make_stub "$STUBS/npm" 'echo https://mirror.example/npm/'
  printf '[dev]\ncompose_files = ["docker-compose.yml"]\n' > devtools.toml
  printf '  NPM_REGISTRY=https://from-env-file.example/\n' > .env
  DOCKER="$STUBS/docker" NPM="$STUBS/npm" run_script bin/dev.sh
  [ "$status" -eq 0 ]
  [ "$(cat "$STUB_LOG")" = $'docker compose -f docker-compose.yml up --build\nregistry=unset' ]
}

@test "dev leaves a registry exported from .env to compose" {
  make_stub "$STUBS/docker" 'echo "registry=${NPM_REGISTRY:-unset}" >> "$STUB_LOG"'
  make_stub "$STUBS/npm" 'echo https://mirror.example/npm/'
  printf '[dev]\ncompose_files = ["docker-compose.yml"]\n' > devtools.toml
  printf 'export NPM_REGISTRY=https://from-env-file.example/\n' > .env
  DOCKER="$STUBS/docker" NPM="$STUBS/npm" run_script bin/dev.sh
  [ "$status" -eq 0 ]
  [ "$(tail -1 "$STUB_LOG")" = "registry=unset" ]
}

@test "dev ignores a commented-out registry in .env" {
  make_stub "$STUBS/docker" 'echo "registry=${NPM_REGISTRY:-unset}" >> "$STUB_LOG"'
  make_stub "$STUBS/npm" 'echo https://mirror.example/npm/'
  printf '[dev]\ncompose_files = ["docker-compose.yml"]\n' > devtools.toml
  printf '# NPM_REGISTRY=https://from-env-file.example/\n' > .env
  DOCKER="$STUBS/docker" NPM="$STUBS/npm" run_script bin/dev.sh
  [ "$status" -eq 0 ]
  [ "$(tail -1 "$STUB_LOG")" = "registry=https://mirror.example/npm/" ]
}

@test "dev passes no registry when npm is not installed" {
  make_stub "$STUBS/docker" 'echo "registry=${NPM_REGISTRY:-unset}" >> "$STUB_LOG"'
  printf '[dev]\ncompose_files = ["docker-compose.yml"]\n' > devtools.toml
  DOCKER="$STUBS/docker" NPM="$STUBS/no-such-npm" run_script bin/dev.sh
  [ "$status" -eq 0 ]
  [ "$(tail -1 "$STUB_LOG")" = "registry=unset" ]
}

@test "dev refuses compose files given as a list of lists" {
  make_stub "$STUBS/docker"
  printf '[dev]\ncompose_files = [["a.yml", "b.yml"]]\n' > devtools.toml
  DOCKER="$STUBS/docker" run_script bin/dev.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"dev.compose_files must be a list"* ]]
  [ ! -s "$STUB_LOG" ]
}

@test "dev passes no registry when npm has none configured" {
  make_stub "$STUBS/docker" 'echo "registry=${NPM_REGISTRY:-unset}" >> "$STUB_LOG"'
  make_stub "$STUBS/npm" 'echo undefined'
  printf '[dev]\ncompose_files = ["docker-compose.yml"]\n' > devtools.toml
  DOCKER="$STUBS/docker" NPM="$STUBS/npm" run_script bin/dev.sh
  [ "$status" -eq 0 ]
  [[ "$output" != *"Installing npm packages"* ]]
  [ "$(tail -1 "$STUB_LOG")" = "registry=unset" ]
}

@test "dev passes no registry when npm fails" {
  make_stub "$STUBS/docker" 'echo "registry=${NPM_REGISTRY:-unset}" >> "$STUB_LOG"'
  make_stub "$STUBS/npm" 'exit 1'
  printf '[dev]\ncompose_files = ["docker-compose.yml"]\n' > devtools.toml
  DOCKER="$STUBS/docker" NPM="$STUBS/npm" run_script bin/dev.sh
  [ "$status" -eq 0 ]
  [ "$(tail -1 "$STUB_LOG")" = "registry=unset" ]
}

@test "dev names the setting when devtools.toml lacks it" {
  make_stub "$STUBS/docker"
  printf '[fetch]\n' > devtools.toml
  DOCKER="$STUBS/docker" run_script bin/dev.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"devtools.toml sets no dev.compose_files"* ]]
  [ ! -s "$STUB_LOG" ]
}

@test "dev refuses an empty list of compose files" {
  make_stub "$STUBS/docker"
  printf '[dev]\ncompose_files = []\n' > devtools.toml
  DOCKER="$STUBS/docker" run_script bin/dev.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"[dev] compose_files in devtools.toml is empty"* ]]
  [ ! -s "$STUB_LOG" ]
}
