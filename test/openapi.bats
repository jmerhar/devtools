#!/usr/bin/env bats
# shellcheck disable=SC2016  # stub bodies are written literally, to expand when the stub runs
# bin/openapi.sh, with the app's interpreter, npm and npx replaced by stubs.

load test_helper

setup() {
  setup_repo
  export STUB_LOG="$BATS_TEST_TMPDIR/calls"
  : > "$STUB_LOG"
  STUBS="$BATS_TEST_TMPDIR/stubs"
  mkdir -p frontend/src/lib
  cat > devtools.toml <<'TOML'
[openapi]
app = "myapp.api.schema:build_app"
schema = "frontend/openapi.json"
types = "frontend/src/lib/api-types.ts"
python = "venv/python"
TOML
  # Stands in for the app's interpreter running export-openapi.py.
  make_stub "$STUBS/python" 'echo "{\"openapi\": \"3.1.0\"}"'
  make_stub "$STUBS/npm" 'echo "cwd=$PWD" >> "$STUB_LOG"' 'echo https://proxy.example/npm/'
  make_stub "$STUBS/npx"
}

@test "openapi exports the schema, then generates types with the pinned generator" {
  PYTHON="$STUBS/python" NPM="$STUBS/npm" NPX="$STUBS/npx" run_script bin/openapi.sh
  [ "$status" -eq 0 ]
  [ "$(cat frontend/openapi.json)" = '{"openapi": "3.1.0"}' ]
  [ "$(sed -n 1p "$STUB_LOG")" = "python $DEVTOOLS_ROOT/bin/export-openapi.py" ]
  grep -q '^cwd=/$' "$STUB_LOG"
  [ "$(tail -1 "$STUB_LOG")" = "npx --yes --registry=https://proxy.example/npm/ openapi-typescript@7.13.0 frontend/openapi.json --default-non-nullable false -o frontend/src/lib/api-types.ts" ]
  [[ "$output" == *"Exporting the schema to frontend/openapi.json"* ]]
  [[ "$output" == *"Generating frontend/src/lib/api-types.ts"* ]]
}

@test "openapi takes the interpreter from devtools.toml when PYTHON is unset" {
  mkdir -p venv && cp "$STUBS/python" venv/python
  NPM="$STUBS/npm" NPX="$STUBS/npx" run_script bin/openapi.sh
  [ "$status" -eq 0 ]
  [ "$(sed -n 1p "$STUB_LOG")" = "python $DEVTOOLS_ROOT/bin/export-openapi.py" ]
}

@test "openapi reports a missing interpreter" {
  NPM="$STUBS/npm" NPX="$STUBS/npx" run_script bin/openapi.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"no interpreter at 'venv/python'"* ]]
}

@test "openapi leaves the committed schema alone when the export fails" {
  printf 'committed\n' > frontend/openapi.json
  make_stub "$STUBS/python" 'echo partial' 'exit 1'
  PYTHON="$STUBS/python" NPM="$STUBS/npm" NPX="$STUBS/npx" run_script bin/openapi.sh
  [ "$status" -eq 1 ]
  [ "$(cat frontend/openapi.json)" = "committed" ]
  [ ! -e frontend/openapi.json.tmp ]
  refute grep -q '^npx' "$STUB_LOG"
}

@test "openapi generates through the public registry when npm has none" {
  make_stub "$STUBS/npm" 'echo undefined'
  PYTHON="$STUBS/python" NPM="$STUBS/npm" NPX="$STUBS/npx" run_script bin/openapi.sh
  [ "$status" -eq 0 ]
  [[ "$(tail -1 "$STUB_LOG")" == "npx --yes --registry=https://registry.npmjs.org/ "* ]]
}

@test "openapi fails when the generator fails" {
  make_stub "$STUBS/npx" 'exit 1'
  PYTHON="$STUBS/python" NPM="$STUBS/no-such-npm" NPX="$STUBS/npx" run_script bin/openapi.sh
  [ "$status" -eq 1 ]
}

@test "openapi names a missing setting" {
  printf '[openapi]\nschema = "a.json"\n' > devtools.toml
  PYTHON="$STUBS/python" run_script bin/openapi.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"devtools.toml sets no openapi.types"* ]]
}

@test "openapi needs export-openapi.py beside it" {
  mkdir -p alone && ln -s "$DEVTOOLS_ROOT/bin/openapi.sh" alone/
  run_alone openapi.sh
  [ "$status" -eq 1 ]
  [[ "$output" == *"add bin/export-openapi.py to [fetch] files"* ]]
}
