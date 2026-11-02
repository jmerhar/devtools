#!/usr/bin/env bash
# Regenerate the package-lock.json of each npm directory devtools.toml lists, or of the one named.
#
# Two things this does that a plain `npm install` does not:
#
#  1. It installs inside a Linux container, matching CI and the images the frontends are built in,
#     so the lockfile records the native packages a Linux install needs. A lockfile written on
#     macOS pins darwin builds of native dependencies, and `npm ci` on Linux then has to resolve
#     them again.
#  2. It rewrites every resolved URL to the public registry. On a network that proxies npm, the
#     lockfile otherwise records that proxy's hostname on every line.
#
#   [npm]
#   dirs = ["frontend"]
#   node_image = "node:24-alpine"   # optional
#
# Each directory needs an .npmrc naming the public registry, which goes into the container so any
# other setting it carries applies; the registry this machine reaches is passed on the command line
# and overrides its registry line.
#
# Usage: .devtools/bin/lockfile.sh [DIR]    (from the repository root; needs Docker)
#   DOCKER   the docker command (default: docker)
#   NPM      the npm command asked for the registry (default: npm)
set -euo pipefail

here="$(dirname "$0")"
[ -f "$here/check-lockfile.sh" ] || {
  echo "lockfile: needs $here/check-lockfile.sh; add bin/check-lockfile.sh to [fetch] files" >&2
  exit 1
}
docker="${DOCKER:-docker}"
npm="${NPM:-npm}"
public="https://registry.npmjs.org/"

if [ $# -gt 0 ]; then
  dirs=("$1")
else
  config=$(python3 "$here/devtools-config.py" --shape list npm.dirs)
  mapfile -t dirs <<< "$config"
  if [ -z "${dirs[0]}" ]; then
    echo "lockfile: [npm] dirs in devtools.toml is empty" >&2
    exit 1
  fi
fi
image=$(python3 "$here/devtools-config.py" --default node:24-alpine npm.node_image)

# The registry npm reaches outside any project, whose .npmrc would name the public one.
registry=$(cd / && "$npm" config get registry 2>/dev/null) || registry=""
if [ -z "$registry" ] || [ "$registry" = "undefined" ]; then
  registry="$public"
fi
echo "Installing through: $registry"
echo "Recording:          $public"

for dir in "${dirs[@]}"; do
  if [ ! -f "$dir/package.json" ] || [ ! -f "$dir/.npmrc" ]; then
    echo "lockfile: $dir needs a package.json and an .npmrc naming $public" >&2
    exit 1
  fi
  abs="$(cd "$dir" && pwd)"
  # Written beside the lockfile under another name, so a failed install leaves the committed one.
  new="$dir/package-lock.json.new"
  rm -f "$new"
  "$docker" run --rm \
    -v "$abs/package.json:/app/package.json:ro" \
    -v "$abs/.npmrc:/app/.npmrc:ro" \
    -v "$abs:/output" \
    -w /app \
    "$image" \
    sh -c "npm install --registry='$registry' --no-fund --no-audit --loglevel=error && cp package-lock.json /output/package-lock.json.new" \
    || { rm -f "$new"; exit 1; }

  # A proxied registry records URLs of the form https://<host>/<prefix>/api/npm/<repo>/<pkg>,
  # which the public registry's never take. The pattern is shaped around that path rather than
  # any particular hostname or product.
  sed -E 's|https://[^"]+/api/npm/[^/]+/|'"$public"'|g' "$new" > "$new.tmp"
  rm -f "$new"
  "$here/check-lockfile.sh" "$new.tmp" || { rm -f "$new.tmp"; exit 1; }
  mv "$new.tmp" "$dir/package-lock.json"
  echo "lockfile: regenerated $dir/package-lock.json"
done
