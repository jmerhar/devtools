#!/usr/bin/env bash
# Archive a built site as the tar GitHub Pages deploys, keeping its hidden files.
#
# A site's hidden files, such as .well-known/assetlinks.json, are part of it, so they stay; links
# are replaced by what they point to, and .git and .github are left out.
#
# Usage: .devtools/bin/pages-artifact.sh SITE_DIR ARCHIVE
set -euo pipefail

site="${1:?usage: pages-artifact.sh SITE_DIR ARCHIVE}"
archive="${2:?usage: pages-artifact.sh SITE_DIR ARCHIVE}"
if [ ! -d "$site" ] || [ -z "$(ls -A "$site")" ]; then
  echo "pages-artifact: $site is missing or empty; the build wrote no site" >&2
  exit 1
fi
# GNU tar, as on CI's runners, also stores each hard link as a file; BSD tar has no such option.
links=(--dereference)
if tar --version 2>/dev/null | grep -q 'GNU tar'; then
  links+=(--hard-dereference)
fi
tar "${links[@]}" --exclude=.git --exclude=.github -cf "$archive" -C "$site" .
echo "pages-artifact: archived $site into $archive"
