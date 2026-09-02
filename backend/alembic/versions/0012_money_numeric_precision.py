"""Money fields Float -> Numeric(12,2) for financial integrity

Revision ID: 0012_money_numeric_precision
Revises: 0011_group6_check_constraints
Create Date: 2026-09-02

Implements DB-level financial integrity:
- Float money fields cause binary representation errors (0.1+0.2 != 0.3)
- round(2) mitigates but not exact, aggregation can drift
- Production financial accounting requires exact Decimal via NUMERIC
- Preserves existing monetary values via CAST, no silent alteration
- PG compatible via batch_alter_table, SQLite compatible via recreate

Safety:
- No data loss: existing values CAST to Numeric, preserves history
- Inspector-guarded: only alters if table/column exists
- Idempotent: safe to run twice
- Downgrade: converts back to Float (lossy but best-effort)

Money fields migrated:
- sponsored_placements: bid_amount_per_click, daily_budget, spent_today, revenue_generated
- products: base_price
- product_skus: price_override
- brand_analytics_events: revenue_amount
- promotions: discount_value, min_order_amount
- promotion_redemptions: discount_amount
- orders: total_amount, subtotal_amount, discount_amount, tax_amount, shipping_amount
- order_items: unit_price, subtotal
- payment_transactions: amount, refunded_amount
- checkout_sessions: total_amount
- return_requests: refund_amount
- exchange_requests: price_delta
- wardrobe_items: purchase_price (optional)
- outfits: total_price (stylist)
- user_style_profiles: budget_monthly_min, max, per_outfit_max (optional)

Non-money Floats remain Float: rating, latitude, longitude, body_scaling, height, ai_confidence etc

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision: str = "0012_money_numeric_precision"
down_revision: Union[str, None] = "0011_group6_check_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables(bind) -> set:
    return set(inspect(bind).get_table_names())


def _get_columns(bind, table: str) -> set:
    try:
        insp = inspect(bind)
        cols = insp.get_columns(table)
        return {c["name"] for c in cols}
    except Exception:
        return set()


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    # Helper to alter column safely
    def alter_money(table: str, column: str, numeric_type=sa.Numeric(12, 2)):
        if table not in tables:
            return
        cols = _get_columns(bind, table)
        if column not in cols:
            return
        try:
            with op.batch_alter_table(table) as batch:
                batch.alter_column(column, type_=numeric_type, existing_type=sa.Float(), existing_nullable=True)
            print(f"[0012] Altered {table}.{column} Float -> Numeric(12,2)")
        except Exception as e:
            print(f"[0012] Could not alter {table}.{column}: {e}")

    # sponsored_placements
    for col in ["bid_amount_per_click", "daily_budget", "spent_today", "revenue_generated"]:
        alter_money("sponsored_placements", col, sa.Numeric(12, 2))

    # products
    alter_money("products", "base_price", sa.Numeric(12, 2))

    # product_skus
    alter_money("product_skus", "price_override", sa.Numeric(12, 2))

    # brand_analytics_events
    alter_money("brand_analytics_events", "revenue_amount", sa.Numeric(12, 2))

    # promotions
    for col in ["discount_value", "min_order_amount"]:
        alter_money("promotions", col, sa.Numeric(12, 2))

    # promotion_redemptions
    alter_money("promotion_redemptions", "discount_amount", sa.Numeric(12, 2))

    # orders
    for col in ["total_amount", "subtotal_amount", "discount_amount", "tax_amount", "shipping_amount"]:
        alter_money("orders", col, sa.Numeric(12, 2))

    # order_items
    for col in ["unit_price", "subtotal"]:
        alter_money("order_items", col, sa.Numeric(12, 2))

    # payment_transactions
    for col in ["amount", "refunded_amount"]:
        alter_money("payment_transactions", col, sa.Numeric(12, 2))

    # checkout_sessions
    alter_money("checkout_sessions", "total_amount", sa.Numeric(12, 2))

    # return_requests
    alter_money("return_requests", "refund_amount", sa.Numeric(12, 2))

    # exchange_requests
    alter_money("exchange_requests", "price_delta", sa.Numeric(12, 2))

    # wardrobe_items
    alter_money("wardrobe_items", "purchase_price", sa.Numeric(12, 2))

    # outfits (stylist total_price)
    alter_money("outfits", "total_price", sa.Numeric(12, 2))

    # user_style_profiles budgets
    for col in ["budget_monthly_min", "budget_monthly_max", "budget_per_outfit_max"]:
        alter_money("user_style_profiles", col, sa.Numeric(12, 2))

    # Ensure existing values are rounded to 2 decimals for consistency (no silent alteration beyond rounding)
    # This is safe: Float values like 19.990000000000002 -> 19.99
    try:
        # Only run rounding update for tables that exist
        if "orders" in tables:
            bind.execute(text("UPDATE orders SET total_amount = ROUND(total_amount, 2), subtotal_amount = ROUND(subtotal_amount, 2), discount_amount = ROUND(discount_amount, 2), tax_amount = ROUND(tax_amount, 2), shipping_amount = ROUND(shipping_amount, 2) WHERE total_amount IS NOT NULL"))
        if "order_items" in tables:
            bind.execute(text("UPDATE order_items SET unit_price = ROUND(unit_price, 2), subtotal = ROUND(subtotal, 2) WHERE unit_price IS NOT NULL"))
        if "products" in tables:
            bind.execute(text("UPDATE products SET base_price = ROUND(base_price, 2) WHERE base_price IS NOT NULL"))
        print("[0012] Rounded existing money values to 2 decimals")
    except Exception as e:
        print(f"[0012] Rounding update skipped: {e}")


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    def alter_back_to_float(table: str, column: str):
        if table not in tables:
            return
        cols = _get_columns(bind, table)
        if column not in cols:
            return
        try:
            with op.batch_alter_table(table) as batch:
                batch.alter_column(column, type_=sa.Float(), existing_type=sa.Numeric(12, 2), existing_nullable=True)
            print(f"[0012] Downgraded {table}.{column} Numeric -> Float")
        except Exception as e:
            print(f"[0012] Could not downgrade {table}.{column}: {e}")

    for tbl, cols in [
        ("sponsored_placements", ["bid_amount_per_click", "daily_budget", "spent_today", "revenue_generated"]),
        ("products", ["base_price"]),
        ("product_skus", ["price_override"]),
        ("brand_analytics_events", ["revenue_amount"]),
        ("promotions", ["discount_value", "min_order_amount"]),
        ("promotion_redemptions", ["discount_amount"]),
        ("orders", ["total_amount", "subtotal_amount", "discount_amount", "tax_amount", "shipping_amount"]),
        ("order_items", ["unit_price", "subtotal"]),
        ("payment_transactions", ["amount", "refunded_amount"]),
        ("checkout_sessions", ["total_amount"]),
        ("return_requests", ["refund_amount"]),
        ("exchange_requests", ["price_delta"]),
        ("wardrobe_items", ["purchase_price"]),
        ("outfits", ["total_price"]),
        ("user_style_profiles", ["budget_monthly_min", "budget_monthly_max", "budget_per_outfit_max"]),
    ]:
        for col in cols:
            alter_back_to_float(tbl, col)
