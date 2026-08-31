"""reconcile recently_viewed table on legacy create_all databases

Revision ID: 0007_reconcile_recently_viewed
Revises: 0006_widen_alembic_version
Create Date: 2026-08-31

Group 4 readiness audit found that ``recently_viewed`` — declared by the
``RecentlyViewed`` model in ``catalog.py`` and actively used by
``dashboard_service`` and ``catalog_repository.get_recently_viewed`` — was
missing from production. The production database was originally built by
``create_all()`` before the RecentlyViewed model was added to the codebase,
and the later ``alembic stamp 0001_baseline`` recorded the baseline as
applied without verifying every table actually existed. As a result the
dashboard query path would fail on Postgres with ``UndefinedTable``.

This migration creates the table idempotently. Fresh SQLite dev databases
where 0001_baseline already created it (guarded by ``_table_exists``) will
no-op. Every other environment gets the table brought into line with the
model.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_reconcile_recently_viewed"
down_revision: Union[str, None] = "0006_widen_alembic_version"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "recently_viewed" in insp.get_table_names():
        return

    op.create_table(
        "recently_viewed",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Integer(),
                  sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("viewed_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_recently_viewed_user_id", "recently_viewed", ["user_id"])
    op.create_index("ix_recently_viewed_id", "recently_viewed", ["id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "recently_viewed" not in insp.get_table_names():
        return
    existing = {idx["name"] for idx in insp.get_indexes("recently_viewed")}
    for idx in ("ix_recently_viewed_user_id", "ix_recently_viewed_id"):
        if idx in existing:
            op.drop_index(idx, table_name="recently_viewed")
    op.drop_table("recently_viewed")
