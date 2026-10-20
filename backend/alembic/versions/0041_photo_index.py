"""0041 · product_images.photo_index — a product may hold MORE THAN ONE photograph.

WHY: ``product_images`` models renditions, not photographs. Every row was keyed
``products/{id}/{id}-{ratio}.{format}`` and every importer call registered a fresh
full ladder, so a product could hold exactly ONE source picture: a second photo
would have overwritten the first photo's renditions (same key) or, if the caller
re-registered, wiped the set. The CSV ``images`` column accepts an array and the
importer silently kept ``parsed[0]`` — a brand that supplied front/back/detail
photographs had two of the three discarded while the job reported success.

This migration adds the missing dimension: ``photo_index`` 0 is the photograph the
existing rows all are, so no backfill is needed and no byte moves. Photograph *n*
gets its own key prefix (``{id}-p{n}-{ratio}.{ext}``) and its own rows, which is
what lets ``gallery_images`` keep its pinned contract ("one frame per ratio" for
the hero photograph) while ``photos[]`` carries the rest.

Single-head chain: 0040_onboarding_completion_metadata -> 0041_photo_index.
Additive only (one non-null column with a server default, one composite index).
SQLite-safe: the column is added with a default, which SQLite accepts in place;
no batch/rebuild is required. PostgreSQL-safe: ADD COLUMN with a constant default
does not rewrite the table.

Revision ID: 0041_photo_index
Revises: 0040_onboarding_completion_metadata
Create Date: 2026-10-21
"""

from alembic import op
import sqlalchemy as sa

revision = "0041_photo_index"
down_revision = "0040_onboarding_completion_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_images",
        sa.Column("photo_index", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_product_images_product_photo",
        "product_images",
        ["product_id", "photo_index"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_product_images_product_photo", table_name="product_images")
    op.drop_column("product_images", "photo_index")
