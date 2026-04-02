#!/bin/bash
set -e

export PATH="/home/user/.bun/bin:/app/ii_agent/.venv/bin:$PATH"

# If running as root, use gosu to switch to user
if [ "$(id -u)" = "0" ]; then
    echo "Switching to user with gosu..."
    exec gosu user "$@"
else
    echo "Already running as non-root user"
    exec "$@"
fi
