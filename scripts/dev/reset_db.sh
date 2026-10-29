#!/usr/bin/env bash
# Wipe and rebuild the LOCAL dev database: drop schema → migrate → the API
# re-seeds the demo catalogue on its next start (only because the DB is empty).
# Refuses to run unless the DSN points at localhost and ENVIRONMENT=development.
set -euo pipefail; source "$(dirname "$0")/_env.sh"; cd "$REPO_ROOT"
case "$DATABASE_URL" in *127.0.0.1*|*localhost*) ;; *) echo "refusing: DATABASE_URL is not local" >&2; exit 2;; esac
[ "$ENVIRONMENT" = development ] || { echo "refusing: ENVIRONMENT=$ENVIRONMENT" >&2; exit 2; }
"$PY" - <<'PYEOF'
import os, sqlalchemy as sa
from backend.app.core.postgres_url import normalise_postgres_url  # driver policy: URL always names the driver
url, connect_args = normalise_postgres_url(os.environ["DATABASE_URL"])
e = sa.create_engine(url, connect_args=connect_args, isolation_level="AUTOCOMMIT")
with e.connect() as c:
    c.execute(sa.text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
print("[reset] schema dropped and recreated")
PYEOF
exec "$(dirname "$0")/migrate.sh"
