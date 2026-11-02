#!/usr/bin/env bash
# Create the GitHub release for a pushed tag, from its CHANGELOG.md section, titled
# "<[release] title> X.Y.Z" (see release.sh).
#
# Usage: .devtools/bin/github-release.sh vX.Y.Z    (from the repository root)
#   Needs gh, authenticated with GH_TOKEN.
#   GH   the gh command (default: gh)
set -euo pipefail

here="$(dirname "$0")"
[ -f "$here/version.py" ] || {
  echo "github-release: needs $here/version.py; add bin/version.py to [fetch] files" >&2
  exit 1
}
gh="${GH:-gh}"
tag="${1:?usage: .devtools/bin/github-release.sh vX.Y.Z}"
version="${tag#v}"

title=$(python3 "$here/devtools-config.py" release.title)
python3 "$here/version.py" check "$tag"
# A re-run of the workflow finds the release already made, and leaves it.
if "$gh" release view "$tag" >/dev/null 2>&1; then
  echo "github-release: $tag already has a release"
  exit 0
fi
notes=$(python3 "$here/version.py" notes "$version")
printf '%s\n' "$notes" \
  | "$gh" release create "$tag" --verify-tag --title "$title $version" --notes-file -
