"""group 4 wardrobe dedup integrity — unique(user_id, image_hash)

Revision ID: 0005_group4_wardrobe_dedup_integrity
Revises: 0004_group4_wardrobe_lifecycle
Create Date: 2026-08-31

Group 4 §24/§27 concurrency hardening: the sha256 duplicate-upload protection
was check-then-act — two concurrent uploads of the same bytes could both pass
the pre-check and both insert. A UNIQUE constraint on (user_id, image_hash)
makes the database the final arbiter; the service catches the resulting
IntegrityError and returns the canonical item as an idempotent duplicate.

NULL hashes (manual/seeded items without an uploaded file) are unaffected —
both SQLite and Postgres treat NULLs as distinct under unique constraints.

batch_alter_table is used for SQLite compatibility (table recreation), the
same pattern as 0003_share_token_hardening.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_group4_wardrobe_dedup_integrity"
down_revision: Union[str, None] = "0004_group4_wardrobe_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CONSTRAINT = "uq_wardrobe_items_user_image_hash"


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("wardrobe_items"):
        return
    existing = {
        c["name"]
        for c in sa.inspect(bind).get_unique_constraints("wardrobe_items")
    }
    if _CONSTRAINT in existing:
        return
    with op.batch_alter_table("wardrobe_items") as batch_op:
        batch_op.create_unique_constraint(_CONSTRAINT, ["user_id", "image_hash"])


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("wardrobe_items"):
        return
    existing = {
        c["name"]
        for c in sa.inspect(bind).get_unique_constraints("wardrobe_items")
    }
    if _CONSTRAINT not in existing:
        return
    with op.batch_alter_table("wardrobe_items") as batch_op:
        batch_op.drop_constraint(_CONSTRAINT, type_="unique")
