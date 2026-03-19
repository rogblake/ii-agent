#!/bin/sh
set -e

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

cd "$REPO_ROOT"

echo "Starting Xvfb virtual framebuffer..."

Xvfb :99 -screen 0 1280x720x16 &

export DISPLAY=:99

echo "Xvfb started. Display is set to $DISPLAY. Starting application..."

if [ "$#" -gt 0 ] && [ "${1#-}" = "$1" ]; then
  PORT_ARG="$1"
  shift
  set -- --port "$PORT_ARG" "$@"
elif [ -n "${PORT:-}" ]; then
  set -- --port "$PORT" "$@"
fi

exec uv run python -m ii_agent.ws_server "$@"
