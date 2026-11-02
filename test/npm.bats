#!/usr/bin/env bats
# shellcheck disable=SC2016  # stub bodies are written literally, to expand when the stub runs
# bin/lockfile.sh and bin/check-lockfile.sh, with docker and npm replaced by stubs.

load test_helper

PUBLIC="https://registry.npmjs.org/"

setup() {
  setup_repo
  export STUB_LOG="$BATS_TEST_TMPDIR/calls"
  : > "$STUB_LOG"
  STUBS="$BATS_TEST_TMPDIR/stubs"
}

# Writes a lockfile whose packages resolve to the given URLs.
# Arguments: path, then one URL per package.
write_lockfile() {
  local path="$1" url
  shift
  mkdir -p "$(dirname "$path")"
  {
    printf '{\n  "packages": {\n'
    for url in "$@"; do
      printf '    "x": { "resolved": "%s" },\n' "$url"
    done
    printf '  }\n}\n'
  } > "$path"
}

# A frontend directory ready for lockfile.sh.
make_frontend() {
  mkdir -p "$1"
  printf '{}\n' > "$1/package.json"
  printf 'registry=%s\n' "$PUBLIC" > "$1/.npmrc"
}

# A docker stand-in that writes, into the directory mounted at /output, a lockfile resolving
# through a proxied registry.
stub_docker() {
  make_stub "$STUBS/docker" \
    'for a in "$@"; do case "$a" in *:/output) out="${a%:/output}" ;; esac; done' \
    'printf "{ \"resolved\": \"https://proxy.example/registry/api/npm/npm-remote/vite/-/vite-7.0.0.tgz\" }\n" > "$out/package-lock.json.new"'
}

# --- check-lockfile.sh ---

@test "check-lockfile passes lockfiles that resolve only to the public registry" {
  printf '[npm]\ndirs = ["frontend", "site"]\n' > devtools.toml
  write_lockfile frontend/package-lock.json "${PUBLIC}vite/-/vite-7.0.0.tgz"
  write_lockfile site/package-lock.json "${PUBLIC}a/-/a-1.0.0.tgz" "${PUBLIC}b/-/b-1.0.0.tgz"
  run_script bin/check-lockfile.sh
  [ "$status" -eq 0 ]
  [[ "$output" == *"2 lockfile(s) resolve only to the public registry"* ]]
}

@test "check-lockfile names each foreign host once, without its paths" {
  printf '[npm]\ndirs = ["frontend"]\n' > devtools.toml
  write_lockfile frontend/package-lock.json "${PUBLIC}ok/-/ok-1.tgz" \
    "https://proxy.example/npm/a/-/a-1.tgz" "https://proxy.example/npm/b/-/b-1.tgz"
  run_script bin/check-lockfile.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"frontend/package-lock.json resolves packages somewhere other than $PUBLIC"* ]]
  [ "$(grep -c 'https://proxy.example/…' <<< "$output")" -eq 1 ]
  [[ "$output" != *"/npm/a/"* ]]
}

@test "check-lockfile refuses a lookalike of the public registry" {
  write_lockfile package-lock.json "https://registry.npmjs.org.example/a/-/a-1.tgz"
  run_script bin/check-lockfile.sh package-lock.json
  [ "$status" -eq 1 ]
  [[ "$output" == *"https://registry.npmjs.org.example/…"* ]]
}

@test "check-lockfile reports a missing lockfile of a listed directory" {
  printf '[npm]\ndirs = ["frontend"]\n' > devtools.toml
  run_script bin/check-lockfile.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"frontend/package-lock.json is missing"* ]]
}

@test "check-lockfile also checks every lockfile git tracks" {
  printf '[npm]\ndirs = ["frontend"]\n' > devtools.toml
  write_lockfile frontend/package-lock.json "${PUBLIC}a/-/a-1.tgz"
  write_lockfile tools/package-lock.json "https://proxy.example/npm/a/-/a-1.tgz"
  git init -q . && git add frontend tools
  run_script bin/check-lockfile.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"tools/package-lock.json resolves packages"* ]]
}

@test "check-lockfile checks a tracked lockfile of a listed directory once" {
  printf '[npm]\ndirs = ["frontend"]\n' > devtools.toml
  write_lockfile frontend/package-lock.json "${PUBLIC}a/-/a-1.tgz"
  git init -q . && git add frontend
  run_script bin/check-lockfile.sh
  [ "$status" -eq 0 ]
  [[ "$output" == *"1 lockfile(s)"* ]]
}

@test "check-lockfile still checks a tracked lockfile whose path a listed directory contains" {
  printf '[npm]\ndirs = ["a b"]\n' > devtools.toml
  write_lockfile "a b/package-lock.json" "${PUBLIC}a/-/a-1.tgz"
  write_lockfile b/package-lock.json "https://proxy.example/npm/a/-/a-1.tgz"
  git init -q . && git add "a b" b
  run_script bin/check-lockfile.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"b/package-lock.json resolves packages"* ]]
}

@test "check-lockfile needs no setting when the lockfiles are tracked" {
  printf '[fetch]\n' > devtools.toml
  write_lockfile web/package-lock.json "${PUBLIC}a/-/a-1.tgz"
  git init -q . && git add web
  run_script bin/check-lockfile.sh
  [ "$status" -eq 0 ]
  [[ "$output" == *"1 lockfile(s)"* ]]
}

@test "check-lockfile passes a workspace package linked by path" {
  write_lockfile package-lock.json "${PUBLIC}a/-/a-1.tgz" "packages/shared"
  run_script bin/check-lockfile.sh package-lock.json
  [ "$status" -eq 0 ]
}

@test "check-lockfile refuses to pass with nothing to check" {
  printf '[npm]\ndirs = []\n' > devtools.toml
  run_script bin/check-lockfile.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"no lockfiles to check"* ]]
}

@test "check-lockfile refuses a setting of the wrong shape" {
  printf '[npm]\ndirs = "frontend"\n' > devtools.toml
  run_script bin/check-lockfile.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"npm.dirs must be a list"* ]]
}

# --- lockfile.sh ---

@test "lockfile installs in a Linux container and records only the public registry" {
  printf '[npm]\ndirs = ["frontend"]\n' > devtools.toml
  make_frontend frontend
  stub_docker
  make_stub "$STUBS/npm" 'echo "cwd=$PWD" >> "$STUB_LOG"' 'echo https://proxy.example/registry/api/npm/npm-remote/'
  DOCKER="$STUBS/docker" NPM="$STUBS/npm" run_script bin/lockfile.sh
  [ "$status" -eq 0 ]
  [[ "$output" == *"Installing through: https://proxy.example/registry/api/npm/npm-remote/"* ]]
  [ "$(cat frontend/package-lock.json)" = "{ \"resolved\": \"${PUBLIC}vite/-/vite-7.0.0.tgz\" }" ]
  grep -q '^cwd=/$' "$STUB_LOG"
  docker_call=$(grep '^docker ' "$STUB_LOG")
  [[ "$docker_call" == *"-v $REPO/frontend/package.json:/app/package.json:ro"* ]]
  [[ "$docker_call" == *"-v $REPO/frontend/.npmrc:/app/.npmrc:ro"* ]]
  [[ "$docker_call" == *" node:24-alpine sh -c npm install --registry='https://proxy.example/registry/api/npm/npm-remote/'"* ]]
  [[ "$output" == *"1 lockfile(s) resolve only to the public registry"* ]]
  [ -z "$(find frontend -name 'package-lock.json.*')" ]
}

@test "lockfile regenerates every listed directory, or only the one named" {
  printf '[npm]\ndirs = ["frontend", "site"]\nnode_image = "node:26-alpine"\n' > devtools.toml
  make_frontend frontend
  make_frontend site
  stub_docker
  make_stub "$STUBS/npm" 'echo undefined'
  DOCKER="$STUBS/docker" NPM="$STUBS/npm" run_script bin/lockfile.sh
  [ "$status" -eq 0 ]
  [[ "$output" == *"Installing through: $PUBLIC"* ]]
  [ "$(grep -c ' node:26-alpine ' "$STUB_LOG")" -eq 2 ]
  : > "$STUB_LOG"
  DOCKER="$STUBS/docker" NPM="$STUBS/npm" run_script bin/lockfile.sh site
  [ "$status" -eq 0 ]
  [ "$(grep -c '^docker ' "$STUB_LOG")" -eq 1 ]
  grep -q "$REPO/site:/output" "$STUB_LOG"
}

@test "lockfile falls back to the public registry when npm is missing" {
  printf '[npm]\ndirs = ["frontend"]\n' > devtools.toml
  make_frontend frontend
  stub_docker
  DOCKER="$STUBS/docker" NPM="$STUBS/no-such-npm" run_script bin/lockfile.sh
  [ "$status" -eq 0 ]
  [[ "$output" == *"Installing through: $PUBLIC"* ]]
}

@test "lockfile refuses a directory without an .npmrc" {
  printf '[npm]\ndirs = ["frontend"]\n' > devtools.toml
  make_frontend frontend
  rm frontend/.npmrc
  stub_docker
  DOCKER="$STUBS/docker" NPM="$STUBS/no-such-npm" run_script bin/lockfile.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"frontend needs a package.json and an .npmrc"* ]]
  refute grep -q '^docker ' "$STUB_LOG"
}

@test "lockfile keeps the committed lockfile when the install fails" {
  printf '[npm]\ndirs = ["frontend"]\n' > devtools.toml
  make_frontend frontend
  printf 'committed\n' > frontend/package-lock.json
  make_stub "$STUBS/docker" 'exit 1'
  DOCKER="$STUBS/docker" NPM="$STUBS/no-such-npm" run_script bin/lockfile.sh
  [ "$status" -eq 1 ]
  [[ "$output" != *"regenerated"* ]]
  [ "$(cat frontend/package-lock.json)" = "committed" ]
  [ -z "$(find frontend -name 'package-lock.json.*')" ]
}

@test "lockfile keeps the committed lockfile when a URL survives the rewrite" {
  printf '[npm]\ndirs = ["frontend"]\n' > devtools.toml
  make_frontend frontend
  printf 'committed\n' > frontend/package-lock.json
  make_stub "$STUBS/docker" \
    'for a in "$@"; do case "$a" in *:/output) out="${a%:/output}" ;; esac; done' \
    'printf "{ \"resolved\": \"https://other.example/npm/a/-/a-1.tgz\" }\n" > "$out/package-lock.json.new"'
  DOCKER="$STUBS/docker" NPM="$STUBS/no-such-npm" run_script bin/lockfile.sh
  [ "$status" -eq 1 ]
  [ "$(cat frontend/package-lock.json)" = "committed" ]
  [ -z "$(find frontend -name 'package-lock.json.*')" ]
}

@test "lockfile needs check-lockfile.sh beside it" {
  mkdir -p alone && ln -s "$DEVTOOLS_ROOT/bin/lockfile.sh" alone/
  run_alone lockfile.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"add bin/check-lockfile.sh to [fetch] files"* ]]
}

@test "lockfile refuses an empty list of directories" {
  printf '[npm]\ndirs = []\n' > devtools.toml
  run_script bin/lockfile.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"[npm] dirs in devtools.toml is empty"* ]]
}
