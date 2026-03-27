#!/usr/bin/env bash
set -euo pipefail

project_dir=""
cache_path=""
declare -a ports=()

cleanup_dir_if_empty() {
  local dir="$1"
  if [[ -n "$dir" && -d "$dir" ]]; then
    rmdir "$dir" >/dev/null 2>&1 || true
  fi
}

safe_remove_path() {
  local path="$1"
  if [[ -z "$path" || "$path" == "/" ]]; then
    return 0
  fi
  if [[ -e "$path" ]]; then
    rm -rf "$path"
  fi
}

kill_port_if_listening() {
  local port="$1"
  if ! command -v lsof >/dev/null 2>&1; then
    return 0
  fi

  local pids
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    return 0
  fi

  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    kill "$pid" >/dev/null 2>&1 || true
  done <<< "$pids"

  sleep 1

  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    return 0
  fi

  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    kill -9 "$pid" >/dev/null 2>&1 || true
  done <<< "$pids"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-dir)
      project_dir="${2:-}"
      shift 2
      ;;
    --cache-path)
      cache_path="${2:-}"
      shift 2
      ;;
    --port)
      ports+=("${2:-}")
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

for port in "${ports[@]}"; do
  [[ -n "$port" ]] || continue
  kill_port_if_listening "$port"
done

if [[ -n "$cache_path" ]]; then
  safe_remove_path "$cache_path"
  cleanup_dir_if_empty "$(dirname "$cache_path")"
fi

safe_remove_path "$project_dir"
