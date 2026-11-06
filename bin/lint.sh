#!/usr/bin/env bash
# Run every check that needs nothing but a clone, and report all their failures in one pass.
#
# Which checks run is listed in devtools.toml; `extra` adds the repository's own commands, each
# run with bash from the repository root:
#
#   [lint]
#   checks = ["shellcheck", "ruff", "lockfile", "version", "compose"]
#   ruff = "backend/.venv/bin/ruff"       # optional; RUFF overrides it (default: ruff)
#   extra = [
#     ["frontend types", "cd frontend && npx tsc -b --force"],
#   ]
#
# The checks:
#   - shellcheck: ShellCheck over bin/*.sh
#   - ruff: ci-ruff.sh
#   - lockfile: check-lockfile.sh
#   - version: version.py check, against the tag RELEASE_TAG names when it is set
#   - compose: check-compose.sh
#
# Usage: .devtools/bin/lint.sh    (from the repository root)
set -uo pipefail

here="$(dirname "$0")"

checks_config=$(python3 "$here/devtools-config.py" --shape list lint.checks) || exit 1
extra_config=$(python3 "$here/devtools-config.py" --shape lists --default "" lint.extra) || exit 1
ruff="${RUFF:-$(python3 "$here/devtools-config.py" --default ruff lint.ruff)}" || exit 1

mapfile -t checks <<< "$checks_config"
# Each check and the script beside this one it runs.
declare -A needs=([ruff]=ci-ruff.sh [lockfile]=check-lockfile.sh [version]=version.py [compose]=check-compose.sh)
for check in "${checks[@]}"; do
  case "$check" in
    shellcheck | ruff | lockfile | version | compose | "") ;;
    *)
      echo "lint: unknown check '$check' in [lint] checks" >&2
      exit 1
      ;;
  esac
  script="${needs[$check]:-}"
  if [ -n "$script" ] && [ ! -f "$here/$script" ]; then
    echo "lint: the $check check needs $here/$script; add bin/$script to [fetch] files" >&2
    exit 1
  fi
done

status=0
run() {
  printf '\n\033[1m--- %s ---\033[0m\n' "$1"
  shift
  "$@" || status=1
}

for check in "${checks[@]}"; do
  case "$check" in
    shellcheck)
      shopt -s nullglob
      scripts=(bin/*.sh)
      shopt -u nullglob
      if [ ${#scripts[@]} -gt 0 ]; then
        run "shellcheck" shellcheck "${scripts[@]}"
      else
        run "shellcheck" echo "no scripts in bin/"
      fi
      ;;
    ruff) run "ruff" env RUFF="$ruff" "$here/ci-ruff.sh" ;;
    lockfile) run "lockfile registry" "$here/check-lockfile.sh" ;;
    version) run "versions agree" python3 "$here/version.py" check ${RELEASE_TAG:+"$RELEASE_TAG"} ;;
    compose) run "compose files parse" "$here/check-compose.sh" ;;
  esac
done

while IFS=$'\t' read -r name command rest; do
  [ -n "$name" ] || continue
  if [ -z "$command" ] || [ -n "$rest" ]; then
    echo "lint: [lint] extra entry '$name' needs exactly a name and a command" >&2
    status=1
    continue
  fi
  run "$name" bash -c "$command"
done <<< "$extra_config"

exit "$status"
