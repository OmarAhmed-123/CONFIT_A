"""Apportion the order-level discount onto each order line; add compare_at_price.

THE DEFECT
----------
`orders.discount_amount` held the whole promo reduction as one order-wide
number and was never distributed to `order_items`. Every consumer that needs a
per-line or per-brand figure therefore had nothing to read, and the brand sales
report computed:

    net_sales = SUM(quantity * unit_price) - returned_value

which ignores the discount entirely. On any order placed with a promo code the
brand was shown MORE revenue than the order actually produced. Nothing failed
loudly; the statement was simply wrong.

THE FIX
-------
`order_items.discount_amount` stores each line's share, apportioned with the
largest-remainder method (`core.money.allocate_proportionally`) so the shares
sum to `orders.discount_amount` exactly.

BACKFILL
--------
Historical orders are backfilled proportionally to line subtotal, in SQL, in
one statement per dialect. The remainder cent that integer division drops is
then pushed onto each order's largest line, so the invariant

    SUM(order_items.discount_amount) == orders.discount_amount

holds for old rows as well as new ones. Orders with no discount are untouched
(the column default of 0 is already correct for them).

The backfill is deliberately expressed in SQL rather than by loading rows into
Python: on a large `order_items` table a row-by-row pass would hold a
transaction open far longer than necessary.

Revision: 0025_order_item_discount_allocation
Revises:  0024_audit_insert_provenance_guard
"""
import sqlalchemy as sa
from alembic import op

revision: str = "0025_order_item_discount_allocation"
down_revision: str = "0024_audit_insert_provenance_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A real prior price, so the storefront can show a discount badge without
    # inventing one. Nullable on purpose: NULL means "never offered cheaper",
    # which is different from "was the same price".
    op.add_column(
        "products",
        sa.Column("compare_at_price", sa.Numeric(12, 2), nullable=True),
    )

    op.add_column(
        "order_items",
        sa.Column(
            "discount_amount",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
    )

    bind = op.get_bind()

    # --- Step 1: proportional share, floored to the cent ------------------
    # Guarded by `o.discount_amount > 0` so undiscounted orders are skipped
    # entirely, and by `> 0` on the order subtotal to avoid division by zero.
    op.execute(
        sa.text(
            """
            UPDATE order_items AS oi
            SET discount_amount = (
                SELECT ROUND(
                    o.discount_amount * oi.subtotal / NULLIF(line_totals.s, 0),
                    2
                )
                FROM orders AS o
                JOIN (
                    SELECT order_id, SUM(subtotal) AS s
                    FROM order_items
                    GROUP BY order_id
                ) AS line_totals ON line_totals.order_id = o.id
                WHERE o.id = oi.order_id
                  AND o.discount_amount > 0
                  AND line_totals.s > 0
            )
            WHERE EXISTS (
                SELECT 1 FROM orders AS o
                WHERE o.id = oi.order_id AND o.discount_amount > 0
            )
            """
        )
    )
    # The correlated subquery yields NULL for rows the WHERE let through but
    # the inner guards rejected; normalise those back to 0.
    op.execute(sa.text(
        "UPDATE order_items SET discount_amount = 0 WHERE discount_amount IS NULL"
    ))

    # --- Step 2: push the dropped remainder onto each order's largest line -
    # Rounding each share independently cannot be relied on to re-sum to the
    # order discount. Rather than leave the invariant broken for historical
    # rows, settle the difference on the line best able to absorb it.
    rows = bind.execute(
        sa.text(
            """
            SELECT o.id AS order_id,
                   o.discount_amount AS target,
                   COALESCE(SUM(oi.discount_amount), 0) AS allocated
            FROM orders AS o
            JOIN order_items AS oi ON oi.order_id = o.id
            WHERE o.discount_amount > 0
            GROUP BY o.id, o.discount_amount
            HAVING COALESCE(SUM(oi.discount_amount), 0) <> o.discount_amount
            """
        )
    ).fetchall()

    for order_id, target, allocated in rows:
        delta = (target or 0) - (allocated or 0)
        if not delta:
            continue
        largest = bind.execute(
            sa.text(
                """
                SELECT id FROM order_items
                WHERE order_id = :oid
                ORDER BY subtotal DESC, id ASC
                LIMIT 1
                """
            ),
            {"oid": order_id},
        ).scalar()
        if largest is not None:
            bind.execute(
                sa.text(
                    "UPDATE order_items "
                    "SET discount_amount = discount_amount + :d "
                    "WHERE id = :iid"
                ),
                {"d": delta, "iid": largest},
            )

    # Drop the server default: the value is supplied by the application at
    # insert time, and leaving a default invites a silent 0 on a path that
    # forgot to allocate.
    with op.batch_alter_table("order_items") as batch:
        batch.alter_column("discount_amount", server_default=None)


def downgrade() -> None:
    op.drop_column("order_items", "discount_amount")
    op.drop_column("products", "compare_at_price")
