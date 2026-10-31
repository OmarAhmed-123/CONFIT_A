#!/usr/bin/env bash
# Boots a deterministic stack and runs the browser E2E journey (en + ar).
#
#   PostgreSQL (E2E_DATABASE_URL, throwaway) → alembic upgrade head
#   backend  : uvicorn, ENVIRONMENT=test, WARDROBE_STYLIST_PROVIDER=deterministic
#              (never a model call; results are labelled `deterministic`)
#   frontend : vite preview of frontend/dist (its /api proxy → backend :8000)
#   runner   : node scripts/qa/e2e_stylist_browser.mjs
#
# Usage (repo root, after `cd frontend && npm ci && npm run build` and
# `pip install -r backend/requirements.txt`):
#   E2E_DATABASE_URL="postgresql://confit:${POSTGRES_PASSWORD}@localhost:5432/confit_e2e" bash scripts/qa/e2e_stylist_browser.sh
# Env: E2E_OUT (artifacts, default ./e2e-artifacts), E2E_WEB_PORT (43123),
#      E2E_API_PORT (8000), PY (python interpreter), PW_EXECUTABLE (optional).
# Exit status is the runner's: 0 only when every check passed in both languages.
set -uo pipefail
cd "$(dirname "$0")/../.."

: "${E2E_DATABASE_URL:?E2E_DATABASE_URL (throwaway PostgreSQL DSN) is required}"
PY="${PY:-python3}"
OUT="${E2E_OUT:-$PWD/e2e-artifacts}"
case "$OUT" in /*) ;; *) OUT="$PWD/$OUT" ;; esac   # absolute: the preview runs from frontend/
WEB_PORT="${E2E_WEB_PORT:-43123}"
API_PORT="${E2E_API_PORT:-8000}"
mkdir -p "$OUT"

if [ ! -f frontend/dist/index.html ]; then
  echo "e2e: frontend/dist missing — run 'npm run build' in frontend/ first" >&2; exit 2
fi

export ENVIRONMENT=test
export DATABASE_URL="$E2E_DATABASE_URL"
export WARDROBE_STYLIST_PROVIDER=deterministic
export WARDROBE_VISION_PROVIDER=legacy
export AUTH_COOKIE_SECURE="${AUTH_COOKIE_SECURE:-false}"
unset WATSONX_APIKEY WATSONX_PROJECT_ID 2>/dev/null || true

echo "e2e: migrating throwaway database to head"
PYTHONPATH=. "$PY" -m alembic -c backend/alembic.ini upgrade head > "$OUT/alembic.log" 2>&1 || { tail -n 40 "$OUT/alembic.log"; exit 2; }

PYTHONPATH=. "$PY" -m uvicorn backend.app.main:app --host 127.0.0.1 --port "$API_PORT" --log-level warning > "$OUT/backend.log" 2>&1 &
API_PID=$!
( cd frontend && ./node_modules/.bin/vite preview --host 127.0.0.1 --port "$WEB_PORT" --strictPort > "$OUT/preview.log" 2>&1 ) &
WEB_PID=$!
cleanup() { kill "$API_PID" "$WEB_PID" 2>/dev/null; pkill -P "$WEB_PID" 2>/dev/null; wait "$API_PID" "$WEB_PID" 2>/dev/null; }
trap cleanup EXIT

for _ in $(seq 1 90); do
  curl -fsS "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1 && curl -fsS "http://127.0.0.1:$WEB_PORT/" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS "http://127.0.0.1:$API_PORT/health" >/dev/null || { echo "e2e: backend did not come up"; tail -n 40 "$OUT/backend.log"; exit 2; }
curl -fsS "http://127.0.0.1:$WEB_PORT/" >/dev/null || { echo "e2e: preview did not come up"; tail -n 20 "$OUT/preview.log"; exit 2; }

BASE_URL="http://127.0.0.1:$WEB_PORT" API_URL="http://127.0.0.1:$API_PORT" OUT_DIR="$OUT" node scripts/qa/e2e_stylist_browser.mjs
status=$?
[ "$status" -eq 0 ] || { echo "--- backend log (tail)"; tail -n 40 "$OUT/backend.log"; }
echo "e2e: result=$([ "$status" -eq 0 ] && echo PASS || echo FAIL)"
exit "$status"
