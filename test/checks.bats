#!/usr/bin/env bats
# shellcheck disable=SC2016  # stub bodies are written literally, to expand when the stub runs
# bin/lint.sh, bin/test-bruno.sh, bin/app-icons.sh and bin/inspect.sh, with the tools they drive
# replaced by stubs.

load test_helper

setup() {
  setup_repo
  export STUB_LOG="$BATS_TEST_TMPDIR/calls"
  : > "$STUB_LOG"
  STUBS="$BATS_TEST_TMPDIR/stubs"
}

# --- lint.sh ---

@test "lint runs the listed checks and the extra commands" {
  make_stub "$STUBS/ruff"
  make_stub "$STUBS/docker"
  mkdir -p bin && printf '#!/usr/bin/env bash\necho hi\n' > bin/a.sh
  cat > devtools.toml <<'TOML'
[lint]
checks = ["shellcheck", "ruff", "compose"]
extra = [["greeting", "echo extra ran in $PWD"]]

[compose]
stacks = [["docker-compose.yml"]]
TOML
  RUFF="$STUBS/ruff" DOCKER="$STUBS/docker" run_script bin/lint.sh
  [ "$status" -eq 0 ]
  [[ "$output" == *"--- shellcheck ---"* ]]
  [[ "$output" == *"--- compose files parse ---"* ]]
  [[ "$output" == *"extra ran in $REPO"* ]]
  [ "$(cat "$STUB_LOG")" = $'ruff check .\nruff format --check .\ndocker compose -f docker-compose.yml config -q' ]
}

@test "lint reports every failing check, not just the first" {
  make_stub "$STUBS/ruff" 'exit 1'
  printf '[lint]\nchecks = ["ruff", "version"]\nextra = [["fails", "exit 3"], ["passes", "true"]]\n' > devtools.toml
  RUFF="$STUBS/ruff" run_script bin/lint.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"--- versions agree ---"* ]]
  [[ "$output" == *"devtools.toml lists no manifests"* ]]
  [[ "$output" == *"--- fails ---"* ]]
  [[ "$output" == *"--- passes ---"* ]]
}

@test "lint checks the versions against the tag RELEASE_TAG names" {
  printf '[lint]\nchecks = ["version"]\n\n[version]\npyprojects = ["pyproject.toml"]\n' > devtools.toml
  printf '[project]\nversion = "1.0.0"\n' > pyproject.toml
  printf '# Changelog\n\n## 1.0.0 — 2026-11-01\n\n- First.\n' > CHANGELOG.md
  run_script bin/lint.sh
  [ "$status" -eq 0 ]
  RELEASE_TAG=v1.0.0 run_script bin/lint.sh
  [ "$status" -eq 0 ]
  RELEASE_TAG=v2.0.0 run_script bin/lint.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"the tag is v2.0.0, but the manifests name 1.0.0"* ]]
}

@test "lint takes ruff from devtools.toml and runs the lockfile check" {
  make_stub "$STUBS/myruff"
  printf '[lint]\nchecks = ["ruff", "lockfile"]\nruff = "%s"\n\n[npm]\ndirs = ["web"]\n' "$STUBS/myruff" > devtools.toml
  mkdir web && printf '{ "resolved": "https://registry.npmjs.org/a/-/a-1.tgz" }\n' > web/package-lock.json
  run_script bin/lint.sh
  [ "$status" -eq 0 ]
  grep -q '^myruff check .$' "$STUB_LOG"
  [[ "$output" == *"1 lockfile(s) resolve only"* ]]
}

@test "lint passes shellcheck with no scripts in bin" {
  printf '[lint]\nchecks = ["shellcheck"]\n' > devtools.toml
  run_script bin/lint.sh
  [ "$status" -eq 0 ]
}

@test "lint refuses an unknown check before running any" {
  printf '[lint]\nchecks = ["shellcheck", "spelling"]\n' > devtools.toml
  run_script bin/lint.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"unknown check 'spelling'"* ]]
  [[ "$output" != *"--- shellcheck ---"* ]]
}

@test "lint refuses an extra entry that is not a name and a command" {
  for extra in '[["lonely"]]' '[["lonely", "true", "surplus"]]'; do
    printf '[lint]\nchecks = []\nextra = %s\n' "$extra" > devtools.toml
    run_script bin/lint.sh
    [ "$status" -eq 1 ]
    [[ "$output" == *"extra entry 'lonely' needs exactly a name and a command"* ]]
  done
}

@test "lint names a check whose script was not fetched" {
  mkdir -p alone && ln -s "$DEVTOOLS_ROOT/bin/lint.sh" "$DEVTOOLS_ROOT/bin/devtools-config.py" alone/
  printf '[lint]\nchecks = ["shellcheck", "version"]\n' > devtools.toml
  run_alone lint.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"the version check needs $REPO/alone/version.py; add bin/version.py to [fetch] files"* ]]
  [[ "$output" != *"--- shellcheck ---"* ]]
}

@test "lint names its missing settings" {
  printf '[fetch]\n' > devtools.toml
  run_script bin/lint.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"devtools.toml sets no lint.checks"* ]]
  printf '[lint]\nchecks = []\nextra = ["flat"]\n' > devtools.toml
  run_script bin/lint.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"lint.extra must be a list of non-empty lists"* ]]
}

# --- test-bruno.sh ---

bruno_config() {
  cat > devtools.toml <<'TOML'
[bruno]
server_dir = "backend"
server = "tests.fixture_server"
health = "/api/health"
folders = ["api", "admin"]
url_var = "base_url"
env_vars = ["login=lucia", "password=correct horse battery"]
port = 18597
python = "venv/python"
TOML
  mkdir -p backend bruno venv
  # Stands in for the fixture server: records how it was started, serves for at most 30 seconds,
  # and records being stopped. Short sleeps, so nothing outlives it.
  make_stub venv/python 'echo "cwd=$PWD pid=$$" >> "$STUB_LOG"' \
    'trap "echo stopped >> \"$STUB_LOG\"; exit 0" TERM' 'for _ in $(seq 300); do sleep 0.1; done'
  make_stub "$STUBS/curl"
  make_stub "$STUBS/npx" 'echo "npx-cwd=$PWD" >> "$STUB_LOG"'
}

@test "test-bruno serves the fixtures, runs the folders against them, and stops the server" {
  bruno_config
  NPX="$STUBS/npx" CURL="$STUBS/curl" run_script bin/test-bruno.sh
  [ "$status" -eq 0 ]
  grep -q "^python -m tests.fixture_server 18597$" "$STUB_LOG"
  grep -q "^cwd=$REPO/backend " "$STUB_LOG"
  grep -q "^curl -fs -o /dev/null http://127.0.0.1:18597/api/health$" "$STUB_LOG"
  grep -q "^npx-cwd=$REPO/bruno$" "$STUB_LOG"
  grep -q "^npx --yes @usebruno/cli@4.2.0 run api admin -r --env local --env-var base_url=http://127.0.0.1:18597 --env-var login=lucia --env-var password=correct horse battery$" "$STUB_LOG"
  grep -q '^stopped$' "$STUB_LOG"
}

@test "test-bruno takes the port and interpreter from the environment" {
  bruno_config
  mkdir -p elsewhere && cp venv/python elsewhere/python
  BRUNO_PORT=19000 PYTHON="$REPO/elsewhere/python" NPX="$STUBS/npx" CURL="$STUBS/curl" run_script bin/test-bruno.sh
  [ "$status" -eq 0 ]
  grep -q "^python -m tests.fixture_server 19000$" "$STUB_LOG"
}

@test "test-bruno runs a bare interpreter name from PATH" {
  bruno_config
  printf '[bruno]\nserver_dir = "backend"\nserver = "s"\nhealth = "/h"\nfolders = ["api"]\nurl_var = "u"\n' > devtools.toml
  PATH="$REPO/venv:$PATH" PYTHON=python NPX="$STUBS/npx" CURL="$STUBS/curl" run_script bin/test-bruno.sh
  [ "$status" -eq 0 ]
  grep -q "^python -m s 8597$" "$STUB_LOG"
}

@test "test-bruno waits for a server that is slow to answer" {
  bruno_config
  # Fails the first probe, as a server still starting does, and answers the next.
  make_stub "$STUBS/curl" '[ -e "$STUB_LOG.up" ] && exit 0' 'touch "$STUB_LOG.up"' 'exit 7'
  NPX="$STUBS/npx" CURL="$STUBS/curl" run_script bin/test-bruno.sh
  [ "$status" -eq 0 ]
  [ "$(grep -c '^curl ' "$STUB_LOG")" -eq 2 ]
  grep -q '^npx ' "$STUB_LOG"
}

@test "test-bruno fails fast when the server exits without answering" {
  bruno_config
  make_stub venv/python 'exit 1'
  make_stub "$STUBS/curl" 'exit 7'
  SECONDS=0
  NPX="$STUBS/npx" CURL="$STUBS/curl" run_script bin/test-bruno.sh
  [ "$status" -eq 1 ]
  [ "$SECONDS" -lt 10 ]
  [[ "$output" == *"the fixture server exited before answering on port 18597"* ]]
  refute grep -q '^npx' "$STUB_LOG"
}

@test "test-bruno refuses to test whatever else answers on the port" {
  bruno_config
  # Exits as a server does when the port is taken, while something else answers there.
  make_stub venv/python 'echo "address already in use" >&2' 'exit 1'
  # Answers only after the server has had time to exit.
  make_stub "$STUBS/curl" 'sleep 0.5'
  NPX="$STUBS/npx" CURL="$STUBS/curl" run_script bin/test-bruno.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"exited before answering"* ]]
  refute grep -q '^npx' "$STUB_LOG"
}

@test "test-bruno hands the server a scratch directory it removes afterwards" {
  bruno_config
  printf '[bruno]\nserver_dir = "backend"\nserver = "s"\nserver_args = ["{scratch}", "--quiet"]\nhealth = "/h"\nfolders = ["api"]\nurl_var = "u"\npython = "venv/python"\n' > devtools.toml
  make_stub venv/python '[ -d "$3" ] && echo "scratch=$3" >> "$STUB_LOG"' \
    'trap "exit 0" TERM' 'for _ in $(seq 300); do sleep 0.1; done'
  NPX="$STUBS/npx" CURL="$STUBS/curl" run_script bin/test-bruno.sh
  [ "$status" -eq 0 ]
  scratch=$(sed -n 's/^scratch=//p' "$STUB_LOG")
  [ -n "$scratch" ]
  grep -q "^python -m s $scratch --quiet 8597$" "$STUB_LOG"
  [ ! -e "$scratch" ]
}

@test "test-bruno waits for the server to exit before returning" {
  bruno_config
  # Detached from the output bats collects, and slow to exit once asked.
  make_stub venv/python 'exec >/dev/null 2>&1' \
    'trap "sleep 1; echo exited >> \"$STUB_LOG\"; exit 0" TERM' 'for _ in $(seq 300); do sleep 0.1; done'
  NPX="$STUBS/npx" CURL="$STUBS/curl" run_script bin/test-bruno.sh
  [ "$status" -eq 0 ]
  grep -q '^exited$' "$STUB_LOG"
}

@test "test-bruno stops Bruno and the server when it is terminated" {
  bruno_config
  make_stub "$STUBS/npx" 'echo "npx-pid=$$" >> "$STUB_LOG"' \
    'trap "echo npx-stopped >> \"$STUB_LOG\"; exit 0" TERM' 'for _ in $(seq 300); do sleep 0.1; done'
  NPX="$STUBS/npx" CURL="$STUBS/curl" "$DEVTOOLS_ROOT/bin/test-bruno.sh" >/dev/null 2>&1 &
  script=$!
  for _ in $(seq 100); do grep -q '^npx-pid=' "$STUB_LOG" && break; sleep 0.1; done
  kill -TERM "$script"
  wait "$script" || true
  grep -q '^npx-stopped$' "$STUB_LOG"
  grep -q '^stopped$' "$STUB_LOG"
}

@test "test-bruno refuses an empty list of folders" {
  bruno_config
  printf '[bruno]\nserver_dir = "backend"\nserver = "s"\nhealth = "/h"\nfolders = []\nurl_var = "u"\n' > devtools.toml
  run_script bin/test-bruno.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"[bruno] folders in devtools.toml is empty"* ]]
}

@test "test-bruno fails when a request's assertions fail, and still stops the server" {
  bruno_config
  make_stub "$STUBS/npx" 'exit 1'
  NPX="$STUBS/npx" CURL="$STUBS/curl" run_script bin/test-bruno.sh
  [ "$status" -eq 1 ]
  grep -q '^stopped$' "$STUB_LOG"
}

# --- app-icons.sh ---

@test "app-icons renders the three sizes on the background" {
  mkdir -p web/icons && touch web/icons/app.svg
  make_stub "$STUBS/rsvg-convert"
  printf '[icons]\nsvg = "web/icons/app.svg"\nout = "web/public/icons"\nbackground = "#2f6f5e"\n' > devtools.toml
  RSVG_CONVERT="$STUBS/rsvg-convert" run_script bin/app-icons.sh
  [ "$status" -eq 0 ]
  [ -d web/public/icons ]
  [ "$(cat "$STUB_LOG")" = "rsvg-convert --background-color #2f6f5e --width 192 --height 192 web/icons/app.svg --output web/public/icons/icon-192.png
rsvg-convert --background-color #2f6f5e --width 512 --height 512 web/icons/app.svg --output web/public/icons/icon-512.png
rsvg-convert --background-color #2f6f5e --width 180 --height 180 web/icons/app.svg --output web/public/icons/apple-touch-icon.png" ]
}

@test "app-icons leaves the background transparent without one" {
  touch app.svg
  make_stub "$STUBS/rsvg-convert"
  printf '[icons]\nsvg = "app.svg"\nout = "icons"\n' > devtools.toml
  RSVG_CONVERT="$STUBS/rsvg-convert" run_script bin/app-icons.sh
  [ "$status" -eq 0 ]
  refute grep -q background "$STUB_LOG"
}

@test "app-icons reports a missing drawing" {
  printf '[icons]\nsvg = "app.svg"\nout = "icons"\n' > devtools.toml
  run_script bin/app-icons.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"app.svg is missing"* ]]
}

# --- inspect.sh ---

# An inspect.sh stand-in that reports a problem for each inspection named in $FINDINGS.
stub_inspect() {
  make_stub "$STUBS/inspect" 'echo "props=$(cat "$IDEA_PROPERTIES")" >> "$STUB_LOG"' \
    'for name in $FINDINGS; do echo "<problems/>" > "$3/$name.xml"; done'
}

@test "inspect passes when no inspection reports a problem" {
  printf '[fetch]\n' > devtools.toml
  stub_inspect
  FINDINGS="" IDEA_INSPECT="$STUBS/inspect" run_script bin/inspect.sh
  [ "$status" -eq 0 ]
  [[ "$output" == *"no problems found"* ]]
  grep -q "^inspect $REPO $REPO/.idea/inspectionProfiles/Project_Default.xml $REPO/inspect/xml -v0$" "$STUB_LOG"
  grep -q "props=idea.system.path=$REPO/inspect/idea/system" "$STUB_LOG"
}

@test "inspect fails naming each inspection with problems, past the ignored ones" {
  printf '[inspect]\nignore = ["UndefinedAction"]\n' > devtools.toml
  stub_inspect
  FINDINGS="UndefinedAction UnusedImport" IDEA_INSPECT="$STUBS/inspect" run_script bin/inspect.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"1 inspection(s) found problems:"* ]]
  [[ "$output" == *"  UnusedImport"* ]]
  [[ "$output" != *"  UndefinedAction"* ]]
}

@test "inspect passes when only ignored inspections report problems" {
  printf '[inspect]\nignore = ["UndefinedAction"]\n' > devtools.toml
  stub_inspect
  FINDINGS="UndefinedAction" IDEA_INSPECT="$STUBS/inspect" run_script bin/inspect.sh
  [ "$status" -eq 0 ]
}

@test "inspect shows the end of IntelliJ's log when it fails" {
  printf '[fetch]\n' > devtools.toml
  make_stub "$STUBS/inspect" 'echo "noise" >&2' 'echo "license expired" >&2' 'exit 2'
  IDEA_INSPECT="$STUBS/inspect" run_script bin/inspect.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"IntelliJ's inspect.sh failed"* ]]
  [[ "$output" == *"license expired"* ]]
}

@test "inspect reports a missing IntelliJ" {
  printf '[fetch]\n' > devtools.toml
  IDEA_INSPECT="$STUBS/none" run_script bin/inspect.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"inspect.sh is not at $STUBS/none"* ]]
}
