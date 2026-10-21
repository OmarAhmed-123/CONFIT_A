"""Add user_wishlist_items table for authenticated favorites persistence & merge.

Revision ID: 0046_user_wishlist_items
Revises: 0045_brand_verified_domains
Create Date: 2026-10-21
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "0046_user_wishlist_items"
down_revision: Union[str, None] = "0045_brand_verified_domains"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "user_wishlist_items" not in insp.get_table_names():
        op.create_table(
            "user_wishlist_items",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "product_id",
                sa.Integer(),
                sa.ForeignKey("products.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("user_id", "product_id", name="uq_user_wishlist_user_product"),
        )
        op.create_index("ix_user_wishlist_items_id", "user_wishlist_items", ["id"])
        op.create_index("ix_user_wishlist_items_user_id", "user_wishlist_items", ["user_id"])
        op.create_index("ix_user_wishlist_items_product_id", "user_wishlist_items", ["product_id"])
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'confit_app_rw') THEN
                        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE user_wishlist_items TO confit_app_rw;
                        GRANT USAGE, SELECT, UPDATE ON SEQUENCE user_wishlist_items_id_seq TO confit_app_rw;
                    END IF;
                END $$;
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "user_wishlist_items" in insp.get_table_names():
        op.drop_index("ix_user_wishlist_items_product_id", table_name="user_wishlist_items")
        op.drop_index("ix_user_wishlist_items_user_id", table_name="user_wishlist_items")
        op.drop_index("ix_user_wishlist_items_id", table_name="user_wishlist_items")
        op.drop_table("user_wishlist_items")
