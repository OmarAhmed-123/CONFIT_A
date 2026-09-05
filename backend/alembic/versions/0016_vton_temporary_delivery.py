"""VTON temporary delivery metadata (NO image bytes)

Revision ID: 0016_vton_temporary_delivery
Revises: 0015_wardrobe_purchase_lineage
Create Date: 2026-09-05

Why
---
Product requirement (2026-09-05 closure directive): generated try-on images
are delivered to the authenticated requesting user and must NOT be stored
permanently (not in PostgreSQL, R2/S3, local disk, the repository, or any
durable object/frontend asset).

The VTON flow therefore no longer writes the rendered image to durable
storage. The only persisted delivery metadata is:

* ``delivery_token_hash`` — SHA-256 of the one-time, high-entropy delivery
  token (the token itself exists only in the authenticated completion
  response); and
* ``delivery_expires_at`` / ``delivery_content_type`` — the expiry and mime
  of the process-local, TTL-bounded staged copy that backs the one-shot
  ``GET /try-on/jobs/{job_id}/result`` download.

Safety
------
* Additive: three nullable columns + one non-unique index. No existing
  column is dropped or narrowed; no row is rewritten.
* Idempotent: existing objects are detected and skipped.
"""
import sqlalchemy as sa
from alembic import op


revision: str = "0016_vton_temporary_delivery"
down_revision: str = "0015_wardrobe_purchase_lineage"
branch_labels = None
depends_on = None

TABLE = "tryon_jobs"
COLUMNS = {
    "delivery_token_hash": sa.Column("delivery_token_hash", sa.String(length=64), nullable=True),
    "delivery_expires_at": sa.Column("delivery_expires_at", sa.DateTime(), nullable=True),
    "delivery_content_type": sa.Column("delivery_content_type", sa.String(length=50), nullable=True),
}
INDEX = "ix_tryon_jobs_delivery_token_hash"


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
                print(f"[0016] Added {TABLE}.{name}")
            else:
                print(f"[0016] {TABLE}.{name} already present — skipping add")
        if INDEX not in _indexes(bind):
            batch.create_index(INDEX, ["delivery_token_hash"], unique=False)
            print(f"[0016] Created index {INDEX}")
        else:
            print(f"[0016] Index {INDEX} already present — skipping")


def downgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table(TABLE) as batch:
        if INDEX in _indexes(bind):
            batch.drop_index(INDEX)
        for name in COLUMNS:
            if name in _columns(bind):
                batch.drop_column(name)
                print(f"[0016] Dropped {TABLE}.{name}")
