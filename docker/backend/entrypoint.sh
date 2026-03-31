#!/bin/bash
set -euo pipefail

MODE="${1:-api}"
shift 2>/dev/null || true

# ---------------------------------------------------------------------------
# Configurable env vars (with sensible defaults)
# ---------------------------------------------------------------------------
GUNICORN_WORKERS="${GUNICORN_WORKERS:-1}"
GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-360}"
GUNICORN_BIND="${GUNICORN_BIND:-0.0.0.0:8000}"

CELERY_APP="${CELERY_APP:-ii_agent.workers.celery.app:celery_app}"
CELERY_CONCURRENCY="${CELERY_CONCURRENCY:-${CELERY_WORKER_CONCURRENCY:-}}"
CELERY_LOGLEVEL="${CELERY_LOGLEVEL:-info}"
CELERY_QUEUES="${CELERY_QUEUES:-default,high_priority,low_priority}"
CELERY_POOL="${CELERY_POOL:-${CELERY_WORKER_POOL:-}}"

FLOWER_PORT="${FLOWER_PORT:-5555}"

# ---------------------------------------------------------------------------
# Mode dispatch
# ---------------------------------------------------------------------------
case "$MODE" in
    api)
        echo "Starting API server (gunicorn + uvicorn workers)..."
        exec gunicorn ii_agent.ws_server:app \
            -k uvicorn.workers.UvicornWorker \
            --workers "$GUNICORN_WORKERS" \
            --timeout "$GUNICORN_TIMEOUT" \
            --bind "$GUNICORN_BIND" \
            "$@"
        ;;
    worker)
        echo "Starting Celery worker..."
        celery_args=(
            celery
            -A "$CELERY_APP"
            worker
            --loglevel="$CELERY_LOGLEVEL"
            --queues="$CELERY_QUEUES"
        )
        if [[ -n "$CELERY_CONCURRENCY" ]]; then
            celery_args+=(--concurrency="$CELERY_CONCURRENCY")
        fi
        if [[ -n "$CELERY_POOL" ]]; then
            celery_args+=(--pool="$CELERY_POOL")
        fi
        exec "${celery_args[@]}" "$@"
        ;;
    beat)
        echo "Starting Celery beat..."
        exec celery -A "$CELERY_APP" beat \
            --loglevel="$CELERY_LOGLEVEL" \
            "$@"
        ;;
    flower)
        echo "Starting Celery Flower..."
        exec celery -A "$CELERY_APP" flower \
            --port="$FLOWER_PORT" \
            "$@"
        ;;
    *)
        echo "Unknown mode '$MODE' — executing as command..."
        exec "$MODE" "$@"
        ;;
esac
