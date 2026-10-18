"""products.sleeve_length — authoritative sleeve metadata for the VTON sleeve gate.

Revision ID: 0040_product_sleeve_length
Revises: 0039_brand_memberships
Create Date: 2026-10-18

Additive, NULL-able column only: no backfill, no guessing of values. The
sleeve-integrity gate treats NULL on an upper-body garment as "undeclared"
and refuses to claim a verified long-sleeve render for it (enforce mode).
The historical 2026-09 line numbered this 0018 in a lineage that was never
merged; the current chain head is 0039, so this migration is 0040.
"""
import sqlalchemy as sa
from alembic import op

revision = "0040_product_sleeve_length"
down_revision = "0039_brand_memberships"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("sleeve_length", sa.String(length=10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("products", "sleeve_length")
