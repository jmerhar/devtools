#!/usr/bin/env bash
# Check that every package in the repository's npm lockfiles resolves to the public registry.
#
# Written as a positive assertion rather than a list of hostnames to reject: a check that named
# the private registries it looked for would publish those names. `npm install` on a network that
# proxies npm records the proxy's hostname on every line of the lockfile, so this is easy to do by
# accident and invisible in review.
#
# Checks the lockfile of each directory devtools.toml lists, which must exist, and every other
# package-lock.json git tracks:
#
#   [npm]
#   dirs = ["frontend"]    # optional when every lockfile is tracked
#
# A workspace package's entry resolves to a path in the repository rather than a URL, and passes.
#
# Usage: .devtools/bin/check-lockfile.sh [LOCKFILE...]    (from the repository root)
#   With arguments, only the named lockfiles are checked.
set -euo pipefail

here="$(dirname "$0")"
public="https://registry.npmjs.org/"

if [ $# -gt 0 ]; then
  lockfiles=("$@")
else
  config=$(python3 "$here/devtools-config.py" --shape list --default "" npm.dirs)
  lockfiles=()
  declare -A seen=()
  while IFS= read -r dir; do
    [ -n "$dir" ] || continue
    lockfiles+=("$dir/package-lock.json")
    seen["$dir/package-lock.json"]=1
  done <<< "$config"
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    tracked=$(git ls-files -- '*package-lock.json')
    while IFS= read -r path; do
      [ -n "$path" ] && [ -z "${seen[$path]:-}" ] && lockfiles+=("$path")
    done <<< "$tracked"
  fi
fi

if [ ${#lockfiles[@]} -eq 0 ]; then
  echo "check-lockfile: no lockfiles to check; list the npm directories in [npm] dirs" >&2
  exit 1
fi

fail=0
for lockfile in "${lockfiles[@]}"; do
  if [ ! -f "$lockfile" ]; then
    echo "check-lockfile: $lockfile is missing; regenerate it with .devtools/bin/lockfile.sh" >&2
    fail=1
    continue
  fi
  # Compared as a literal prefix, so a lookalike host (registry.npmjs.org.example) cannot pass.
  foreign=()
  while IFS= read -r url; do
    [[ "$url" == "$public"* || "$url" != *://* ]] || foreign+=("$url")
  done < <(grep -oE '"resolved": *"[^"]+"' "$lockfile" | sed -E 's/"resolved": *"//; s/"$//')
  if [ ${#foreign[@]} -gt 0 ]; then
    echo "check-lockfile: $lockfile resolves packages somewhere other than $public:" >&2
    # Only the scheme and host, once each: enough to act on without echoing every path.
    printf '%s\n' "${foreign[@]}" | sed -E 's|^([a-z+]+://[^/]+).*|  \1/…|' | sort -u >&2
    fail=1
  fi
done

if [ "$fail" -ne 0 ]; then
  echo "check-lockfile: regenerate with .devtools/bin/lockfile.sh, which rewrites the URLs" >&2
  exit 1
fi
echo "check-lockfile: ${#lockfiles[@]} lockfile(s) resolve only to the public registry"
