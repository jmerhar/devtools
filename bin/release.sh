#!/usr/bin/env bash
# Cut a release: .devtools/bin/release.sh X.Y.Z    (from the repository root)
#
# On a clean main, writes X.Y.Z into every manifest and the compose file (see version.py), dates
# CHANGELOG.md's Unreleased section as X.Y.Z's, commits `chore(release): X.Y.Z` and tags it vX.Y.Z
# with "<title> X.Y.Z" and that section as the tag's message, signed when git has a signing key.
# The message is kept verbatim, since git would otherwise strip its `###` headings as comments.
# Nothing is pushed: the last line says how, and CI publishes when the tag arrives.
#
#   [release]
#   title = "My app"                         # the tag message's first line, before the version
#   note = "Run make install to pick it up." # optional, printed after the release
set -euo pipefail

here="$(dirname "$0")"
version="${1:?usage: .devtools/bin/release.sh X.Y.Z}"
[ -f "$here/version.py" ] || {
  echo "release: needs $here/version.py; add bin/version.py to [fetch] files" >&2
  exit 1
}

title=$(python3 "$here/devtools-config.py" release.title)
note=$(python3 "$here/devtools-config.py" --default "" release.note)

if [ -n "$(git status --porcelain)" ]; then
  echo "release: the working tree has changes; commit or stash them first" >&2
  exit 1
fi
if [ "$(git symbolic-ref --short HEAD 2>/dev/null)" != "main" ]; then
  echo "release: releases are cut from main" >&2
  exit 1
fi
if git rev-parse --quiet --verify "refs/tags/v$version" >/dev/null; then
  echo "release: the tag v$version already exists" >&2
  exit 1
fi

# Nothing below leaves a partial release: `set` changes nothing unless the whole release can be
# cut, a failed commit (a hook, signing) restores the files it changed, and a failed tag undoes
# the commit, so the working tree is as it started and the release can be run again.
python3 "$here/version.py" set "$version"
notes=$(python3 "$here/version.py" notes "$version")
if ! git commit --quiet --all --message "chore(release): $version"; then
  git checkout -- .
  echo "release: the commit failed; the files are restored" >&2
  exit 1
fi

sign=(--annotate)
if [ -n "$(git config --get user.signingkey || true)" ]; then
  sign=(--sign)
fi
if ! printf '%s %s\n\n%s\n' "$title" "$version" "$notes" \
  | git tag "${sign[@]}" --cleanup=verbatim "v$version" --file=-; then
  git reset --quiet --hard HEAD~1
  echo "release: tagging failed; the release commit is undone" >&2
  exit 1
fi

echo "Released $version. Publish it with: git push origin main v$version"
if [ -n "$note" ]; then
  echo "$note"
fi
