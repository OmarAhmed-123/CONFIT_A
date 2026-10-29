#!/usr/bin/env bash
# Apply Alembic migrations to $DATABASE_URL (default: local confit_dev).
set -euo pipefail; source "$(dirname "$0")/_env.sh"; cd "$REPO_ROOT"
"$PY" -m alembic -c backend/alembic.ini upgrade head
"$PY" -m alembic -c backend/alembic.ini current
