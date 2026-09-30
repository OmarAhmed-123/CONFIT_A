"""Make wardrobe deletion reversible — the precondition for Undo.

WHY THIS MIGRATION EXISTS
-------------------------
The Undo/Remove-to-Bin specification is explicit: *optimistic reversible
deletion is only allowed if the endpoint supports restore, or the action can
be safely reversed*. It is not.

``WardrobeService.delete_item`` does two irreversible things in one call::

    self.wardrobe_repo.delete_item(item)   # DELETE FROM wardrobe_items
    self._delete_owned_image(image_url)    # and removes the object from S3

So a front-end "Undo" built on today's backend would be a lie twice over: the
row is gone, and the photograph the user uploaded is gone from storage. The
button would appear to work until the page reloaded, and the image could
never come back at all.

WHAT THIS ADDS
--------------
``wardrobe_items.deleted_at`` — NULL for a live item, a UTC timestamp for one
in the bin. Deletion becomes a state transition, and the IMAGE IS KEPT for
the duration of the grace window so a restore returns the real photograph
rather than a broken thumbnail.

Permanent deletion stays available as a separate, explicitly-confirmed action
(spec §6.6) and is the only path that removes the stored object.

WHY A PARTIAL INDEX
-------------------
Every wardrobe read becomes ``WHERE user_id = ? AND deleted_at IS NULL``.
A partial index over live rows only keeps that lookup cheap and, importantly,
does not grow with the bin — the index stays the size of the working set.
SQLite (used by the test suite) supports partial indexes too, so one
definition serves both engines.

THE UNIQUE CONSTRAINT INTERACTION — the non-obvious part
--------------------------------------------------------
``uq_wardrobe_items_user_image_hash`` is UNIQUE on ``(user_id, image_hash)``.
A soft-deleted row still occupies that slot, so re-uploading the same
photograph while the old one sits in the bin would raise IntegrityError and
surface as a 500.

The constraint is deliberately NOT relaxed: it is what stops a user
accumulating duplicates of the same garment, and the specification's
acceptance criteria require "no duplicates in the list". The collision is
resolved in the service layer instead — a duplicate upload that matches a
BINNED item restores and refreshes that item rather than inserting a second
one. That keeps one row per (user, image) at all times, which is the actual
invariant, and turns a crash into the behaviour the user wanted anyway.

Revision: 0030_wardrobe_soft_delete
Revises:  0029_brand_profile_not_null_defaults
"""
import sqlalchemy as sa
from alembic import op

revision: str = "0030_wardrobe_soft_delete"
down_revision: str = "0029_brand_profile_not_null_defaults"
branch_labels = None
depends_on = None

_INDEX = "ix_wardrobe_items_user_active"


def upgrade() -> None:
    op.add_column(
        "wardrobe_items",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Existing rows are live by definition: NULL is already the correct value,
    # so there is deliberately no backfill. Writing a value here would be
    # inventing history.
    op.create_index(
        _INDEX,
        "wardrobe_items",
        ["user_id"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="wardrobe_items")
    op.drop_column("wardrobe_items", "deleted_at")
