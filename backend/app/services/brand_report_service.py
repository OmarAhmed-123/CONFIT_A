"""Authoritative data source for brand product/sales reporting.

WHY THIS IS A SERVICE AND NOT PDF CODE
--------------------------------------
The PDF must never become a second source of truth. If the report computed its
own "units sold" the dashboard and the PDF would drift the moment either
changed, and a brand would receive an invoice-shaped document disagreeing with
the screen it was read from. So the numbers live here, in one place, and the
renderer is a dumb consumer of this output (DRY + a clean reporting pipeline).

WHAT THE NUMBERS MEAN (stated, not implied)
-------------------------------------------
Every figure is derived from authoritative commerce records -- `orders` and
`order_items` -- never from display counters:

  units_sold    SUM(order_items.quantity) for revenue-eligible orders.
  gross_sales   SUM(order_items.quantity * order_items.unit_price), the price
                actually captured on the line at purchase time, so later
                re-pricing cannot rewrite history.
  returned_units SUM(quantity) of lines flagged is_returned. NOTE: that flag
                marks an OPENED return, not a completed refund, so this is
                reported as "returns opened" and never silently called a refund.
  net_sales     gross_sales minus the value of returned lines. Labelled
                "net of returns opened" for the same reason.
  return_rate   returned_units / units_sold, and **None** when units_sold is 0.
                A rate with an empty denominator is undefined, not 0% and not
                infinity. The renderer prints N/A.

Revenue eligibility is delegated to `revenue_policy.revenue_eligible`, the same
predicate the analytics endpoints use, so the report and the dashboard cannot
disagree about which orders count.

Stock figures come from `product_skus.stock_level` (the sellable pool) and
`store_inventories` (the BOPIS pool), reported separately because they are
different things and summing them would double-count.

TENANCY
-------
Every query is filtered by `brand_id` at the database level. The caller resolves
that id from the authenticated user; this service never accepts a brand id from
a client payload.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.money import quantize_money, to_decimal
from backend.app.core.revenue_policy import REVENUE_BASIS, revenue_eligible
from backend.app.models.catalog import (Category, Product, ProductSKU,
                                        StoreInventory, StoreLocation)
from backend.app.models.commerce import Order, OrderItem
from backend.app.models.user import BrandProfile


class BrandReportService:
    """Builds the product/sales dataset behind the brand report."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ #
    def build_product_sales_report(
        self,
        brand_id: int,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        category_id: Optional[int] = None,
        product_id: Optional[int] = None,
        include_zero_sales: bool = True,
    ) -> Dict[str, Any]:
        """Return the full report payload for one brand.

        Filters are applied in SQL, not in Python, so a large catalog does not
        have to be materialised to be narrowed.
        """
        brand = self.db.get(BrandProfile, brand_id)
        if not brand:
            raise ValueError(f"Brand {brand_id} not found")

        # --- catalog side -------------------------------------------------
        cat_q = (
            select(Product.id, Product.title, Product.base_price, Product.currency,
                   Product.color_family, Category.name.label("category_name"))
            .join(Category, Category.id == Product.category_id, isouter=True)
            .where(Product.brand_id == brand_id)
        )
        if category_id is not None:
            cat_q = cat_q.where(Product.category_id == category_id)
        if product_id is not None:
            cat_q = cat_q.where(Product.id == product_id)
        products = self.db.execute(cat_q.order_by(Product.title)).all()
        product_ids = [p.id for p in products]

        # --- sales side: ONE grouped query, filtered by the same predicates -
        sales: Dict[int, Dict[str, Any]] = {}
        if product_ids:
            sales_q = (
                select(
                    OrderItem.product_id,
                    func.coalesce(func.sum(OrderItem.quantity), 0).label("units"),
                    func.coalesce(
                        func.sum(OrderItem.quantity * OrderItem.unit_price), 0
                    ).label("gross"),
                    func.coalesce(func.sum(
                        func.coalesce(OrderItem.quantity, 0)
                        * func.cast(OrderItem.is_returned, __import__("sqlalchemy").Integer)
                    ), 0).label("returned_units"),
                    func.coalesce(func.sum(
                        OrderItem.quantity * OrderItem.unit_price
                        * func.cast(OrderItem.is_returned, __import__("sqlalchemy").Integer)
                    ), 0).label("returned_value"),
                )
                .join(Order, Order.id == OrderItem.order_id)
                .where(OrderItem.brand_id == brand_id,
                       OrderItem.product_id.in_(product_ids),
                       revenue_eligible(Order.status))
                .group_by(OrderItem.product_id)
            )
            if date_from is not None:
                sales_q = sales_q.where(Order.created_at >= date_from)
            if date_to is not None:
                sales_q = sales_q.where(Order.created_at <= date_to)
            for row in self.db.execute(sales_q).all():
                sales[row.product_id] = {
                    "units": int(row.units or 0),
                    "gross": quantize_money(to_decimal(row.gross or 0)),
                    "returned_units": int(row.returned_units or 0),
                    "returned_value": quantize_money(to_decimal(row.returned_value or 0)),
                }

        # --- stock: sellable pool and BOPIS pool, kept separate -------------
        stock: Dict[int, Dict[str, int]] = {}
        if product_ids:
            for pid, lvl, skus in self.db.execute(
                select(ProductSKU.product_id,
                       func.coalesce(func.sum(ProductSKU.stock_level), 0),
                       func.count(ProductSKU.id))
                .where(ProductSKU.product_id.in_(product_ids))
                .group_by(ProductSKU.product_id)
            ).all():
                stock[pid] = {"stock_level": int(lvl or 0), "sku_count": int(skus or 0)}

            for pid, qty, res in self.db.execute(
                select(ProductSKU.product_id,
                       func.coalesce(func.sum(StoreInventory.quantity), 0),
                       func.coalesce(func.sum(StoreInventory.reserved_quantity), 0))
                .join(StoreInventory, StoreInventory.sku_id == ProductSKU.id)
                .join(StoreLocation, StoreLocation.id == StoreInventory.store_id)
                .where(ProductSKU.product_id.in_(product_ids),
                       # Tenant-safe: the store must belong to this brand too.
                       StoreLocation.brand_id == brand_id)
                .group_by(ProductSKU.product_id)
            ).all():
                stock.setdefault(pid, {"stock_level": 0, "sku_count": 0})
                stock[pid]["bopis_quantity"] = int(qty or 0)
                stock[pid]["bopis_reserved"] = int(res or 0)

        # --- assemble -------------------------------------------------------
        rows: List[Dict[str, Any]] = []
        for p in products:
            s = sales.get(p.id)
            st = stock.get(p.id, {})
            units = s["units"] if s else 0
            if not include_zero_sales and units == 0:
                continue
            gross = s["gross"] if s else Decimal("0.00")
            ret_units = s["returned_units"] if s else 0
            ret_value = s["returned_value"] if s else Decimal("0.00")
            rows.append({
                "product_id": p.id,
                "title": p.title,
                "category": p.category_name or "Uncategorised",
                "color": p.color_family or "—",
                "currency": p.currency or "AED",
                "list_price": quantize_money(to_decimal(p.base_price or 0)),
                "sku_count": st.get("sku_count", 0),
                "units_sold": units,
                "gross_sales": gross,
                "returned_units": ret_units,
                "net_sales": quantize_money(gross - ret_value),
                # Undefined, not zero, when nothing was sold.
                "return_rate": (round(ret_units / units * 100, 1) if units else None),
                "stock_level": st.get("stock_level", 0),
                "bopis_quantity": st.get("bopis_quantity", 0),
                "bopis_reserved": st.get("bopis_reserved", 0),
            })

        total_units = sum(r["units_sold"] for r in rows)
        total_gross = quantize_money(sum((r["gross_sales"] for r in rows), Decimal("0.00")))
        total_net = quantize_money(sum((r["net_sales"] for r in rows), Decimal("0.00")))
        total_returned = sum(r["returned_units"] for r in rows)

        return {
            "brand": {"id": brand.id, "name": brand.brand_name, "slug": brand.slug},
            "generated_at": datetime.now(timezone.utc),
            "period": {
                "from": date_from,
                "to": date_to,
                "label": self._period_label(date_from, date_to),
            },
            "filters": {"category_id": category_id, "product_id": product_id,
                        "include_zero_sales": include_zero_sales},
            "rows": rows,
            "totals": {
                "products": len(rows),
                "units_sold": total_units,
                "gross_sales": total_gross,
                "net_sales": total_net,
                "returned_units": total_returned,
                "return_rate": (round(total_returned / total_units * 100, 1)
                                if total_units else None),
                "currency": rows[0]["currency"] if rows else "AED",
            },
            "methodology": (
                "Units and sales are summed from order_items joined to orders, "
                f"counting only revenue-eligible orders ({REVENUE_BASIS}); the same "
                "predicate the analytics dashboard uses, so the two cannot disagree. "
                "Gross sales use the unit price captured on the line at purchase time. "
                "'Returns' counts order lines flagged is_returned, which marks an "
                "OPENED return request, not a completed refund; net sales are therefore "
                "labelled net of returns opened. A return rate with no units sold is "
                "reported as N/A because it is undefined, never 0%. Sellable stock "
                "(product_skus.stock_level) and in-store BOPIS stock (store_inventories) "
                "are shown separately because they are different pools and adding them "
                "would double-count."
            ),
        }

    @staticmethod
    def _period_label(date_from: Optional[datetime], date_to: Optional[datetime]) -> str:
        if not date_from and not date_to:
            return "All time (no date filter applied)"
        fmt = "%d %b %Y"
        if date_from and date_to:
            return f"{date_from.strftime(fmt)} – {date_to.strftime(fmt)}"
        if date_from:
            return f"From {date_from.strftime(fmt)}"
        return f"Up to {date_to.strftime(fmt)}"
