#!/usr/bin/env bash

# II A2A Server Startup Script
# This script starts the A2A server for II Agent platform

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

cd "$REPO_ROOT"

# Parse command-line arguments
SHOW_HELP="false"
CLI_HOST=""
CLI_PORT=""

while [ $# -gt 0 ]; do
  case "$1" in
    --help|-h)
      SHOW_HELP="true"
      shift
      ;;
    --host=*)
      CLI_HOST="${1#*=}"
      shift
      ;;
    --host)
      shift
      if [ $# -eq 0 ]; then
        echo "Error: --host requires a value."
        exit 1
      fi
      CLI_HOST="$1"
      shift
      ;;
    --port=*)
      CLI_PORT="${1#*=}"
      shift
      ;;
    --port)
      shift
      if [ $# -eq 0 ]; then
        echo "Error: --port requires a value."
        exit 1
      fi
      CLI_PORT="$1"
      shift
      ;;
    *)
      echo "Error: Unknown option '$1'."
      echo "Use --help to see available options."
      exit 1
      ;;
  esac
done

# Show help if requested
if [ "$SHOW_HELP" = "true" ]; then
  echo "II A2A Server Startup Script"
  echo ""
  echo "Usage: $0 [options]"
  echo ""
  echo "Options:"
  echo "  --host HOST          Start server on specified HOST (overrides environment variables)"
  echo "  --port PORT          Start server on specified PORT (overrides environment variables)"
  echo "  -h, --help           Show this help message and exit"
  echo ""
  echo "Environment Variables:"
  echo "  A2A_SERVER_HOST     Server host (default: 0.0.0.0)"
  echo "  A2A_SERVER_PORT     Server port (default: 11002)"
  echo "  A2A_LOG_LEVEL       Log level (default: info)"
  echo "  A2A_MAX_WORKERS     Max workers (default: 1)"
  echo "  A2A_TIMEOUT         Timeout in seconds (default: 300)"
  echo "  A2A_PUBLIC_BASE_URL Publicly reachable base URL (optional, e.g. https://agent.example.com/a2a)"
  echo "  A2A_THIRD_PARTY_AGENTS  JSON string with third-party agents config"
  echo "  A2A_ALLOWED_API_KEYS    Comma separated list of API keys (Bearer/X-A2A-API-Key)"
  echo ""
  echo "Examples:"
  echo "  $0                                    # Start with defaults"
  echo "  A2A_SERVER_PORT=11003 $0             # Start on port 11003"
  echo "  A2A_LOG_LEVEL=debug $0               # Start with debug logging"
  echo ""
  exit 0
fi

# Default configuration
DEFAULT_HOST="0.0.0.0"
DEFAULT_PORT="11002"
DEFAULT_LOG_LEVEL="info"
DEFAULT_MAX_WORKERS="1"
DEFAULT_TIMEOUT="300"

# Allow overriding via environment variables
if [ -n "$CLI_PORT" ]; then
  if ! [[ "$CLI_PORT" =~ ^[0-9]+$ ]]; then
    echo "Error: --port must be a positive integer."
    exit 1
  fi
fi

if [ -n "$CLI_HOST" ]; then
  export A2A_SERVER_HOST="$CLI_HOST"
else
  export A2A_SERVER_HOST="${A2A_SERVER_HOST:-$DEFAULT_HOST}"
fi

if [ -n "$CLI_PORT" ]; then
  export A2A_SERVER_PORT="$CLI_PORT"
else
  export A2A_SERVER_PORT="${A2A_SERVER_PORT:-$DEFAULT_PORT}"
fi

export A2A_LOG_LEVEL="${A2A_LOG_LEVEL:-$DEFAULT_LOG_LEVEL}"
export A2A_MAX_WORKERS="${A2A_MAX_WORKERS:-$DEFAULT_MAX_WORKERS}"
export A2A_TIMEOUT="${A2A_TIMEOUT:-$DEFAULT_TIMEOUT}"

echo "Starting II A2A Server..."
echo "Host: $A2A_SERVER_HOST"
echo "Port: $A2A_SERVER_PORT"
echo "Log Level: $A2A_LOG_LEVEL"
echo "Max Workers: $A2A_MAX_WORKERS"
echo "Timeout: $A2A_TIMEOUT"

# Resolve uv command for the project's managed Python environment
UV_BIN="${UV_BIN:-uv}"
if ! command -v "$UV_BIN" >/dev/null 2>&1; then
  echo "Error: uv is not installed or not in PATH"
  exit 1
fi
echo "Using uv command: $UV_BIN"

# Check if the A2A module can be imported
echo "Checking A2A module availability..."
if ! "$UV_BIN" run python -c "from ii_agent.a2a.config import A2AConfig" >/dev/null 2>&1; then
  echo "Error: Cannot import A2A module. Make sure you're in the correct directory."
  exit 1
fi

# Check if required dependencies are available
echo "Checking dependencies..."
if ! "$UV_BIN" run python -c "import uvicorn" >/dev/null 2>&1; then
  echo "Error: uvicorn is not installed in the uv environment."
  exit 1
fi

# Check if a2a-sdk is available
if ! "$UV_BIN" run python -c "import a2a" >/dev/null 2>&1; then
  echo "Error: a2a-sdk is not installed in the uv environment."
  exit 1
fi

# Resolve the public Agent Card URL using the Python helper (falls back on failure)
CARD_BASE_URL=""
if CARD_BASE_URL=$("$UV_BIN" run python - <<'PY'
from ii_agent.a2a.config import A2AConfig
from ii_agent.a2a.__main__ import resolve_agent_card_base_url

config = A2AConfig()
print(resolve_agent_card_base_url(config), end="")
PY
); then
  CARD_URL="${CARD_BASE_URL%/}/.well-known/agent-card.json"
else
  CARD_URL="http://$A2A_SERVER_HOST:$A2A_SERVER_PORT/.well-known/agent-card.json"
fi

# Start the A2A server
echo "Starting A2A server..."
echo "Agent Card will be available at: $CARD_URL"
echo "Press Ctrl+C to stop the server"
echo ""

# Pass environment variables to Python module
export A2A_SERVER_HOST
export A2A_SERVER_PORT
export A2A_LOG_LEVEL
export A2A_MAX_WORKERS
export A2A_TIMEOUT
export A2A_THIRD_PARTY_AGENTS
export A2A_ALLOWED_API_KEYS

exec "$UV_BIN" run python -m ii_agent.a2a
