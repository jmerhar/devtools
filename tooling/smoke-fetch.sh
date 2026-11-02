#!/usr/bin/env bash
# Fetch every consumer-facing file of this repository from GitHub at a ref, the way a repository
# using devtools does, and check each arrives identical to the working tree. The fetcher itself is
# among them, since the README tells a repository to download it from the same place.
#
# Proves the fetcher's default URLs and this repository's published layout agree, which the bats
# suites cannot: they fetch from file:// stand-ins. CI runs it at the commit being tested, once
# GitHub serves that commit.
#
# Usage: tooling/smoke-fetch.sh REF
set -euo pipefail

ref="${1:?usage: tooling/smoke-fetch.sh REF}"
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

cd "$root"
mapfile -t files < <(git ls-files make config bin fetch)
{
  printf '[fetch]\nref = "%s"\ncoverage = true\nfiles = [\n' "$ref"
  printf '  "%s",\n' "${files[@]}"
  printf ']\n'
} > "$work/devtools.toml"

cd "$work"
"$root/fetch/devtools-fetch.sh"
for f in "${files[@]}"; do
  cmp "$root/$f" ".devtools/$f"
done
test -s .devtools/coverage/coverage-report.py
test -s .devtools/coverage/run-kcov.sh
echo "smoke-fetch: ${#files[@]} files and the coverage tooling fetched intact at $ref"
