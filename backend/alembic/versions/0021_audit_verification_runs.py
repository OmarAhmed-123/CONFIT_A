"""Persisted audit-verification runs — closes the stated tail-truncation limit.

Migration 0020 made single-run verification prove that the *surviving* prefix
of the audit chain is intact, and honestly stated its limit: deleting only the
newest rows (tail truncation) is undetectable within one run, because the
surviving chain still verifies.

This migration closes that limit the way the audit literature recommends:
record every verification outcome as an immutable event. Each run persists
the chain head it observed; the next run checks that the previously recorded
head STILL EXISTS in ``audit_logs`` — if the tail was deleted, the recorded
head is gone and the truncation surfaces as a concrete violation.

``audit_verification_runs`` is append-only by application policy (no ORM
update/delete path exists) and is itself covered by the audit trail: every
integrity check writes an ``ADMIN_AUDIT_INTEGRITY_CHECK`` row, which is
chained like every other row.

Revision: 0021_audit_verification_runs
Revises:  0020_audit_hash_chain
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0021_audit_verification_runs"
down_revision: str = "0020_audit_hash_chain"
branch_labels = None
depends_on = None

TABLE = "audit_verification_runs"


def _tables(bind) -> set:
    from sqlalchemy import inspect
    return set(inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    if TABLE in _tables(bind):
        print(f"[0021] {TABLE} already present — skipping create")
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_at", sa.DateTime(), nullable=False),
        sa.Column("window_days", sa.Integer(), nullable=False),
        sa.Column("checked_rows", sa.Integer(), nullable=False),
        sa.Column("sampled_rows", sa.Integer(), nullable=False),
        sa.Column("chained_rows", sa.Integer(), nullable=False),
        sa.Column("unchained_rows", sa.Integer(), nullable=False),
        sa.Column("break_count", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("tamper_evident", sa.Boolean(), nullable=False),
        # The GLOBAL chain head observed at run time (newest audit_logs row
        # with a hash), not the window head — this is the truncation anchor.
        sa.Column("head_hash", sa.String(length=64), nullable=True),
        sa.Column("head_row_id", sa.Integer(), nullable=True),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.Column("canonical_version", sa.Integer(), nullable=False),
        # Actor + correlation, same enrichment contract as audit_logs.
        sa.Column("triggered_by_user_id", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_audit_verification_runs_run_at", TABLE, ["run_at"])
    print(f"[0021] Created {TABLE}")


def downgrade() -> None:
    bind = op.get_bind()
    if TABLE in _tables(bind):
        op.drop_index("ix_audit_verification_runs_run_at", table_name=TABLE)
        op.drop_table(TABLE)
        print(f"[0021] Dropped {TABLE}")
