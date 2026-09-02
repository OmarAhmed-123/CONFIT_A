"""Group 5 commerce: promotions, payments, fulfillment, reservations, events.

Revision ID: 0008_group5_commerce
Revises: 0007_reconcile_recently_viewed
Create Date: 2026-09-02

Idempotent inspector-guarded delta for the transactional layer. Fresh SQLite
dev databases created via ``Base.metadata.create_all()`` already have these
objects and will no-op. Production Postgres that stamped 0001_baseline
receives the Group 5 columns and tables.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "0008_group5_commerce"
down_revision: Union[str, None] = "0007_reconcile_recently_viewed"
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


def _uniques(bind, table: str) -> set:
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return set()
    names = set()
    for uq in insp.get_unique_constraints(table):
        if uq.get("name"):
            names.add(uq["name"])
    return names


def _add_column(bind, table: str, column: sa.Column) -> None:
    if table not in _tables(bind) or column.name in _columns(bind, table):
        return
    # SQLite cannot ALTER TABLE ... ADD COLUMN with an inline ForeignKey.
    if bind.dialect.name == "sqlite" and column.foreign_keys:
        op.add_column(
            table,
            sa.Column(column.name, column.type, nullable=column.nullable),
        )
        return
    op.add_column(table, column)


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    _add_column(bind, "carts", sa.Column("promo_code", sa.String(length=50), nullable=True))
    _add_column(bind, "orders", sa.Column("guest_email", sa.String(length=255), nullable=True))
    _add_column(bind, "orders", sa.Column("guest_session_token", sa.String(length=100), nullable=True))
    _add_column(bind, "orders", sa.Column("promo_code", sa.String(length=50), nullable=True))
    _add_column(bind, "orders", sa.Column("payment_mode", sa.String(length=20), nullable=True))
    _add_column(bind, "orders", sa.Column("shipping_method", sa.String(length=30), nullable=True))

    if "orders" in tables:
        existing_idx = _indexes(bind, "orders")
        if "ix_orders_guest_email" not in existing_idx and "guest_email" in _columns(bind, "orders"):
            op.create_index("ix_orders_guest_email", "orders", ["guest_email"])
        if "ix_orders_guest_session_token" not in existing_idx and "guest_session_token" in _columns(bind, "orders"):
            op.create_index("ix_orders_guest_session_token", "orders", ["guest_session_token"])

    _add_column(bind, "return_requests", sa.Column("guest_email", sa.String(length=255), nullable=True))
    _add_column(bind, "return_requests", sa.Column("label_provider_ref", sa.String(length=100), nullable=True))

    if "promotions" not in tables:
        op.create_table(
            "promotions",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("code", sa.String(length=50), nullable=False),
            sa.Column("description", sa.String(length=255), nullable=False),
            sa.Column("discount_type", sa.String(length=20), nullable=False),
            sa.Column("discount_value", sa.Float(), nullable=False),
            sa.Column("min_order_amount", sa.Float(), nullable=False),
            sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brand_profiles.id", ondelete="SET NULL"), nullable=True),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
            sa.Column("market", sa.String(length=10), nullable=True),
            sa.Column("currency", sa.String(length=10), nullable=False),
            sa.Column("max_redemptions", sa.Integer(), nullable=True),
            sa.Column("max_per_user", sa.Integer(), nullable=False),
            sa.Column("stackable", sa.Boolean(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("starts_at", sa.DateTime(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_promotions_id", "promotions", ["id"])
        op.create_index("ix_promotions_code", "promotions", ["code"], unique=True)

    if "fulfillment_groups" not in _tables(bind):
        op.create_table(
            "fulfillment_groups",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
            sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brand_profiles.id"), nullable=False),
            sa.Column("brand_name", sa.String(length=255), nullable=False),
            sa.Column("fulfillment_type", sa.String(length=30), nullable=False),
            sa.Column("store_id", sa.Integer(), sa.ForeignKey("store_locations.id"), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("carrier", sa.String(length=100), nullable=True),
            sa.Column("tracking_number", sa.String(length=100), nullable=True, unique=True),
            sa.Column("estimated_delivery_date", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_fulfillment_groups_id", "fulfillment_groups", ["id"])
        op.create_index("ix_fulfillment_groups_order_id", "fulfillment_groups", ["order_id"])

    _add_column(
        bind,
        "order_items",
        sa.Column("outfit_id", sa.Integer(), sa.ForeignKey("outfits.id", ondelete="SET NULL"), nullable=True),
    )
    _add_column(
        bind,
        "order_items",
        sa.Column(
            "fulfillment_group_id",
            sa.Integer(),
            sa.ForeignKey("fulfillment_groups.id", ondelete="SET NULL", name="fk_order_items_fulfillment_group"),
            nullable=True,
        ),
    )

    if "promotion_redemptions" not in _tables(bind):
        op.create_table(
            "promotion_redemptions",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("promotion_id", sa.Integer(), sa.ForeignKey("promotions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("guest_email", sa.String(length=255), nullable=True),
            sa.Column("discount_amount", sa.Float(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("promotion_id", "order_id", name="uq_promo_redemption_order"),
        )
        op.create_index("ix_promotion_redemptions_id", "promotion_redemptions", ["id"])

    if "payment_transactions" not in _tables(bind):
        op.create_table(
            "payment_transactions",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
            sa.Column("provider", sa.String(length=50), nullable=False),
            sa.Column("method", sa.String(length=50), nullable=False),
            sa.Column("provider_tx_id", sa.String(length=100), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("currency", sa.String(length=10), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("mode", sa.String(length=20), nullable=False),
            sa.Column("idempotency_key", sa.String(length=100), nullable=True),
            sa.Column("refunded_amount", sa.Float(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("provider", "provider_tx_id", name="uq_payment_provider_tx"),
            sa.UniqueConstraint("idempotency_key", name="uq_payment_idempotency"),
        )
        op.create_index("ix_payment_transactions_id", "payment_transactions", ["id"])
        op.create_index("ix_payment_transactions_order_id", "payment_transactions", ["order_id"])

    if "webhook_events" not in _tables(bind):
        op.create_table(
            "webhook_events",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("provider", sa.String(length=50), nullable=False),
            sa.Column("event_id", sa.String(length=128), nullable=False),
            sa.Column("order_number", sa.String(length=50), nullable=True),
            sa.Column("processed_at", sa.DateTime(), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),
        )
        op.create_index("ix_webhook_events_id", "webhook_events", ["id"])

    if "inventory_reservations" not in _tables(bind):
        op.create_table(
            "inventory_reservations",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("sku_id", sa.Integer(), sa.ForeignKey("product_skus.id", ondelete="CASCADE"), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="SET NULL"), nullable=True),
            sa.Column("store_id", sa.Integer(), sa.ForeignKey("store_locations.id", ondelete="SET NULL"), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("released_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_inventory_reservations_id", "inventory_reservations", ["id"])
        op.create_index("ix_inv_res_sku_status", "inventory_reservations", ["sku_id", "status"])

    if "order_events" not in _tables(bind):
        op.create_table(
            "order_events",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status_key", sa.String(length=50), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_order_events_id", "order_events", ["id"])
        op.create_index("ix_order_events_order_created", "order_events", ["order_id", "created_at"])

    if "shipments" not in _tables(bind):
        op.create_table(
            "shipments",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("fulfillment_group_id", sa.Integer(), sa.ForeignKey("fulfillment_groups.id", ondelete="CASCADE"), nullable=False),
            sa.Column("carrier", sa.String(length=100), nullable=False),
            sa.Column("tracking_number", sa.String(length=100), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("shipped_at", sa.DateTime(), nullable=True),
            sa.Column("delivered_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_shipments_id", "shipments", ["id"])
        op.create_index("ix_shipments_tracking_number", "shipments", ["tracking_number"], unique=True)

    if "return_items" not in _tables(bind):
        op.create_table(
            "return_items",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("return_request_id", sa.Integer(), sa.ForeignKey("return_requests.id", ondelete="CASCADE"), nullable=False),
            sa.Column("order_item_id", sa.Integer(), sa.ForeignKey("order_items.id", ondelete="CASCADE"), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.UniqueConstraint("return_request_id", "order_item_id", name="uq_return_item"),
        )
        op.create_index("ix_return_items_id", "return_items", ["id"])

    if "exchange_requests" not in _tables(bind):
        op.create_table(
            "exchange_requests",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("exchange_number", sa.String(length=50), nullable=False),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
            sa.Column("original_item_id", sa.Integer(), sa.ForeignKey("order_items.id"), nullable=False),
            sa.Column("replacement_sku_id", sa.Integer(), sa.ForeignKey("product_skus.id"), nullable=False),
            sa.Column("price_delta", sa.Float(), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("payment_status", sa.String(length=30), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_exchange_requests_id", "exchange_requests", ["id"])
        op.create_index("ix_exchange_requests_exchange_number", "exchange_requests", ["exchange_number"], unique=True)

    if "cart_items" in _tables(bind) and "uq_cart_items_cart_sku" not in _uniques(bind, "cart_items"):
        try:
            if bind.dialect.name == "sqlite":
                with op.batch_alter_table("cart_items") as batch:
                    batch.create_unique_constraint("uq_cart_items_cart_sku", ["cart_id", "product_sku_id"])
            else:
                op.create_unique_constraint("uq_cart_items_cart_sku", "cart_items", ["cart_id", "product_sku_id"])
        except Exception:
            pass

    if "store_inventories" in _tables(bind) and "uq_store_inventories_store_sku" not in _uniques(bind, "store_inventories"):
        try:
            if bind.dialect.name == "sqlite":
                with op.batch_alter_table("store_inventories") as batch:
                    batch.create_unique_constraint("uq_store_inventories_store_sku", ["store_id", "sku_id"])
            else:
                op.create_unique_constraint(
                    "uq_store_inventories_store_sku", "store_inventories", ["store_id", "sku_id"]
                )
        except Exception:
            pass


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    for table in (
        "exchange_requests",
        "return_items",
        "shipments",
        "order_events",
        "inventory_reservations",
        "webhook_events",
        "payment_transactions",
        "promotion_redemptions",
        "promotions",
    ):
        if table in tables:
            op.drop_table(table)

    if "order_items" in _tables(bind) and "fulfillment_group_id" in _columns(bind, "order_items"):
        op.drop_column("order_items", "fulfillment_group_id")
    if "order_items" in _tables(bind) and "outfit_id" in _columns(bind, "order_items"):
        op.drop_column("order_items", "outfit_id")
    if "fulfillment_groups" in _tables(bind):
        op.drop_table("fulfillment_groups")

    for col in ("label_provider_ref", "guest_email"):
        if "return_requests" in _tables(bind) and col in _columns(bind, "return_requests"):
            op.drop_column("return_requests", col)

    if "orders" in _tables(bind):
        existing_idx = _indexes(bind, "orders")
        for idx in ("ix_orders_guest_email", "ix_orders_guest_session_token"):
            if idx in existing_idx:
                op.drop_index(idx, table_name="orders")
        for col in ("shipping_method", "payment_mode", "promo_code", "guest_session_token", "guest_email"):
            if col in _columns(bind, "orders"):
                op.drop_column("orders", col)

    if "carts" in _tables(bind) and "promo_code" in _columns(bind, "carts"):
        op.drop_column("carts", "promo_code")
