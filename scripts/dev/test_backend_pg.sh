#!/usr/bin/env bash
# Run backend tests against the local PostgreSQL test database instead of SQLite.
# Usage: scripts/dev/test_backend_pg.sh [pytest args…]   (default: stylist suites)
set -euo pipefail; source "$(dirname "$0")/_env.sh"; cd "$REPO_ROOT"
export ENVIRONMENT=test
export CONFIT_TEST_DB_URL="${CONFIT_TEST_DB_URL:-postgresql://confit:confit@127.0.0.1:5432/confit_test}"
exec "$PY" -m pytest -q -p no:cacheprovider "${@:-backend/tests/test_stylist_explanation_consistency.py backend/tests/test_watsonx_stylist.py}"
