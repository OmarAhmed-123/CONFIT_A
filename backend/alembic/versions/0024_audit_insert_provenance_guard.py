"""Require HMAC provenance fields on every new audit-table INSERT.

0020/0023 intentionally left chain columns nullable for historical legacy rows.
The verifier classified a NULL row as a bypass only when its id sorted after
the first signed row. Because the runtime credential legitimately retains
INSERT and may supply an explicit primary key, a new unsigned row with a low id
could otherwise masquerade as legacy.

This migration installs BEFORE INSERT triggers on both audit tables. New rows
must carry every chain provenance field; existing NULL legacy rows are not
changed or backfilled. Invalid non-NULL signatures remain detectable by the
normal HMAC/link verifier. PostgreSQL and the official SQLite local mode both
enforce the invariant.

Revision: 0024_audit_insert_provenance_guard
Revises:  0023_verification_run_hmac_chain
"""
from alembic import op

from backend.app.core.audit_insert_guard import (
    insert_guard_install_sql,
    insert_guard_remove_sql,
)

revision: str = "0024_audit_insert_provenance_guard"
down_revision: str = "0023_verification_run_hmac_chain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    statements = insert_guard_install_sql(dialect)
    for statement in statements:
        op.execute(statement)
    if statements:
        print(f"[0024] audit INSERT provenance guards installed ({dialect})")
    else:
        print(f"[0024] unsupported dialect {dialect!r}; no INSERT guard installed")


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    for statement in insert_guard_remove_sql(dialect):
        op.execute(statement)
    print(f"[0024] audit INSERT provenance guards removed ({dialect})")
