"""Make outfit deletion reversible — Undo for /builder and /my-looks.

WHY
---
Migration 0030 made WARDROBE deletion reversible. The Undo specification also
covers "Remove look" and "clear slot" on `/builder` and `/my-looks`, and that
half was still a hard delete:

    StylistRepository.delete_outfit:
        self.db.delete(outfit)   # OutfitItem rows cascade (all, delete-orphan)

So "Remove look" destroyed the outfit AND every line in it. An Undo button
there would have been the same lie the wardrobe one would have been: nothing
to restore.

A PRIVACY CONSEQUENCE THE WARDROBE DID NOT HAVE
-----------------------------------------------
Outfits can be SHARED: `outfits.share_token` powers a public, unauthenticated
page at `/looks/{token}`. A naive soft delete would leave a "deleted" look
reachable by anyone holding the link — the user pressed delete and the thing
stayed on the internet.

`get_outfit_by_share_token` is therefore filtered to live rows in the same
change. Deleting a look revokes its public visibility immediately; restoring
it brings the same token back, which is the behaviour a user expects from
Undo. That is enforced by a test, because it is the kind of guarantee that
silently regresses.

Partial index over live rows only, so `/my-looks` stays cheap and the index
does not grow with the bin. SQLite supports partial indexes too, so one
definition serves the test suite and PostgreSQL alike.

Revision: 0031_outfit_soft_delete
Revises:  0030_wardrobe_soft_delete
"""
import sqlalchemy as sa
from alembic import op

revision: str = "0031_outfit_soft_delete"
down_revision: str = "0030_wardrobe_soft_delete"
branch_labels = None
depends_on = None

_INDEX = "ix_outfits_user_active"


def upgrade() -> None:
    op.add_column("outfits", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    # Existing rows are live by definition; NULL is already correct, so there
    # is deliberately no backfill. Writing a value would invent history.
    op.create_index(
        _INDEX,
        "outfits",
        ["user_id"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="outfits")
    op.drop_column("outfits", "deleted_at")
