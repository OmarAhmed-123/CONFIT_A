"""Record which model produced a wardrobe item's AI metadata.

Revision ID: 0047_wardrobe_analysis_source
Revises: 0046_user_wishlist_items
Create Date: 2026-10-26

Why: FR-18 honesty — the UI must be able to say "analysed by <model>" (or
"entered manually") per item, and never present a fallback as real inference.
``analysis_source`` holds the provider's model id (e.g. ``ibm/granite-…``,
``meta-llama/llama-4-…``, ``gemini-flash-lite-latest``), ``manual`` for user
entered metadata, or NULL for rows predating this column. Additive, nullable,
no backfill (a NULL is the truthful state for historical rows).
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "0047_wardrobe_analysis_source"
down_revision: Union[str, None] = "0046_user_wishlist_items"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(insp, table: str) -> set:
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "wardrobe_items" in insp.get_table_names():
        if "analysis_source" not in _columns(insp, "wardrobe_items"):
            op.add_column("wardrobe_items", sa.Column("analysis_source", sa.String(length=120), nullable=True))
        if "analysis_description" not in _columns(insp, "wardrobe_items"):
            op.add_column("wardrobe_items", sa.Column("analysis_description", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "wardrobe_items" in insp.get_table_names():
        cols = _columns(insp, "wardrobe_items")
        if "analysis_description" in cols:
            op.drop_column("wardrobe_items", "analysis_description")
        if "analysis_source" in cols:
            op.drop_column("wardrobe_items", "analysis_source")
