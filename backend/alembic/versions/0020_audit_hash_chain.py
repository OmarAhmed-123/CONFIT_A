"""Tamper-evident audit chain — closes the P0 from the 2026-09-22 audit.

Adds three nullable columns to ``audit_logs``:

* ``prev_hash``          — entry_hash of the previous row (64-zero genesis
                           for the first chained row),
* ``entry_hash``         — HMAC-SHA256 over the canonical row content +
                           prev_hash (see backend/app/core/audit_chain.py),
* ``chain_key_version``  — which HMAC key signed this row, so key rotation
                           never invalidates history.

Deliberately **no backfill**: rows written before this migration were never
covered by any integrity mechanism, and signing them now would fabricate a
guarantee that did not exist when they were written. They stay NULL and the
integrity endpoint reports them separately as ``unchained_rows`` (honest
legacy), while every row from this migration forward is chained by the
mapper-level ``before_insert`` listener.

Additive-only and idempotent (same replay-safety pattern as 0017): existing
rows keep NULL, no existing column changes, downgrade is a clean column drop.

Revision: 0020_audit_hash_chain
Revises:  0019_brand_tenant_integrity_and_ad_ledger
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0020_audit_hash_chain"
down_revision: str = "0019_brand_tenant_integrity_and_ad_ledger"
branch_labels = None
depends_on = None

TABLE = "audit_logs"
COLUMNS = {
    "prev_hash": sa.Column("prev_hash", sa.String(length=64), nullable=True),
    "entry_hash": sa.Column("entry_hash", sa.String(length=64), nullable=True),
    "chain_key_version": sa.Column("chain_key_version", sa.Integer(), nullable=True),
}
INDEX_NAME = "ix_audit_logs_entry_hash"


def _columns(bind) -> set:
    from sqlalchemy import inspect
    return {c["name"] for c in inspect(bind).get_columns(TABLE)}


def _indexes(bind) -> set:
    from sqlalchemy import inspect
    return {i["name"] for i in inspect(bind).get_indexes(TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    present = _columns(bind)
    with op.batch_alter_table(TABLE) as batch:
        for name, col in COLUMNS.items():
            if name not in present:
                batch.add_column(col)
                print(f"[0020] Added {TABLE}.{name}")
            else:
                print(f"[0020] {TABLE}.{name} already present — skipping add")
    if INDEX_NAME not in _indexes(bind):
        op.create_index(INDEX_NAME, TABLE, ["entry_hash"])
        print(f"[0020] Created index {INDEX_NAME}")


def downgrade() -> None:
    bind = op.get_bind()
    if INDEX_NAME in _indexes(bind):
        op.drop_index(INDEX_NAME, table_name=TABLE)
    present = _columns(bind)
    with op.batch_alter_table(TABLE) as batch:
        for name in COLUMNS:
            if name in present:
                batch.drop_column(name)
                print(f"[0020] Dropped {TABLE}.{name}")
