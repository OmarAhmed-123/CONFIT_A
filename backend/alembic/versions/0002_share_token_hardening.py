"""share token hardening — lengthen outfits.share_token for C8 tokens

Revision ID: 0002_share_token_hardening
Revises: 0001_baseline
Create Date: 2026-08-30

C8 replaces the 8-hex-char share tokens with full-strength
``secrets.token_urlsafe(24)`` values (~32 chars + ``look_`` prefix). The
column is widened to VARCHAR(255) so the stronger token always fits; the
unique index is (re)asserted. Existing short tokens remain valid — this is a
non-destructive widening.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_share_token_hardening"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("outfits") as batch_op:
        batch_op.alter_column(
            "share_token",
            existing_type=sa.String(length=100),
            type_=sa.String(length=255),
            existing_nullable=True,
        )
    # Ensure the uniqueness guarantee exists even on databases whose baseline
    # predated it (no-op if already present).
    bind = op.get_bind()
    existing_indexes = {idx["name"] for idx in sa.inspect(bind).get_indexes("outfits")}
    if "ix_outfits_share_token" not in existing_indexes:
        op.create_index("ix_outfits_share_token", "outfits", ["share_token"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("outfits") as batch_op:
        batch_op.alter_column(
            "share_token",
            existing_type=sa.String(length=255),
            type_=sa.String(length=100),
            existing_nullable=True,
        )
