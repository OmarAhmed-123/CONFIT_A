"""Product.sleeve_length — authoritative sleeve construction for the VTON
sleeve-integrity gate (S31 repair, 2026-09-16).

Revision ID: 0019_product_sleeve_length
Revises: 0018_partner_onboarding_email_lifecycle
Create Date: 2026-09-16

Idempotent inspector-guarded delta. Fresh SQLite dev databases created via
``Base.metadata.create_all()`` already have the column and will no-op.
Production Postgres receives the nullable column; existing rows are NULL
(= undeclared), which the gate treats as NOT VERIFIED for upper-slot
garments (honest refusal) until the operator declares the sleeve
construction — never guessed (AT-19).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "0019_product_sleeve_length"
down_revision: Union[str, None] = "0018_partner_onboarding_email_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(bind, table: str) -> set:
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if "products" not in inspect(bind).get_table_names():
        return
    if "sleeve_length" not in _columns(bind, "products"):
        op.add_column(
            "products",
            sa.Column("sleeve_length", sa.String(length=16), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "products" in inspect(bind).get_table_names() and "sleeve_length" in _columns(bind, "products"):
        op.drop_column("products", "sleeve_length")
