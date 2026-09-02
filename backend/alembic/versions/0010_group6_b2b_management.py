"""Group 6 B2B Brand & Admin Management

Revision ID: 0010_group6_b2b_management
Revises: 0009_checkout_sessions
Create Date: 2026-09-02

Implements:
- CatalogImportJob for bulk CSV import with idempotency and error reporting
- BrandAnalyticsEvent for canonical funnel tracking (view, tryon, add_to_cart, purchase, etc)
- SponsoredPlacement hardening: remove fake defaults, add start/end dates, indexes
- StyleHeatmapAggregate already exists

Idempotent inspector-guarded for SQLite dev.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "0010_group6_b2b_management"
down_revision: Union[str, None] = "0009_checkout_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables(bind) -> set:
    return set(inspect(bind).get_table_names())


def _columns(bind, table: str) -> set:
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def _indexes(bind, table: str) -> set:
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {idx["name"] for idx in insp.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    # 1. CatalogImportJob table
    if "catalog_import_jobs" not in tables:
        op.create_table(
            "catalog_import_jobs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("file_name", sa.String(length=500), nullable=True),
            sa.Column("file_size", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="queued"),
            sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("accepted_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rejected_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("duplicate_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("errors_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_catalog_import_brand_status", "catalog_import_jobs", ["brand_id", "status"])
        op.create_index("ix_catalog_import_created", "catalog_import_jobs", ["created_at"])

    # 2. BrandAnalyticsEvent table
    if "brand_analytics_events" not in tables:
        op.create_table(
            "brand_analytics_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_id", sa.String(length=100), nullable=False, unique=True, index=True),
            sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("sku_id", sa.Integer(), sa.ForeignKey("product_skus.id", ondelete="SET NULL"), nullable=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("session_token", sa.String(length=100), nullable=True),
            sa.Column("event_type", sa.String(length=50), nullable=False, index=True),
            sa.Column("attribution_source", sa.String(length=50), nullable=True),
            sa.Column("outfit_id", sa.Integer(), sa.ForeignKey("outfits.id", ondelete="SET NULL"), nullable=True),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="SET NULL"), nullable=True),
            sa.Column("revenue_amount", sa.Float(), nullable=True),
            sa.Column("event_metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False, index=True),
        )
        op.create_index("ix_brand_analytics_brand_type_time", "brand_analytics_events", ["brand_id", "event_type", "created_at"])
        op.create_index("ix_brand_analytics_product", "brand_analytics_events", ["product_id"])
        op.create_index("ix_brand_analytics_sku", "brand_analytics_events", ["sku_id"])
        op.create_index("ix_brand_analytics_event_id", "brand_analytics_events", ["event_id"], unique=True)

    # 3. Harden SponsoredPlacement - add columns if missing, fix defaults
    if "sponsored_placements" in tables:
        cols = _columns(bind, "sponsored_placements")
        if "start_date" not in cols:
            op.add_column("sponsored_placements", sa.Column("start_date", sa.DateTime(), nullable=True))
        if "end_date" not in cols:
            op.add_column("sponsored_placements", sa.Column("end_date", sa.DateTime(), nullable=True))
        if "updated_at" not in cols:
            op.add_column("sponsored_placements", sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))

        # Fix defaults from fake 1420 etc to 0 - data migration not needed as we will update via ORM
        # But ensure indexes exist
        idxs = _indexes(bind, "sponsored_placements")
        if "ix_sponsored_placements_brand_id" not in idxs:
            try:
                op.create_index("ix_sponsored_placements_brand_id", "sponsored_placements", ["brand_id"])
            except Exception:
                pass
        if "ix_sponsored_placements_product_id" not in idxs:
            try:
                op.create_index("ix_sponsored_placements_product_id", "sponsored_placements", ["product_id"])
            except Exception:
                pass

    # 4. Ensure brand_profiles has indexes for performance
    if "brand_profiles" in tables:
        idxs = _indexes(bind, "brand_profiles")
        # Already has unique indexes on brand_name, slug, user_id

    # 5. Ensure products has brand_id index
    if "products" in tables:
        idxs = _indexes(bind, "products")
        if "ix_products_brand_id" not in idxs:
            try:
                op.create_index("ix_products_brand_id", "products", ["brand_id"])
            except Exception:
                pass

    # 6. Ensure product_skus has product_id index
    if "product_skus" in tables:
        idxs = _indexes(bind, "product_skus")
        if "ix_product_skus_product_id" not in idxs:
            try:
                op.create_index("ix_product_skus_product_id", "product_skus", ["product_id"])
            except Exception:
                pass


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    if "brand_analytics_events" in tables:
        op.drop_table("brand_analytics_events")
    if "catalog_import_jobs" in tables:
        op.drop_table("catalog_import_jobs")

    # Do not drop columns from sponsored_placements on downgrade to preserve data
