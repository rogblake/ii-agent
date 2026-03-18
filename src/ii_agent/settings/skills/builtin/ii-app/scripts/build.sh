#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CRATE_DIR="${SKILL_ROOT}/scripts/ii-app-cli"
TARGET_DIR="/tmp/ii-app-target"
OUT_BIN="${SKILL_ROOT}/bin/ii-app-real"
CARGO_BIN="${CARGO_BIN:-$(command -v cargo || true)}"

if [[ -z "${CARGO_BIN}" && -x /opt/homebrew/bin/cargo ]]; then
  CARGO_BIN="/opt/homebrew/bin/cargo"
fi

if [[ -z "${CARGO_BIN}" ]]; then
  echo "cargo not found. Set CARGO_BIN or install Rust." >&2
  exit 1
fi

"${CARGO_BIN}" build --release --manifest-path "${CRATE_DIR}/Cargo.toml" --target-dir "${TARGET_DIR}"
cp "${TARGET_DIR}/release/ii-app" "${OUT_BIN}"
chmod +x "${OUT_BIN}"
echo "Built ${OUT_BIN}"
