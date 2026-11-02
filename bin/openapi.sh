#!/usr/bin/env bash
# Export the API's OpenAPI schema, then generate the frontend's TypeScript types from it.
#
# Both are committed, so a change to a response shape shows up as a diff in the change that caused
# it, and a check that regenerates them and diffs (`make contract`) proves the copies are current.
#
#   [openapi]
#   app = "myapp.api.schema:build_app"         # see export-openapi.py
#   schema = "frontend/openapi.json"
#   types = "frontend/src/lib/api-types.ts"
#   python = "backend/.venv/bin/python"        # optional; PYTHON overrides it
#   defaults_optional = true                   # optional, the default
#
# The generator runs as a pinned package of its own rather than one installed into the frontend,
# fetched through the registry this machine's npm reaches outside any project. With
# defaults_optional, a field with a default stays optional (--default-non-nullable false), as the
# API treats it in a request; without it, such a field is required, as it is in a response.
#
# Usage: .devtools/bin/openapi.sh    (from the repository root)
#   PYTHON   the interpreter the app is installed in
#   NPM      the npm command asked for the registry (default: npm)
#   NPX      the npx command (default: npx)
set -euo pipefail

here="$(dirname "$0")"
[ -f "$here/export-openapi.py" ] || {
  echo "openapi: needs $here/export-openapi.py; add bin/export-openapi.py to [fetch] files" >&2
  exit 1
}
npm="${NPM:-npm}"
npx="${NPX:-npx}"
generator="openapi-typescript@7.13.0"

schema=$(python3 "$here/devtools-config.py" openapi.schema)
types=$(python3 "$here/devtools-config.py" openapi.types)
python="${PYTHON:-$(python3 "$here/devtools-config.py" --default backend/.venv/bin/python openapi.python)}"
defaults_optional=$(python3 "$here/devtools-config.py" --default true openapi.defaults_optional)
case "$defaults_optional" in
  true) flags=(--default-non-nullable false) ;;
  false) flags=() ;;
  *)
    echo "openapi: [openapi] defaults_optional must be true or false" >&2
    exit 1
    ;;
esac
if ! command -v "$python" >/dev/null 2>&1; then
  echo "openapi: no interpreter at '$python'; install the app first, or set PYTHON" >&2
  exit 1
fi

echo "Exporting the schema to $schema"
# Written to a temporary file first, so a failed export leaves the committed schema as it was.
"$python" "$here/export-openapi.py" > "$schema.tmp" || { rm -f "$schema.tmp"; exit 1; }
mv "$schema.tmp" "$schema"

echo "Generating $types"
registry=$(cd / && "$npm" config get registry 2>/dev/null) || registry=""
if [ -z "$registry" ] || [ "$registry" = "undefined" ]; then
  registry="https://registry.npmjs.org/"
fi
"$npx" --yes --registry="$registry" "$generator" "$schema" "${flags[@]}" -o "$types"
