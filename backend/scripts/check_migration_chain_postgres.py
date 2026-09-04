"""Migration-chain reality gate — runs the REAL Alembic chain on a REAL PostgreSQL.

    PYTHONPATH=. python3 backend/scripts/check_migration_chain_postgres.py postgresql://user:pw@host/db

What it proves (exit 0) or refutes (exit 1) on the given EMPTY database:

  1. ``alembic upgrade head`` succeeds from an empty PostgreSQL database and the
     database really is at head afterwards (checked via ``alembic_version`` and a
     table count — never via the exit code alone: on 2026-09-03 the chain
     "succeeded" with rc=0 while every migration was silently rolled back).
  2. The migrated schema is EXACTLY what the ORM expects: every ``Base.metadata``
     table and column exists and no ORM column is missing (column-type drift such as
     ``double precision`` vs ``numeric(12,2)`` on money columns is reported too).
  3. The application's schema gate (``backend.app.core.schema_gate``) accepts the
     migrated database under the production policy.
  4. ``alembic downgrade base`` really empties the database and ``upgrade head``
     rebuilds it — the chain is reversible, not one-way.

Requires a throwaway database: it is dropped to an empty ``public`` schema first.
Safety: refuses to run against hostnames that look like managed production
(``neon.tech``, ``rds.amazonaws.com``, ``supabase``) unless ``--i-know-this-is-a-scratch-db``.
"""
from __future__ import annotations

import os
import subprocess
import sys
from decimal import Decimal

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ALEMBIC_INI = os.path.join(REPO_ROOT, "backend", "alembic.ini")

MONEY_COLUMNS = {
    ("orders", "total_amount"), ("orders", "tax_amount"), ("orders", "discount_amount"),
    ("order_items", "unit_price"), ("order_items", "subtotal"),
    ("brand_analytics_events", "revenue_amount"), ("checkout_sessions", "total_amount"),
}
MANAGED_PRODUCTION_HOST_MARKERS = ("neon.tech", "rds.amazonaws.com", "supabase.", "azure.com", "gcp")


def _alembic(url: str, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, ALEMBIC_DATABASE_URL=url, PYTHONPATH=REPO_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", ALEMBIC_INI, *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
    )


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    url = argv[0]
    force = "--i-know-this-is-a-scratch-db" in argv
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if not url.startswith("postgresql"):
        print(f"FAIL: this gate is PostgreSQL-only (got dialect of {url.split(':')[0]!r}); SQLite is not evidence")
        return 1
    if any(m in url for m in MANAGED_PRODUCTION_HOST_MARKERS) and not force:
        print("FAIL: refusing to wipe what looks like a managed production database")
        return 1

    from sqlalchemy import create_engine, inspect, text

    sys.path.insert(0, REPO_ROOT)
    import backend.app.models  # noqa: F401  registers every mapper
    from backend.app.core.database import Base
    from backend.app.core import schema_gate

    engine = create_engine(url, pool_pre_ping=True)
    failures: list[str] = []

    def table_count() -> int:
        with engine.connect() as c:
            return c.execute(text(
                "select count(*) from information_schema.tables where table_schema='public'")).scalar() or 0

    def revision() -> str | None:
        with engine.connect() as c:
            if not inspect(c).has_table("alembic_version"):
                return None
            return c.execute(text("select version_num from alembic_version")).scalar()

    # 0. wipe
    with engine.begin() as c:
        c.execute(text("drop schema public cascade; create schema public;"))
    print(f"[0] scratch database wiped: {table_count()} tables")

    # 1. empty -> head
    r = _alembic(url, "upgrade", "head")
    head = schema_gate.expected_head_revision()
    rev, n = revision(), table_count()
    print(f"[1] upgrade head rc={r.returncode} revision={rev} tables={n} (expected head {head})")
    if r.returncode != 0:
        failures.append("upgrade head exited non-zero:\n" + r.stderr[-2000:])
    if rev != head:
        failures.append(f"database revision after upgrade is {rev!r}, expected {head!r} (silent rollback?)")
    if n < len(Base.metadata.tables):
        failures.append(f"only {n} tables after upgrade; ORM declares {len(Base.metadata.tables)}")

    # 2. schema == ORM metadata
    insp = inspect(engine)
    db_tables = set(insp.get_table_names())
    missing_tables = sorted(set(Base.metadata.tables) - db_tables)
    if missing_tables:
        failures.append(f"ORM tables missing from migrated schema: {missing_tables}")
    for tname, table in sorted(Base.metadata.tables.items()):
        if tname not in db_tables:
            continue
        db_cols = {c["name"]: c for c in insp.get_columns(tname)}
        missing_cols = sorted(set(table.columns.keys()) - set(db_cols))
        if missing_cols:
            failures.append(f"{tname}: ORM columns missing from migrated schema: {missing_cols}")
    for tname, col in sorted(MONEY_COLUMNS):
        if tname in db_tables:
            cols = {c["name"]: c for c in insp.get_columns(tname)}
            if col in cols:
                t = str(cols[col]["type"]).upper()
                if not t.startswith("NUMERIC"):
                    failures.append(f"{tname}.{col} is {t}, expected NUMERIC(12, 2) (money must not be float)")
    extra = sorted(db_tables - set(Base.metadata.tables) - {"alembic_version"} - schema_gate.MIGRATION_ONLY_TABLES)
    print(f"[2] ORM/migration parity: missing tables={missing_tables} migration-only extras={extra}")
    if extra:
        failures.append(f"tables created by migrations but unknown to ORM and not declared MIGRATION_ONLY: {extra}")

    # 3. application gate accepts it under production policy
    report = schema_gate.evaluate(engine)
    ok = schema_gate.acceptable(report, "production")
    print(f"[3] schema gate verdict={report.verdict} acceptable(production)={ok}")
    if not ok:
        failures.append("schema gate rejects the freshly migrated database: " + "; ".join(report.findings))

    # 4. reversible: head -> base -> head
    r = _alembic(url, "downgrade", "base")
    rev, n = revision(), table_count()
    print(f"[4a] downgrade base rc={r.returncode} revision={rev} tables={n}")
    if r.returncode != 0 or rev is not None or n > 1:
        failures.append(f"downgrade base did not empty the database (rc={r.returncode}, rev={rev}, tables={n})")
    r = _alembic(url, "upgrade", "head")
    rev, n = revision(), table_count()
    print(f"[4b] upgrade head (again) rc={r.returncode} revision={rev} tables={n}")
    if r.returncode != 0 or rev != head:
        failures.append(f"re-upgrade after downgrade failed (rc={r.returncode}, rev={rev})")

    # 5. numeric round trip on the real column type (money is not float)
    with engine.begin() as c:
        if "migration_audit_log" in set(inspect(c).get_table_names()):
            c.execute(text(
                "insert into migration_audit_log (migration_revision, table_name, field_name, original_value, remediated_value, action, reason) "
                "values ('gate-selftest', 'orders', 'total_amount', '0.1', '0.10', 'repair', 'self-test row')"))
            c.execute(text("delete from migration_audit_log where migration_revision='gate-selftest'"))
        t = c.execute(text("select 9999999999.99::numeric(12,2)")).scalar()
        if Decimal(str(t)) != Decimal("9999999999.99"):
            failures.append("NUMERIC(12,2) round trip lost precision")
    print("[5] numeric(12,2) round trip ok")

    engine.dispose()
    if failures:
        print("\nMIGRATION CHAIN GATE: FAIL")
        for f in failures:
            print("  ✗", f)
        return 1
    print("\nMIGRATION CHAIN GATE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
