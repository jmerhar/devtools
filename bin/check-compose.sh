#!/usr/bin/env bash
# Check that every compose stack the repository runs resolves and validates.
#
# Catches a typo in a compose file before a deployment does. The stacks are the combinations of
# files passed together with -f, listed in devtools.toml:
#
#   [compose]
#   stacks = [
#     ["docker-compose.yml"],
#     ["docker-compose.yml", "docker-compose.build.yml"],
#   ]
#
# Usage: .devtools/bin/check-compose.sh    (from the repository root)
#   DOCKER   the docker command (default: docker)
set -euo pipefail

here="$(dirname "$0")"
docker="${DOCKER:-docker}"

# Read into a variable first: a process substitution would hide the reader's exit status.
config=$(python3 "$here/devtools-config.py" --shape lists compose.stacks)
mapfile -t stacks <<< "$config"
if [ -z "${stacks[0]}" ]; then
  echo "check-compose: [compose] stacks in devtools.toml is empty" >&2
  exit 1
fi

for stack in "${stacks[@]}"; do
  IFS=$'\t' read -ra files <<< "$stack"
  args=()
  for file in "${files[@]}"; do
    args+=(-f "$file")
  done
  "$docker" compose "${args[@]}" config -q
  echo "check-compose: ${files[*]} is valid"
done
