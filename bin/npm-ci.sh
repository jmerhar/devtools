#!/usr/bin/env bash
# Install the node_modules of each npm directory devtools.toml lists, or of the one named, exactly
# as its package-lock.json records them.
#
# Runs `npm ci` through the registry npm reaches outside any project. Each directory's .npmrc names
# the public registry, which is what its lockfile records; on a network that proxies npm, that
# registry may be out of reach, so the install goes through the one the machine is configured for.
# `npm ci` never rewrites the lockfile, so whichever registry serves the packages, the committed
# lockfile keeps naming only the public one.
#
#   [npm]
#   dirs = ["frontend"]
#
# Usage: .devtools/bin/npm-ci.sh [DIR]    (from the repository root)
#   NPM   the npm command (default: npm)
set -euo pipefail

here="$(dirname "$0")"
npm="${NPM:-npm}"

if [ $# -gt 0 ]; then
  dirs=("$1")
else
  config=$(python3 "$here/devtools-config.py" --shape list npm.dirs)
  mapfile -t dirs <<< "$config"
  if [ -z "${dirs[0]}" ]; then
    echo "npm-ci: [npm] dirs in devtools.toml is empty" >&2
    exit 1
  fi
fi

# The registry npm reaches outside any project, whose .npmrc would name the public one.
registry=$(cd / && "$npm" config get registry 2>/dev/null) || registry=""
if [ -z "$registry" ] || [ "$registry" = "undefined" ]; then
  registry="https://registry.npmjs.org/"
fi

for dir in "${dirs[@]}"; do
  if [ ! -f "$dir/package-lock.json" ]; then
    echo "npm-ci: $dir has no package-lock.json; make lockfile writes one" >&2
    exit 1
  fi
  echo "npm-ci: installing $dir through $registry"
  (cd "$dir" && "$npm" ci --no-audit --no-fund --registry="$registry")
done
