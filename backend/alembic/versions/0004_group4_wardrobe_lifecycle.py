"""group 4 wardrobe lifecycle — processing status, seasonality, AI metadata

Revision ID: 0004_group4_wardrobe_lifecycle
Revises: 0003_share_token_hardening
Create Date: 2026-08-30

Group 4 (Personal Wardrobe & Smart Reuse) production hardening:

* ``processing_status`` — real item lifecycle (uploaded -> processing ->
  ready | failed/retryable) so image uploads never appear "done" before the
  vision analysis actually succeeded.
* ``processing_error`` — last failure detail powering honest retry UX.
* ``ai_confidence`` — the vision model's own confidence, persisted for audit.
* ``seasonality`` / ``secondary_colors`` — BRD structured AI fields.
* ``image_hash`` — sha256 of the uploaded bytes for duplicate-upload
  protection during bulk import.

All columns are added defensively (no-op if they already exist) and existing
rows are backfilled to ``processing_status='ready'`` — they were created
through the metadata path which required complete attributes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_group4_wardrobe_lifecycle"
down_revision: Union[str, None] = "0003_share_token_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns(bind, table: str) -> set:
    return {col["name"] for col in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("wardrobe_items"):
        return
    existing = _existing_columns(bind, "wardrobe_items")

    additions = {
        "secondary_colors": sa.Column("secondary_colors", sa.Text(), nullable=False, server_default="[]"),
        "seasonality": sa.Column("seasonality", sa.String(length=30), nullable=False, server_default="All-Season"),
        "processing_status": sa.Column("processing_status", sa.String(length=20), nullable=False, server_default="ready"),
        "processing_error": sa.Column("processing_error", sa.Text(), nullable=True),
        "ai_confidence": sa.Column("ai_confidence", sa.Float(), nullable=True),
        "image_hash": sa.Column("image_hash", sa.String(length=64), nullable=True),
    }
    for name, column in additions.items():
        if name not in existing:
            op.add_column("wardrobe_items", column)

    # Existing rows were created with complete manual metadata — they are
    # already usable, so they graduate to 'ready' rather than appearing as
    # unprocessed uploads.
    op.execute("UPDATE wardrobe_items SET processing_status = 'ready' WHERE processing_status IS NULL")

    existing_indexes = {idx["name"] for idx in sa.inspect(bind).get_indexes("wardrobe_items")}
    if "ix_wardrobe_items_processing_status" not in existing_indexes:
        op.create_index("ix_wardrobe_items_processing_status", "wardrobe_items", ["processing_status"])
    if "ix_wardrobe_items_image_hash" not in existing_indexes:
        op.create_index("ix_wardrobe_items_image_hash", "wardrobe_items", ["image_hash"])


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("wardrobe_items"):
        return
    existing_indexes = {idx["name"] for idx in sa.inspect(bind).get_indexes("wardrobe_items")}
    for idx in ("ix_wardrobe_items_image_hash", "ix_wardrobe_items_processing_status"):
        if idx in existing_indexes:
            op.drop_index(idx, table_name="wardrobe_items")
    existing = _existing_columns(bind, "wardrobe_items")
    for name in ("image_hash", "ai_confidence", "processing_error", "processing_status",
                 "seasonality", "secondary_colors"):
        if name in existing:
            op.drop_column("wardrobe_items", name)
