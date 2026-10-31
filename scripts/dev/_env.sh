# Shared defaults for the scripts in this directory. Source, don't execute.
# Every value here is a LOCAL-ONLY default; real deployments read secrets from
# their own environment (see backend/.env.example). Override by exporting the
# variable before calling a script.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PYTHONPATH="${PYTHONPATH:-$REPO_ROOT}"
export LANG="${LANG:-C.UTF-8}"
export ENVIRONMENT="${ENVIRONMENT:-development}"
# Local PostgreSQL credentials. The password is a variable, never a literal
# inside a URL (repo policy enforced by the gitleaks rule database-dsn-with-password).
export POSTGRES_USER="${POSTGRES_USER:-confit}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-confit}"      # local-only default
export POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"
export POSTGRES_PORT="${POSTGRES_PORT:-5432}"
PG_BASE="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}"
export DATABASE_URL="${DATABASE_URL:-$PG_BASE/confit_dev}"
export CONFIT_TEST_DB_URL="${CONFIT_TEST_DB_URL:-$PG_BASE/confit_test}"
export BENCH_DATABASE_URL="${BENCH_DATABASE_URL:-$PG_BASE/confit_bench}"
export SECRET_KEY="${SECRET_KEY:-local-dev-secret-not-for-prod}"
export JWT_REFRESH_SECRET="${JWT_REFRESH_SECRET:-local-dev-refresh-not-for-prod}"
# AI mode. "deterministic" = labelled rule-based matcher, NO model call, honest
# `source=deterministic_fallback`, `ai_generated=false`. "watsonx" = live IBM
# watsonx.ai (needs WATSONX_APIKEY / WATSONX_PROJECT_ID / WATSONX_URL in your
# env or backend/.env). "auto" = watsonx when configured, else deterministic.
export WARDROBE_STYLIST_PROVIDER="${WARDROBE_STYLIST_PROVIDER:-deterministic}"
# Python interpreter: explicit $PY → active virtualenv → repo .venv → ../.venv → python3
if [ -z "${PY:-}" ]; then
  for cand in "${VIRTUAL_ENV:-}/bin/python" "$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/../.venv/bin/python"; do
    [ -x "$cand" ] && PY="$cand" && break
  done
fi
PY="${PY:-$(command -v python3)}"
export PY
