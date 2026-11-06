#!/usr/bin/env bash
# Check that a frontend-config release tag names the version in frontend-config/package.json and
# that frontend-config/CHANGELOG.md has a dated section for it.
#
# Run by the publish workflow before anything is published.
#
# Usage: tooling/frontend-config-version.sh frontend-config-vX.Y.Z
set -euo pipefail

tag="${1:?usage: tooling/frontend-config-version.sh frontend-config-vX.Y.Z}"
cd "$(dirname "$0")/../frontend-config"
version=$(node -p 'require("./package.json").version')
if [ "$tag" != "frontend-config-v$version" ]; then
  echo "frontend-config-version: the tag is $tag, but package.json names $version" >&2
  exit 1
fi
if ! grep -qE "^## ${version//./\\.} — [0-9]{4}-[0-9]{2}-[0-9]{2}$" CHANGELOG.md; then
  echo "frontend-config-version: CHANGELOG.md has no dated section for $version" >&2
  exit 1
fi
echo "frontend-config-version: $tag matches package.json and CHANGELOG.md"
