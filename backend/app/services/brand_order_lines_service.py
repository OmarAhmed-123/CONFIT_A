"""Per-line sales visibility for a brand: who bought what, and what it earned.

WHY THIS EXISTS
---------------
Before this service the only order-derived surface a brand had was
`build_product_sales_report`, which is AGGREGATE — units and revenue rolled up
per product. A brand could see "14 units of the Navy Blazer" but could not
answer any of the operational questions that actually matter when stock leaves
a shelf:

  - which order, and when
  - which customer is expecting it
  - which size / colour left inventory, and how many
  - which store the pickup is against, if any
  - what the line grossed, what discount it bore, and what it NETS

That last triple is the point. `orders.discount_amount` is order-wide and, until
migration 0025, was never apportioned, so "what did I actually earn on this
line" had no answer anywhere in the system.

TENANT ISOLATION
----------------
Every query filters `OrderItem.brand_id == brand_id`. A brand sees its own
lines and nothing else, even when an order spans several brands — which is the
normal case here, since one cart is deliberately partitioned into per-brand
fulfillment groups. The order's own totals are NOT exposed for that reason:
they describe a basket this brand only partly owns, and showing them would
disclose another brand's revenue.

PERSONAL DATA
-------------
A brand is the fulfilling party, so it receives the shipping recipient's name
and destination city — the minimum needed to pick, pack and hand over an order.
Email, phone and the full street address are deliberately NOT returned by this
service. They are available to the fulfillment surfaces that genuinely need
them; a sales-visibility list does not.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.money import quantize_money, to_decimal
from backend.app.core.revenue_policy import revenue_eligible
from backend.app.models.catalog import Product, ProductSKU, StoreLocation
from backend.app.models.commerce import (
    FulfillmentGroup,
    Order,
    OrderItem,
)
from backend.app.models.user import User


class BrandOrderLinesService:
    """Read-only per-line sales view, scoped to one brand."""

    def __init__(self, db: Session):
        self.db = db

    def build_order_lines(
        self,
        brand_id: int,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        product_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Return this brand's order lines, newest first.

        One query for the page and one for the totals. The totals are computed
        over the WHOLE filtered set, not just the returned page — a brand
        reading "net 4,210.00" at the top of a paginated table must not be
        reading the total of the 20 rows it can currently see.
        """
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))

        base_filters = [
            OrderItem.brand_id == brand_id,
            revenue_eligible(Order.status),
        ]
        if date_from is not None:
            base_filters.append(Order.created_at >= date_from)
        if date_to is not None:
            base_filters.append(Order.created_at <= date_to)
        if product_id is not None:
            base_filters.append(OrderItem.product_id == product_id)
        if status:
            base_filters.append(Order.status == status)

        # --- the page ------------------------------------------------------
        # LEFT joins throughout: a SKU can be deleted (SET NULL), an order can
        # be a guest order with no user, and a delivery order has no store.
        # None of those should make the line disappear from the brand's view.
        rows_q = (
            select(
                OrderItem.id.label("line_id"),
                OrderItem.quantity,
                OrderItem.unit_price,
                OrderItem.subtotal,
                OrderItem.discount_amount,
                OrderItem.size,
                OrderItem.color,
                OrderItem.product_title,
                OrderItem.product_id,
                OrderItem.is_returned,
                ProductSKU.sku_code,
                ProductSKU.stock_level,
                Product.thumbnail_url,
                Order.id.label("order_id"),
                Order.order_number,
                Order.created_at,
                Order.status,
                Order.currency,
                Order.payment_status,
                Order.payment_method,
                Order.fulfillment_type,
                Order.shipping_recipient_name,
                Order.shipping_city,
                Order.guest_email,
                Order.promo_code,
                User.full_name.label("account_name"),
                StoreLocation.id.label("store_id"),
                StoreLocation.name.label("store_name"),
                FulfillmentGroup.status.label("fulfillment_status"),
                FulfillmentGroup.tracking_number,
            )
            .join(Order, Order.id == OrderItem.order_id)
            .join(Product, Product.id == OrderItem.product_id, isouter=True)
            .join(ProductSKU, ProductSKU.id == OrderItem.product_sku_id, isouter=True)
            .join(User, User.id == Order.user_id, isouter=True)
            .join(
                FulfillmentGroup,
                FulfillmentGroup.id == OrderItem.fulfillment_group_id,
                isouter=True,
            )
            .join(
                StoreLocation,
                StoreLocation.id == func.coalesce(
                    FulfillmentGroup.store_id, Order.bopis_store_id
                ),
                isouter=True,
            )
            .where(*base_filters)
            .order_by(Order.created_at.desc(), OrderItem.id.desc())
            .limit(limit)
            .offset(offset)
        )

        lines: List[Dict[str, Any]] = []
        for r in self.db.execute(rows_q).all():
            gross = quantize_money(to_decimal(r.subtotal or 0))
            discount = quantize_money(to_decimal(r.discount_amount or 0))
            net = quantize_money(gross - discount)
            lines.append(
                {
                    "line_id": r.line_id,
                    "order_id": r.order_id,
                    "order_number": r.order_number,
                    "placed_at": r.created_at,
                    "order_status": r.status,
                    "fulfillment_status": r.fulfillment_status,
                    "fulfillment_type": r.fulfillment_type,
                    "tracking_number": r.tracking_number,
                    "payment_status": r.payment_status,
                    "payment_method": r.payment_method,
                    # --- customer (minimum needed to fulfil) ---------------
                    "customer_name": self._customer_label(
                        r.shipping_recipient_name, r.account_name, r.guest_email
                    ),
                    "customer_city": r.shipping_city,
                    # --- what left inventory --------------------------------
                    "product_id": r.product_id,
                    "product_title": r.product_title,
                    "thumbnail_url": r.thumbnail_url,
                    "sku_code": r.sku_code,
                    "size": r.size,
                    "color": r.color,
                    "quantity": int(r.quantity or 0),
                    # Stock remaining on that SKU right now. None when the SKU
                    # row is gone — stated as unknown rather than as 0, which
                    # would read as "sold out".
                    "sku_stock_remaining": (
                        int(r.stock_level) if r.stock_level is not None else None
                    ),
                    "store_id": r.store_id,
                    "store_name": r.store_name,
                    # --- money ----------------------------------------------
                    "currency": r.currency,
                    "unit_price": quantize_money(to_decimal(r.unit_price or 0)),
                    "gross_amount": gross,
                    "discount_amount": discount,
                    "net_amount": net,
                    "promo_code": r.promo_code,
                    "is_returned": bool(r.is_returned),
                }
            )

        # --- totals over the FULL filtered set, not just this page ---------
        totals_q = (
            select(
                func.count(OrderItem.id).label("line_count"),
                func.coalesce(func.sum(OrderItem.quantity), 0).label("units"),
                func.coalesce(func.sum(OrderItem.subtotal), 0).label("gross"),
                func.coalesce(
                    func.sum(OrderItem.discount_amount), 0
                ).label("discount"),
                func.count(func.distinct(OrderItem.order_id)).label("orders"),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .where(*base_filters)
        )
        t = self.db.execute(totals_q).one()
        gross_total = quantize_money(to_decimal(t.gross or 0))
        discount_total = quantize_money(to_decimal(t.discount or 0))

        return {
            "lines": lines,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "returned": len(lines),
                "total_lines": int(t.line_count or 0),
                "has_more": offset + len(lines) < int(t.line_count or 0),
            },
            "totals": {
                "orders": int(t.orders or 0),
                "lines": int(t.line_count or 0),
                "units": int(t.units or 0),
                # The three figures the brand asked for, stated separately so
                # the arithmetic is auditable rather than implied:
                #   gross  - what the goods listed for
                #   discount - the share of promo discounts these lines bore
                #   net    - what the lines actually earned
                "gross_amount": gross_total,
                "discount_amount": discount_total,
                "net_amount": quantize_money(gross_total - discount_total),
            },
            "filters": {
                "date_from": date_from,
                "date_to": date_to,
                "product_id": product_id,
                "status": status,
            },
        }

    @staticmethod
    def _customer_label(
        recipient: Optional[str],
        account_name: Optional[str],
        guest_email: Optional[str],
    ) -> str:
        """Best available human label for the buyer.

        Order of preference: the name the order ships to, then the account
        holder's name, then a masked guest email. A guest's full email is not
        a name and is not disclosed in full — only enough to distinguish one
        guest order from another when following up.
        """
        if recipient and recipient.strip():
            return recipient.strip()
        if account_name and account_name.strip():
            return account_name.strip()
        if guest_email and "@" in guest_email:
            local, _, domain = guest_email.partition("@")
            head = local[:2] if len(local) > 2 else local[:1]
            return f"{head}{'*' * max(len(local) - len(head), 1)}@{domain}"
        return "Guest"
