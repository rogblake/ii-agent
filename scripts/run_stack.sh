#!/usr/bin/env bash

#Set up
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)

echo "Using $ROOT_DIR"
COMPOSE_FILE="$ROOT_DIR/docker/docker-compose.stack.yaml"
ENV_FILE="$ROOT_DIR/docker/.stack.env"
ENV_EXAMPLE="$ROOT_DIR/docker/.stack.env.example"
PROJECT_NAME=${COMPOSE_PROJECT_NAME:-ii-agent-stack}
BUILD_FLAG=""

usage() {
  cat <<USAGE
Usage: scripts/run_stack.sh [--build]
  --build    Force Docker to rebuild images before starting services
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "${1:-}" == "--build" ]]; then
  BUILD_FLAG="--build"
  shift || true
fi

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  echo "Created $ENV_FILE from template. Populate it with real credentials before rerunning." >&2
  exit 1
fi

compose() {
  docker compose --project-name "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

compose_up() {
  compose up -d ${BUILD_FLAG:+$BUILD_FLAG} "$@"
}

get_env_value() {
  local key=$1
  local default=${2:-}
  local value
  value=$(grep -E "^${key}=" "$ENV_FILE" | tail -n1 | cut -d '=' -f 2- || true)
  if [[ -z "$value" ]]; then
    printf '%s' "$default"
  else
    printf '%s' "$value"
  fi
}

update_env_value() {
  local key=$1
  local value=$2
  python3 - "$ENV_FILE" "$key" "$value" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]

lines = []
found = False
for raw_line in path.read_text().splitlines():
    if not raw_line.strip() or raw_line.strip().startswith('#'):
        lines.append(raw_line)
        continue
    name, sep, current = raw_line.partition('=')
    if name == key:
        lines.append(f"{key}={value}")
        found = True
    else:
        lines.append(raw_line)

if not found:
    lines.append(f"{key}={value}")

path.write_text("\n".join(lines).rstrip() + "\n")
PY
}

strip_wrapping_quotes() {
  local value=$1

  if [[ "$value" == \"*\" && "$value" == *\" ]]; then
    value=${value:1:${#value}-2}
  elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
    value=${value:1:${#value}-2}
  fi

  printf '%s' "$value"
}

resolve_repo_host_path() {
  local raw_value=$1
  local path_value
  path_value=$(strip_wrapping_quotes "$raw_value")

  if [[ -z "$path_value" ]]; then
    return 0
  fi

  if [[ "$path_value" == /* ]]; then
    printf '%s' "$path_value"
  else
    printf '%s' "$ROOT_DIR/${path_value#./}"
  fi
}

ensure_google_credentials_mount_path() {
  local current_credentials_path
  current_credentials_path=$(get_env_value GOOGLE_APPLICATION_CREDENTIALS)

  if [[ -z "$current_credentials_path" ]]; then
    return
  fi

  local resolved_credentials_path
  resolved_credentials_path=$(resolve_repo_host_path "$current_credentials_path")

  if [[ "$resolved_credentials_path" != "$current_credentials_path" ]]; then
    update_env_value GOOGLE_APPLICATION_CREDENTIALS "$resolved_credentials_path"
    echo "Resolved GOOGLE_APPLICATION_CREDENTIALS to $resolved_credentials_path in $ENV_FILE"
  fi

  if [[ -d "$resolved_credentials_path" ]]; then
    echo "GOOGLE_APPLICATION_CREDENTIALS must point to a file, but resolved to a directory: $resolved_credentials_path" >&2
    exit 1
  fi

  if [[ ! -f "$resolved_credentials_path" ]]; then
    echo "GOOGLE_APPLICATION_CREDENTIALS file not found: $resolved_credentials_path" >&2
    exit 1
  fi
}

ensure_frontend_build_env() {
  local backend_port
  backend_port=$(get_env_value BACKEND_PORT 8000)
  local default_api_url="http://localhost:${backend_port}"
  local current_api_url
  current_api_url=$(get_env_value VITE_API_URL)
  if [[ -z "$current_api_url" ]]; then
    update_env_value VITE_API_URL "$default_api_url"
    echo "Defaulted VITE_API_URL to $default_api_url in $ENV_FILE"
  fi
}

ensure_frontend_build_env
ensure_google_credentials_mount_path

# Start shared infrastructure first.
compose_up postgres redis

# Start the application services after the shared infrastructure is up.
compose_up backend
compose_up celery
compose_up frontend

frontend_port=$(get_env_value FRONTEND_PORT 1420)
backend_port=$(get_env_value BACKEND_PORT 8000)

cat <<SUMMARY
Stack is running (project name: $PROJECT_NAME)
  Frontend:             http://localhost:${frontend_port}
  Backend:              http://localhost:${backend_port}
  Celery worker:        docker compose logs -f celery

Use 'docker compose --project-name $PROJECT_NAME -f docker/docker-compose.stack.yaml ps' to inspect containers.
SUMMARY
