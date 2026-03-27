#!/bin/bash
set -e

export PATH="/home/user/.bun/bin:/app/ii_sandbox/.venv/bin:$PATH"
export II_APP_SKILL_ROOT=/usr/local/share/ii-app

# If running as root, use gosu to switch to user
if [ "$(id -u)" = "0" ]; then
    echo "Switching to user with gosu..."
    exec gosu user "$@"
else
    echo "Already running as non-root user"
    exec "$@"
fi
