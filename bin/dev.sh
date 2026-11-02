#!/usr/bin/env bash
# Start the development stack with hot reload.
#
# Wraps the compose command to hand it the registry npm is configured to reach. Two installs
# happen in a typical stack and neither can be assumed to reach the public registry: the image
# build runs `npm ci` in its frontend stage, and a Vite container runs one of its own on every
# start. Exported rather than passed with --build-arg because compose substitutes it into both.
#
# The compose files come from devtools.toml, and arguments pass through to `compose up`:
#
#   [dev]
#   compose_files = ["docker-compose.yml", "docker-compose.dev.yml"]
#
# Usage: .devtools/bin/dev.sh [compose up arguments]    (from the repository root)
#   DOCKER         the docker command (default: docker)
#   NPM            the npm command (default: npm)
#   NPM_REGISTRY   the registry to install through, instead of the one npm reports
set -euo pipefail

here="$(dirname "$0")"
docker="${DOCKER:-docker}"
npm="${NPM:-npm}"

config=$(python3 "$here/devtools-config.py" --shape list dev.compose_files)
mapfile -t files <<< "$config"
if [ -z "${files[0]}" ]; then
  echo "dev: [dev] compose_files in devtools.toml is empty" >&2
  exit 1
fi
args=()
for file in "${files[@]}"; do
  args+=(-f "$file")
done

# A value set by hand, in the environment or in .env, is the developer's own choice, and compose
# reads .env itself, so it is left alone. npm is asked from / so that a project .npmrc pinning
# the public registry does not hide the one this machine is configured for.
if [ -z "${NPM_REGISTRY:-}" ] && ! grep -qsE '^[[:space:]]*(export[[:space:]]+)?NPM_REGISTRY=' .env; then
  registry=$(cd / && "$npm" config get registry 2>/dev/null) || registry=""
  # npm answers "undefined" when nothing is configured, which is not a URL.
  if [ -n "$registry" ] && [ "$registry" != "undefined" ]; then
    export NPM_REGISTRY="$registry"
    echo "Installing npm packages through: $NPM_REGISTRY"
  fi
fi

exec "$docker" compose "${args[@]}" up --build "$@"
