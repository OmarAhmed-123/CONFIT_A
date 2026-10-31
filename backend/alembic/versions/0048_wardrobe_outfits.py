"""Persist outfits assembled from the user's own wardrobe.

Revision ID: 0048_wardrobe_outfits
Revises: 0047_wardrobe_analysis_source
Create Date: 2026-10-26

Why: the AI wardrobe stylist could recommend a look but not keep it. Catalog
``outfits`` carry prices/cart/share semantics and require ``product_id``, so a
wardrobe look gets its own small pair of tables. Items reference
``wardrobe_items.id`` with ON DELETE CASCADE: a saved look can never display
a garment the user has removed. Additive only; downgrade drops both tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0048_wardrobe_outfits"
down_revision: str | None = "0047_wardrobe_analysis_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())
    if "wardrobe_outfits" not in tables:
        op.create_table(
            "wardrobe_outfits",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(length=160), nullable=False),
            sa.Column("occasion", sa.String(length=60), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("styling_notes_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("limitations_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("missing_categories_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("context_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("is_complete", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("source", sa.String(length=40), nullable=False),
            sa.Column("ai_generated", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("model_id", sa.String(length=160), nullable=True),
            sa.Column("prompt_version", sa.String(length=40), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_wardrobe_outfits_user_id", "wardrobe_outfits", ["user_id"])
    if "wardrobe_outfit_items" not in tables:
        op.create_table(
            "wardrobe_outfit_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("outfit_id", sa.Integer(), sa.ForeignKey("wardrobe_outfits.id", ondelete="CASCADE"), nullable=False),
            sa.Column("wardrobe_item_id", sa.Integer(), sa.ForeignKey("wardrobe_items.id", ondelete="CASCADE"), nullable=False),
            sa.Column("role", sa.String(length=20), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        )
        op.create_index("ix_wardrobe_outfit_items_outfit_id", "wardrobe_outfit_items", ["outfit_id"])
        op.create_index("ix_wardrobe_outfit_items_wardrobe_item_id", "wardrobe_outfit_items", ["wardrobe_item_id"])
    if bind.dialect.name == "postgresql":
        # Same convention as 0046: the runtime role owns no objects, so every
        # new table must be granted explicitly or the API gets 42501 at runtime.
        op.execute(
            sa.text(
                """
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'confit_app_rw') THEN
                        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE wardrobe_outfits TO confit_app_rw;
                        GRANT USAGE, SELECT, UPDATE ON SEQUENCE wardrobe_outfits_id_seq TO confit_app_rw;
                        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE wardrobe_outfit_items TO confit_app_rw;
                        GRANT USAGE, SELECT, UPDATE ON SEQUENCE wardrobe_outfit_items_id_seq TO confit_app_rw;
                    END IF;
                END $$;
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())
    if "wardrobe_outfit_items" in tables:
        op.drop_table("wardrobe_outfit_items")
    if "wardrobe_outfits" in tables:
        op.drop_table("wardrobe_outfits")
