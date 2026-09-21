"""OUTFIT-01: share-link lifecycle + outfit mutation metadata.

Motivation (audit 2026-09-21, Outfit Composer / My Looks / public sharing):
``outfits.share_token`` existed but had no lifecycle at all — a minted link
lived forever, could not be revoked, and nothing recorded when the outfit was
last edited or how often a public link had been opened. A share feature
without revocation/expiry is a permanent, unrevocable data-exposure surface.

This revision adds four nullable/defaulted columns:

* ``share_expires_at``  – UTC instant after which the public token 404s.
* ``share_revoked_at``  – set by DELETE /outfits/{id}/share; a revoked token is
  never reusable and is indistinguishable from an unknown one (404).
* ``share_view_count``  – how many times the public page resolved the token, so
  the owner can see real exposure instead of guessing.
* ``updated_at``        – last mutation (title/occasion/items/order), required
  for optimistic concurrency and for honest "last edited" UI.

Additive-only and idempotent: existing rows keep NULL / 0, no existing column
changes, and re-running the upgrade skips columns that already exist. The
downgrade is a clean column drop.

Revision: 0018_outfit_share_lifecycle
Revises:  0017_audit_before_after_request_id
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0018_outfit_share_lifecycle"
down_revision: str = "0017_audit_before_after_request_id"
branch_labels = None
depends_on = None

TABLE = "outfits"
COLUMNS = {
    "share_expires_at": sa.Column("share_expires_at", sa.DateTime(), nullable=True),
    "share_revoked_at": sa.Column("share_revoked_at", sa.DateTime(), nullable=True),
    "share_view_count": sa.Column(
        "share_view_count", sa.Integer(), nullable=False, server_default="0"
    ),
    "updated_at": sa.Column("updated_at", sa.DateTime(), nullable=True),
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
                print(f"[0018] Added {TABLE}.{name}")
            else:
                print(f"[0018] {TABLE}.{name} already present — skipping add")

    # Backfill updated_at from created_at so "last edited" is never a lie for
    # rows that predate this column (they were last touched at creation).
    if "updated_at" not in present:
        op.execute(
            sa.text(
                f"UPDATE {TABLE} SET updated_at = created_at WHERE updated_at IS NULL"
            )
        )
        print("[0018] Backfilled outfits.updated_at from created_at")


def downgrade() -> None:
    bind = op.get_bind()
    present = _columns(bind)
    with op.batch_alter_table(TABLE) as batch:
        for name in COLUMNS:
            if name in present:
                batch.drop_column(name)
                print(f"[0018] Dropped {TABLE}.{name}")
