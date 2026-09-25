"""HMAC-chain audit_verification_runs so forged INSERTs are detectable.

0022 enforced append-only storage (REVOKE + UPDATE/DELETE/TRUNCATE triggers),
but the runtime role legitimately retained INSERT. A stolen runtime DB
credential could insert an arbitrary fake verification result. 0023 adds a
domain-separated HMAC chain populated by the AuditVerificationRun mapper
listener. Legacy runs remain NULL and are labelled unsigned; they are never
backfilled or presented as protected-at-creation.

Revision: 0023_verification_run_hmac_chain
Revises:  0022_audit_append_only_guard
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0023_verification_run_hmac_chain"
down_revision: str = "0022_audit_append_only_guard"
branch_labels = None
depends_on = None

TABLE = "audit_verification_runs"


def _columns(bind) -> set[str]:
    from sqlalchemy import inspect
    return {column["name"] for column in inspect(bind).get_columns(TABLE)}


def _indexes(bind) -> set[str]:
    from sqlalchemy import inspect
    return {index["name"] for index in inspect(bind).get_indexes(TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    columns = _columns(bind)
    additions = (
        ("run_prev_hash", sa.String(length=64)),
        ("run_hash", sa.String(length=64)),
        ("run_hmac_key_version", sa.Integer()),
    )
    for name, type_ in additions:
        if name not in columns:
            op.add_column(TABLE, sa.Column(name, type_, nullable=True))
            print(f"[0023] Added {TABLE}.{name}")
    if "ix_audit_verification_runs_run_hash" not in _indexes(bind):
        op.create_index(
            "ix_audit_verification_runs_run_hash", TABLE, ["run_hash"], unique=False
        )
        print("[0023] Created ix_audit_verification_runs_run_hash")


def downgrade() -> None:
    bind = op.get_bind()
    if "ix_audit_verification_runs_run_hash" in _indexes(bind):
        op.drop_index("ix_audit_verification_runs_run_hash", table_name=TABLE)
    columns = _columns(bind)
    for name in ("run_hmac_key_version", "run_hash", "run_prev_hash"):
        if name in columns:
            op.drop_column(TABLE, name)
    print("[0023] Removed verification-run HMAC-chain fields")
