#!/bin/sh
set -eu

# The API is the only service that applies migrations.  Workers wait for its
# health check, so every container sees the current schema before processing.
if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
  alembic upgrade head
fi

exec "$@"
