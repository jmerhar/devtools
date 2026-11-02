#!/usr/bin/env bash
# Run a Bruno collection, with its assertions, against the real API served by the repository's
# fixture server over a throwaway database.
#
#   [bruno]
#   server_dir = "backend"                  # where the server module is run from
#   server = "tests.fixture_server"         # run as `python -m <server> [server_args...] <port>`
#   server_args = ["{scratch}"]             # optional; {scratch} is a directory removed afterwards
#   health = "/api/health"                  # answered once the server is ready
#   folders = ["api"]                       # the collection's folders to run, from bruno/
#   url_var = "base_url"                    # the environment variable given the server's URL
#   env_vars = ["login=lucia"]              # optional, more --env-var values
#   port = 8597                             # optional; BRUNO_PORT overrides it
#   python = "backend/.venv/bin/python"     # optional; PYTHON overrides it
#
# The server and Bruno are stopped and waited for however the run ends, so neither outlives it
# and the port is free again.
#
# Usage: .devtools/bin/test-bruno.sh    (from the repository root; needs Node for the Bruno CLI)
#   NPX    the npx command (default: npx)
#   CURL   the curl command the readiness probe uses (default: curl)
set -euo pipefail

here="$(dirname "$0")"
npx="${NPX:-npx}"
curl="${CURL:-curl}"
cli="@usebruno/cli@4.2.0"
setting() { python3 "$here/devtools-config.py" "$@"; }

server_dir=$(setting bruno.server_dir)
server=$(setting bruno.server)
server_config=$(setting --shape list --default "" bruno.server_args)
health=$(setting bruno.health)
folders_config=$(setting --shape list bruno.folders)
url_var=$(setting bruno.url_var)
env_config=$(setting --shape list --default "" bruno.env_vars)
port="${BRUNO_PORT:-$(setting --default 8597 bruno.port)}"
python="${PYTHON:-$(setting --default backend/.venv/bin/python bruno.python)}"
mapfile -t folders <<< "$folders_config"
if [ -z "${folders[0]}" ]; then
  echo "test-bruno: [bruno] folders in devtools.toml is empty" >&2
  exit 1
fi
# A path is made absolute, since the server runs from server_dir; a bare command is left to PATH.
case "$python" in
  /*) ;;
  */*) python="$PWD/$python" ;;
esac

scratch=""
server_pid=""
bruno_pid=""
# shellcheck disable=SC2317,SC2329  # run by the EXIT trap
stop() {
  local pid
  for pid in "$bruno_pid" "$server_pid"; do
    [ -n "$pid" ] || continue
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  done
  [ -z "$scratch" ] || rm -rf "$scratch"
}
trap stop EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

server_args=()
while IFS= read -r arg; do
  [ -n "$arg" ] || continue
  if [ "$arg" = "{scratch}" ]; then
    [ -n "$scratch" ] || scratch="$(mktemp -d)"
    arg="$scratch"
  fi
  server_args+=("$arg")
done <<< "$server_config"

root="$PWD"
(cd "$server_dir" && exec "$python" -m "$server" "${server_args[@]}" "$port") &
server_pid=$!

for attempt in $(seq 1 120); do
  # Only our server counts: something else answering on the port while ours has exited is not it.
  if ! kill -0 "$server_pid" 2>/dev/null; then
    echo "test-bruno: the fixture server exited before answering on port $port" >&2
    exit 1
  fi
  "$curl" -fs -o /dev/null "http://127.0.0.1:$port$health" && break
  if [ "$attempt" -eq 120 ]; then
    echo "test-bruno: the fixture server did not answer on port $port" >&2
    exit 1
  fi
  sleep 0.5
done
if ! kill -0 "$server_pid" 2>/dev/null; then
  echo "test-bruno: the fixture server exited before answering on port $port" >&2
  exit 1
fi

args=(--env-var "$url_var=http://127.0.0.1:$port")
while IFS= read -r var; do
  [ -n "$var" ] && args+=(--env-var "$var")
done <<< "$env_config"

cd "$root/bruno"
# In the background and waited for, so a signal to this script reaches the trap at once.
"$npx" --yes "$cli" run "${folders[@]}" -r --env local "${args[@]}" &
bruno_pid=$!
status=0
wait "$bruno_pid" || status=$?
bruno_pid=""
exit "$status"
