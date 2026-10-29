#!/usr/bin/env bash
# Native (no Docker) PostgreSQL for local development. Verified 2026-10-29 on
# Debian 13 / PostgreSQL 17.11 inside a 2 GB sandbox without Docker.
#   apt-get install postgresql        (Debian/Ubuntu)   brew install postgresql@17 (macOS)
# Data dir defaults to $HOME/.confit-pgdata; port 5432; listens on 127.0.0.1 only.
set -euo pipefail
PGDATA="${PGDATA:-$HOME/.confit-pgdata}"
PGPORT="${PGPORT:-5432}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-confit}"   # local-only default; override for anything shared
PGBIN="${PGBIN:-$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1 || true)}"
[ -n "$PGBIN" ] || PGBIN="$(dirname "$(command -v pg_ctl)")"
export LANG=C.UTF-8
if [ ! -f "$PGDATA/PG_VERSION" ]; then
  echo "[pg] initdb → $PGDATA (UTF8, C.UTF-8 — the seed contains Arabic)"
  "$PGBIN/initdb" -D "$PGDATA" -E UTF8 --locale=C.UTF-8 -U postgres >/dev/null
fi
# unix_socket_directories=/tmp avoids needing write access to /var/run/postgresql
if "$PGBIN/pg_ctl" -D "$PGDATA" status >/dev/null 2>&1; then
  echo "[pg] already running (PGDATA=$PGDATA)"
else
  "$PGBIN/pg_ctl" -D "$PGDATA" -l "$PGDATA/pg.log" \
    -o "-p $PGPORT -c listen_addresses=127.0.0.1 -c unix_socket_directories=/tmp" start
fi
"$PGBIN/psql" -h 127.0.0.1 -p "$PGPORT" -U postgres -v ON_ERROR_STOP=0 -q <<SQL
DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='confit') THEN
  CREATE ROLE confit LOGIN PASSWORD '${POSTGRES_PASSWORD}' SUPERUSER; END IF; END \$\$;
SQL
for db in confit_dev confit_test confit_bench; do
  "$PGBIN/psql" -h 127.0.0.1 -p "$PGPORT" -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1 \
    || "$PGBIN/psql" -h 127.0.0.1 -p "$PGPORT" -U postgres -qc "CREATE DATABASE $db OWNER confit ENCODING 'UTF8' TEMPLATE template0 LC_COLLATE 'C.UTF-8' LC_CTYPE 'C.UTF-8'"
done
echo "[pg] ready on 127.0.0.1:$PGPORT — databases confit_dev, confit_test, confit_bench (role confit; password from POSTGRES_PASSWORD, local default)"
echo "[pg] stop with: $PGBIN/pg_ctl -D $PGDATA stop"
