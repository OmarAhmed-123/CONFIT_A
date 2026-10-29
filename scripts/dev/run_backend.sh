#!/usr/bin/env bash
# FastAPI on http://0.0.0.0:8000 against the local PostgreSQL.
# First start on an empty database seeds the demo catalogue (one worker only —
# several workers racing on an empty DB produce a harmless but noisy warning).
set -euo pipefail; source "$(dirname "$0")/_env.sh"; cd "$REPO_ROOT"
echo "[api] DATABASE_URL=${DATABASE_URL%%@*}@…  WARDROBE_STYLIST_PROVIDER=$WARDROBE_STYLIST_PROVIDER"
exec "$PY" -m uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT:-8000}" "${@:---reload}"
