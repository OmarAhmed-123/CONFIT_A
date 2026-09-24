"""Database-level append-only guard on the audit tables (PostgreSQL).

Forensic finding that motivated this migration (re-audit of PRs #187-#189):
the production runtime role (``confit_app_rw``) held UPDATE, DELETE and
TRUNCATE on ``audit_logs`` and ``audit_verification_runs`` — proven by
executing (and rolling back) real UPDATE/DELETE/TRUNCATE statements against
the production database with the runtime credential. The HMAC chain from
0020 made tampering *tamper-evident*, but nothing at the database layer
*restricted* it: append-only was an application-code convention.

This migration installs two independent layers (see
backend/app/core/audit_db_guard.py, the single source of the SQL):

1. REVOKE UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER on both audit tables
   from the runtime role (conditional — the role exists on Neon, not in CI).
2. BEFORE UPDATE/DELETE/TRUNCATE triggers that RAISE EXCEPTION regardless
   of role privileges (defence in depth, and protection against accidental
   owner-credential mutations).

Precise trust claim after this migration: the audit tables are
**database-restricted append-only** for the runtime credential and
**tamper-evident** against anyone below the table owner. They are NOT
immutable: the owner can DROP TRIGGER (a DDL act) and mutate — which still
breaks the HMAC chain. External anchoring is the documented next tier.

SQLite (dev): no privilege system, no plpgsql — documented no-op. The guard
is exercised by the PostgreSQL CI jobs and was verified on production.

Revision: 0022_audit_append_only_guard
Revises:  0021_audit_verification_runs
"""
from alembic import op

from backend.app.core.audit_db_guard import guard_install_sql, guard_remove_sql

revision: str = "0022_audit_append_only_guard"
down_revision: str = "0021_audit_verification_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        print("[0022] non-PostgreSQL dialect — append-only guard is a documented no-op")
        return
    for statement in guard_install_sql():
        op.execute(statement)
    print("[0022] append-only guard installed on audit_logs + audit_verification_runs")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for statement in guard_remove_sql():
        op.execute(statement)
    print("[0022] append-only guard removed (pre-0022 grants restored)")
