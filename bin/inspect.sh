#!/usr/bin/env bash
# Run IntelliJ IDEA's inspections offline, and fail if any inspection reports a problem.
#
# Runs beside an open IDE: an idea.properties isolates the system and log paths (lock files,
# caches), and leaves the config path shared, so the headless run has the same plugins, SDKs and
# settings as the IDE and reports the same problems. Results land in inspect/, one XML file per
# inspection that found something.
#
#   [inspect]
#   ignore = ["UndefinedAction"]     # optional: inspections whose findings are headless-only
#
# Usage: .devtools/bin/inspect.sh    (from the repository root)
#   IDEA_INSPECT   IntelliJ's inspect.sh (default: the one in /Applications/IntelliJ IDEA.app)
set -euo pipefail

here="$(dirname "$0")"
inspect="${IDEA_INSPECT:-/Applications/IntelliJ IDEA.app/Contents/bin/inspect.sh}"
project="$PWD"
profile="$project/.idea/inspectionProfiles/Project_Default.xml"
xml="$project/inspect/xml"
idea="$project/inspect/idea"

ignore_config=$(python3 "$here/devtools-config.py" --shape list --default "" inspect.ignore)
if [ ! -x "$inspect" ]; then
  echo "inspect: IntelliJ IDEA's inspect.sh is not at $inspect; set IDEA_INSPECT" >&2
  exit 1
fi

properties="$(mktemp)"
trap 'rm -f "$properties"' EXIT
printf 'idea.system.path=%s/system\nidea.log.path=%s/log\n' "$idea" "$idea" > "$properties"
export IDEA_PROPERTIES="$properties"

rm -rf "$xml" "$idea"
mkdir -p "$xml" "$idea"
echo "Running IntelliJ inspections..."
# Its stderr is mostly startup noise, so it is kept in a log and shown only when the run fails.
if ! "$inspect" "$project" "$profile" "$xml" -v0 2> "$idea/stderr.log"; then
  echo "inspect: IntelliJ's inspect.sh failed; the end of its log ($idea/stderr.log):" >&2
  tail -20 "$idea/stderr.log" >&2
  exit 1
fi

while IFS= read -r name; do
  [ -n "$name" ] && rm -f "$xml/$name.xml"
done <<< "$ignore_config"

shopt -s nullglob
found=("$xml"/*.xml)
if [ ${#found[@]} -gt 0 ]; then
  echo "inspect: ${#found[@]} inspection(s) found problems:"
  for f in "${found[@]}"; do
    echo "  $(basename "$f" .xml)"
  done
  exit 1
fi
echo "inspect: no problems found"
