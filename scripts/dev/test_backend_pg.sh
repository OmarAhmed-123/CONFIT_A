#!/usr/bin/env bash
# Run backend tests against the local PostgreSQL test database instead of SQLite.
# Usage: scripts/dev/test_backend_pg.sh [pytest args…]   (default: stylist suites)
set -euo pipefail; source "$(dirname "$0")/_env.sh"; cd "$REPO_ROOT"
export ENVIRONMENT=test
exec "$PY" -m pytest -q -p no:cacheprovider "${@:-backend/tests/test_stylist_explanation_consistency.py backend/tests/test_watsonx_stylist.py}"
