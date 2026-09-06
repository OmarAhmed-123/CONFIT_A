"""ADMIN-01: full audit completeness — before/after state + request id.

Adds three nullable columns to audit_logs so every security-relevant event
can carry the full before/after resource state and the correlation id of the
HTTP request that produced it. Additive-only: existing rows keep NULL and no
existing column changes, so the upgrade is safe to replay (idempotent) and
the downgrade is a clean column drop.

Revision: 0017_audit_before_after_request_id
Revises:  0016_vton_temporary_delivery
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0017_audit_before_after_request_id"
down_revision: str = "0016_vton_temporary_delivery"
branch_labels = None
depends_on = None

TABLE = "audit_logs"
COLUMNS = {
    "before_json": sa.Column("before_json", sa.Text(), nullable=True),
    "after_json": sa.Column("after_json", sa.Text(), nullable=True),
    "request_id": sa.Column("request_id", sa.String(length=64), nullable=True),
}


def _columns(bind) -> set:
    from sqlalchemy import inspect
    return {c["name"] for c in inspect(bind).get_columns(TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    present = _columns(bind)
    with op.batch_alter_table(TABLE) as batch:
        for name, col in COLUMNS.items():
            if name not in present:
                batch.add_column(col)
                print(f"[0017] Added {TABLE}.{name}")
            else:
                print(f"[0017] {TABLE}.{name} already present — skipping add")


def downgrade() -> None:
    bind = op.get_bind()
    present = _columns(bind)
    with op.batch_alter_table(TABLE) as batch:
        for name in COLUMNS:
            if name in present:
                batch.drop_column(name)
                print(f"[0017] Dropped {TABLE}.{name}")
