"""Advanced Analytics & Business Intelligence Engine for CONFIT_A.

Provides comprehensive, authoritative, role-aware business performance analytics,
trend analysis, branch/store breakdowns, product and inventory health, promotion metrics,
automated business insights, and CSV/PDF export generation.

CORE PRINCIPLES (Strictly Enforced):
1. Single source of truth: All metrics derive directly from authoritative commerce
   models (`Order`, `OrderItem`, `Product`, `ProductSKU`, `StoreLocation`,
   `StoreInventory`, `Promotion`) and adhere to `revenue_policy.revenue_eligible`.
2. Tenant Isolation: Every brand query enforces `brand_id` at the database level.
3. Accurate Financial Definitions:
   - Gross Sales = SUM(quantity * unit_price) for revenue-eligible orders.
   - Net Sales = Gross Sales - Brand-apportioned Discounts - Value of Opened Returns.
   - Undefined rates (0 denominator) return None (rendered as 'N/A'), never 0% or infinity.
4. Timezone & Boundary Safety: All datetime comparisons use naive UTC via `to_naive_utc`.
5. Formula Injection Protection: All exported CSV values starting with `=,+,-,@` are escaped with `'`.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select, or_, and_, desc, case
from sqlalchemy.orm import Session

from backend.app.core.money import quantize_money, to_decimal
from backend.app.core.revenue_policy import REVENUE_BASIS, revenue_eligible
from backend.app.core.timeutils import to_naive_utc
from backend.app.models.catalog import (
    Category,
    Product,
    ProductSKU,
    StoreInventory,
    StoreLocation,
)
from backend.app.models.commerce import Order, OrderItem, Promotion
from backend.app.models.user import BrandProfile, User


def sanitize_csv_cell(value: Any) -> str:
    """Protect against spreadsheet formula injection (CSV Injection / CWE-1236)."""
    if value is None:
        return ""
    val_str = str(value)
    if val_str and val_str[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{val_str}"
    return val_str


class BusinessIntelligenceService:
    """Calculates comprehensive analytics for Brand Owners, Branch Managers, and Platform Admins."""

    sanitize_csv_cell = staticmethod(sanitize_csv_cell)

    def __init__(self, db: Session):
        self.db = db

    # -------------------------------------------------------------------------
    # Date Range & Comparison Resolution
    # -------------------------------------------------------------------------
    @staticmethod
    def resolve_date_windows(
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        days: Optional[int] = None,
        compare: bool = True,
    ) -> Tuple[Optional[datetime], Optional[datetime], Optional[datetime], Optional[datetime], str, Optional[str]]:
        """Resolves current date window and preceding equivalent comparison window.

        Returns (curr_from, curr_to, prev_from, prev_to, curr_label, prev_label).
        """
        now = to_naive_utc(datetime.now(timezone.utc))

        if days is not None and days > 0:
            curr_to = now
            curr_from = curr_to - timedelta(days=days)
            curr_label = f"Last {days} Days"
            if compare:
                prev_to = curr_from
                prev_from = prev_to - timedelta(days=days)
                prev_label = f"Preceding {days} Days"
            else:
                prev_from = prev_to = prev_label = None
            return curr_from, curr_to, prev_from, prev_to, curr_label, prev_label

        c_from = to_naive_utc(date_from)
        c_to = to_naive_utc(date_to)

        if c_from and c_to:
            if c_to < c_from:
                c_from, c_to = c_to, c_from
            delta = c_to - c_from
            fmt = "%d %b %Y"
            curr_label = f"{c_from.strftime(fmt)} – {c_to.strftime(fmt)}"
            if compare and delta.total_seconds() > 0:
                prev_to = c_from
                prev_from = prev_to - delta
                prev_label = f"{prev_from.strftime(fmt)} – {prev_to.strftime(fmt)}"
            else:
                prev_from = prev_to = prev_label = None
            return c_from, c_to, prev_from, prev_to, curr_label, prev_label

        if c_from and not c_to:
            curr_label = f"From {c_from.strftime('%d %b %Y')}"
            return c_from, None, None, None, curr_label, None

        if not c_from and c_to:
            curr_label = f"Up to {c_to.strftime('%d %b %Y')}"
            return None, c_to, None, None, curr_label, None

        # Default: All Time
        return None, None, None, None, "All Time", None

    # -------------------------------------------------------------------------
    # Core Brand Performance Dashboard
    # -------------------------------------------------------------------------
    def get_brand_bi_dashboard(
        self,
        brand_id: int,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        days: Optional[int] = None,
        branch_id: Optional[int] = None,
        category_id: Optional[int] = None,
        compare: bool = True,
    ) -> Dict[str, Any]:
        """Consolidated BI dataset for brand owners and branch managers."""
        brand = self.db.get(BrandProfile, brand_id)
        if not brand:
            raise ValueError(f"Brand ID {brand_id} not found")

        curr_from, curr_to, prev_from, prev_to, curr_label, prev_label = self.resolve_date_windows(
            date_from=date_from, date_to=date_to, days=days, compare=compare
        )

        # 1. Primary Metrics (Current Window)
        current_kpis = self._compute_period_kpis(
            brand_id=brand_id,
            date_from=curr_from,
            date_to=curr_to,
            branch_id=branch_id,
            category_id=category_id,
        )

        # 2. Comparison Metrics (Preceding Window)
        previous_kpis = None
        kpi_growth: Dict[str, Optional[float]] = {}
        kpi_growth_basis: Dict[str, str] = {}
        if prev_from is not None:
            previous_kpis = self._compute_period_kpis(
                brand_id=brand_id,
                date_from=prev_from,
                date_to=prev_to,
                branch_id=branch_id,
                category_id=category_id,
            )
            kpi_growth = self._calculate_growth_rates(current_kpis, previous_kpis)
            kpi_growth_basis = self._growth_basis(current_kpis, previous_kpis)

        # 3. Time Series Trends
        trend_series = self._compute_sales_trend(
            brand_id=brand_id,
            date_from=curr_from,
            date_to=curr_to,
            branch_id=branch_id,
            category_id=category_id,
        )

        # 4. Category Performance & Share
        categories_breakdown = self._compute_category_performance(
            brand_id=brand_id,
            date_from=curr_from,
            date_to=curr_to,
            branch_id=branch_id,
        )

        # 5. Top Products Performance
        products_breakdown = self._compute_product_performance(
            brand_id=brand_id,
            date_from=curr_from,
            date_to=curr_to,
            branch_id=branch_id,
            category_id=category_id,
        )

        # 6. Branch / Location Performance
        branches_breakdown = self._compute_branch_performance(
            brand_id=brand_id,
            date_from=curr_from,
            date_to=curr_to,
            filter_branch_id=branch_id,
        )

        # 7. Inventory Health & Replenishment
        inventory_health = self._compute_inventory_health(
            brand_id=brand_id,
            branch_id=branch_id,
        )

        # 8. Promotion Performance
        promotions_breakdown = self._compute_promotions_performance(
            brand_id=brand_id,
            date_from=curr_from,
            date_to=curr_to,
        )

        # 9. Automated Business Insights
        insights = self._generate_business_insights(
            brand_name=brand.brand_name,
            current_kpis=current_kpis,
            growth=kpi_growth,
            growth_basis=kpi_growth_basis,
            categories=categories_breakdown,
            branches=branches_breakdown,
            inventory=inventory_health,
            period_label=curr_label,
            comparison_label=prev_label,
        )

        return {
            "brand": {
                "id": brand.id,
                "name": brand.brand_name,
                "slug": brand.slug,
                "commission_rate": brand.commission_rate,
                "return_rate_benchmark": brand.return_rate_benchmark,
                "current_return_rate": brand.current_return_rate,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period": {
                "from": curr_from.isoformat() if curr_from else None,
                "to": curr_to.isoformat() if curr_to else None,
                "label": curr_label,
                "comparison_from": prev_from.isoformat() if prev_from else None,
                "comparison_to": prev_to.isoformat() if prev_to else None,
                "comparison_label": prev_label,
            },
            "filters": {
                "branch_id": branch_id,
                "category_id": category_id,
            },
            "kpis": current_kpis,
            "comparison_kpis": previous_kpis,
            "growth": kpi_growth,
            #: key -> ok | no_prior_baseline | no_activity | not_comparable.
            #: Lets the UI say WHY a ratio is absent instead of leaving a gap.
            "growth_basis": kpi_growth_basis,
            "trends": trend_series,
            "categories": categories_breakdown,
            "products": products_breakdown,
            "branches": branches_breakdown,
            "inventory": inventory_health,
            "promotions": promotions_breakdown,
            "insights": insights,
            "methodology": (
                f"Revenue and sales figures are strictly aggregated from revenue-eligible orders ({REVENUE_BASIS}) "
                "under tenant isolation. Gross sales represent line value captured at checkout. "
                "Net sales reflect gross sales minus apportioned promotional discounts and returns opened. "
                "Stock pools distinguish central warehouse units from branch BOPIS inventories."
            ),
        }

    # -------------------------------------------------------------------------
    # KPI Period Calculations
    # -------------------------------------------------------------------------
    def _compute_period_kpis(
        self,
        brand_id: Optional[int],
        date_from: Optional[datetime],
        date_to: Optional[datetime],
        branch_id: Optional[int] = None,
        category_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Calculates accurate, verified financial and commercial totals."""
        # Query OrderItem joined to Order
        q = (
            select(
                func.count(func.distinct(Order.id)).label("orders_count"),
                func.coalesce(func.sum(OrderItem.quantity), 0).label("units_sold"),
                func.coalesce(
                    func.sum(OrderItem.quantity * OrderItem.unit_price), 0
                ).label("gross_sales"),
                func.coalesce(
                    func.sum(OrderItem.discount_amount), 0
                ).label("discount_total"),
                func.coalesce(
                    func.sum(
                        func.coalesce(OrderItem.quantity, 0)
                        * func.cast(OrderItem.is_returned, __import__("sqlalchemy").Integer)
                    ),
                    0,
                ).label("returned_units"),
                func.coalesce(
                    func.sum(
                        OrderItem.quantity
                        * OrderItem.unit_price
                        * func.cast(OrderItem.is_returned, __import__("sqlalchemy").Integer)
                    ),
                    0,
                ).label("returned_value"),
                func.count(
                    func.distinct(
                        func.nullif(
                            case((Order.try_on_assisted == True, Order.id), else_=None),
                            None,
                        )
                    )
                ).label("tryon_assisted_orders"),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .where(revenue_eligible(Order.status))
        )

        if brand_id is not None:
            q = q.where(OrderItem.brand_id == brand_id)
        if branch_id is not None:
            # Attributed to branch via BOPIS pickup
            q = q.where(Order.bopis_store_id == branch_id)
        if category_id is not None:
            q = q.join(Product, Product.id == OrderItem.product_id).where(Product.category_id == category_id)
        if date_from is not None:
            q = q.where(Order.created_at >= date_from)
        if date_to is not None:
            q = q.where(Order.created_at <= date_to)

        res = self.db.execute(q).first()

        orders_count = int(res.orders_count or 0)
        units_sold = int(res.units_sold or 0)
        gross_sales = quantize_money(to_decimal(res.gross_sales or 0))
        discount_total = quantize_money(to_decimal(res.discount_total or 0))
        returned_units = int(res.returned_units or 0)
        returned_value = quantize_money(to_decimal(res.returned_value or 0))
        tryon_orders = int(res.tryon_assisted_orders or 0)

        # Net sales = gross - discount - returned_value
        net_sales = quantize_money(gross_sales - discount_total - returned_value)

        # AOV (Average Order Value)
        aov = (
            quantize_money(gross_sales / Decimal(str(orders_count)))
            if orders_count > 0
            else Decimal("0.00")
        )

        # Return Rate (Returned Units / Units Sold)
        return_rate = (
            round((returned_units / units_sold) * 100, 1)
            if units_sold > 0
            else None
        )

        # Try-on Share
        tryon_share = (
            round((tryon_orders / orders_count) * 100, 1)
            if orders_count > 0
            else None
        )

        # Default currency determination
        currency_q = select(Order.currency).join(OrderItem, OrderItem.order_id == Order.id)
        if brand_id is not None:
            currency_q = currency_q.where(OrderItem.brand_id == brand_id)
        curr_row = self.db.execute(currency_q.limit(1)).scalar()
        currency = curr_row or "USD"

        return {
            "gross_sales": float(gross_sales),
            "net_sales": float(net_sales),
            "discount_total": float(discount_total),
            "returned_value": float(returned_value),
            "orders_count": orders_count,
            "units_sold": units_sold,
            "returned_units": returned_units,
            "average_order_value": float(aov),
            "return_rate": return_rate,
            "tryon_assisted_orders": tryon_orders,
            "tryon_share_pct": tryon_share,
            "currency": currency,
        }

    #: The metrics the dashboard compares period over period.
    GROWTH_METRICS = ("gross_sales", "net_sales", "orders_count", "units_sold", "average_order_value")

    @staticmethod
    def _calculate_growth_rates(current: Dict[str, Any], previous: Dict[str, Any]) -> Dict[str, Optional[float]]:
        """Period-over-period percentage change, with no invented baselines.

        THE DEFECT THIS REPLACES (measured 2026-10-20)
        ----------------------------------------------
        ``prev_val == 0`` returned ``100.0`` whenever the current value was
        positive. A brand in its first month, or one returning after a closed
        month, was shown a green "+100%" on gross sales, net sales, orders,
        units and AOV — five success claims derived from an empty baseline.
        Percentage growth from zero is undefined: there is no denominator. The
        only honest answer is "no comparable baseline", and the number has to be
        absent, not large.

        CONTRACT
        --------
        For current ``C`` and previous ``P``:

        * ``P > 0``                      -> ``(C - P) / P * 100``, rounded to 0.1
        * ``P == 0 and C > 0``           -> ``None``  (undefined; basis
                                            ``no_prior_baseline``)
        * ``P == 0 and C == 0``          -> ``None``  (nothing happened either
                                            period; basis ``no_activity``)
        * ``P is None or C is None``     -> ``None``  (the period was not
                                            measured; basis ``not_comparable``)

        ``None`` means "not calculable", never "zero". Callers must not render it
        as a number, and ``growth_basis`` travels with it so the UI can say WHY
        instead of showing a blank where a chip was expected.
        """
        growth: Dict[str, Optional[float]] = {}
        for key in BusinessIntelligenceService.GROWTH_METRICS:
            curr_val = current.get(key)
            prev_val = previous.get(key)
            if prev_val is None or curr_val is None or prev_val == 0:
                growth[f"{key}_change_pct"] = None
            else:
                change = ((curr_val - prev_val) / prev_val) * 100.0
                growth[f"{key}_change_pct"] = round(change, 1)
        return growth

    @staticmethod
    def _growth_basis(current: Dict[str, Any], previous: Dict[str, Any]) -> Dict[str, str]:
        """Why each growth figure is a number, or absent. Never a guess.

        Returned alongside ``growth`` rather than inside it: ``growth`` is a
        numeric map that the CSV export and the chart layer both iterate, and a
        string value in it would corrupt both.
        """
        basis: Dict[str, str] = {}
        for key in BusinessIntelligenceService.GROWTH_METRICS:
            curr_val = current.get(key)
            prev_val = previous.get(key)
            if prev_val is None or curr_val is None:
                basis[key] = "not_comparable"
            elif prev_val == 0:
                basis[key] = "no_activity" if curr_val == 0 else "no_prior_baseline"
            else:
                basis[key] = "ok"
        return basis

    # -------------------------------------------------------------------------
    # Time Series Trend
    # -------------------------------------------------------------------------
    def _compute_sales_trend(
        self,
        brand_id: Optional[int],
        date_from: Optional[datetime],
        date_to: Optional[datetime],
        branch_id: Optional[int] = None,
        category_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Daily or weekly buckets of revenue and order volume for interactive charting."""
        # Query order items grouped by date
        date_col = func.date(Order.created_at)

        q = (
            select(
                date_col.label("day"),
                func.count(func.distinct(Order.id)).label("orders"),
                func.coalesce(func.sum(OrderItem.quantity), 0).label("units"),
                func.coalesce(
                    func.sum(OrderItem.quantity * OrderItem.unit_price), 0
                ).label("gross"),
                func.coalesce(
                    func.sum(
                        (OrderItem.quantity * OrderItem.unit_price)
                        - func.coalesce(OrderItem.discount_amount, 0)
                        - (
                            OrderItem.quantity
                            * OrderItem.unit_price
                            * func.cast(OrderItem.is_returned, __import__("sqlalchemy").Integer)
                        )
                    ),
                    0,
                ).label("net"),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .where(revenue_eligible(Order.status))
        )

        if brand_id is not None:
            q = q.where(OrderItem.brand_id == brand_id)
        if branch_id is not None:
            q = q.where(Order.bopis_store_id == branch_id)
        if category_id is not None:
            q = q.join(Product, Product.id == OrderItem.product_id).where(Product.category_id == category_id)
        if date_from is not None:
            q = q.where(Order.created_at >= date_from)
        if date_to is not None:
            q = q.where(Order.created_at <= date_to)

        q = q.group_by(date_col).order_by(date_col.asc())
        rows = self.db.execute(q).all()

        points = []
        for r in rows:
            points.append({
                "date": str(r.day),
                "orders": int(r.orders or 0),
                "units": int(r.units or 0),
                "gross_sales": float(quantize_money(to_decimal(r.gross or 0))),
                "net_sales": float(quantize_money(to_decimal(r.net or 0))),
            })
        return points

    # -------------------------------------------------------------------------
    # Category Performance
    # -------------------------------------------------------------------------
    def _compute_category_performance(
        self,
        brand_id: Optional[int],
        date_from: Optional[datetime],
        date_to: Optional[datetime],
        branch_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Breakdown of sales, units and revenue share by product category."""
        q = (
            select(
                Category.id.label("category_id"),
                Category.name.label("category_name"),
                Category.name_ar.label("category_name_ar"),
                func.coalesce(func.sum(OrderItem.quantity), 0).label("units_sold"),
                func.coalesce(
                    func.sum(OrderItem.quantity * OrderItem.unit_price), 0
                ).label("gross_sales"),
            )
            .join(Product, Product.category_id == Category.id)
            .join(OrderItem, OrderItem.product_id == Product.id)
            .join(Order, Order.id == OrderItem.order_id)
            .where(revenue_eligible(Order.status))
        )

        if brand_id is not None:
            q = q.where(OrderItem.brand_id == brand_id)
        if branch_id is not None:
            q = q.where(Order.bopis_store_id == branch_id)
        if date_from is not None:
            q = q.where(Order.created_at >= date_from)
        if date_to is not None:
            q = q.where(Order.created_at <= date_to)

        q = q.group_by(Category.id, Category.name, Category.name_ar).order_by(desc("gross_sales"))
        rows = self.db.execute(q).all()

        total_gross = sum((to_decimal(r.gross_sales or 0) for r in rows), Decimal("0.00"))
        items = []
        for r in rows:
            gross = quantize_money(to_decimal(r.gross_sales or 0))
            share = round(float((gross / total_gross) * 100), 1) if total_gross > 0 else 0.0
            items.append({
                "category_id": r.category_id,
                "category_name": r.category_name,
                "category_name_ar": r.category_name_ar,
                "units_sold": int(r.units_sold or 0),
                "gross_sales": float(gross),
                "share_pct": share,
            })
        return items

    # -------------------------------------------------------------------------
    # Product Performance
    # -------------------------------------------------------------------------
    def _compute_product_performance(
        self,
        brand_id: Optional[int],
        date_from: Optional[datetime],
        date_to: Optional[datetime],
        branch_id: Optional[int] = None,
        category_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Top performing products with SKU stock levels and return rates."""
        # 1. Product Sales Query
        q = (
            select(
                Product.id.label("product_id"),
                Product.title.label("title"),
                Category.name.label("category_name"),
                Product.base_price.label("base_price"),
                Product.currency.label("currency"),
                func.coalesce(func.sum(OrderItem.quantity), 0).label("units_sold"),
                func.coalesce(
                    func.sum(OrderItem.quantity * OrderItem.unit_price), 0
                ).label("gross_sales"),
                func.coalesce(
                    func.sum(
                        func.coalesce(OrderItem.quantity, 0)
                        * func.cast(OrderItem.is_returned, __import__("sqlalchemy").Integer)
                    ),
                    0,
                ).label("returned_units"),
            )
            .join(Category, Category.id == Product.category_id, isouter=True)
            .join(OrderItem, OrderItem.product_id == Product.id)
            .join(Order, Order.id == OrderItem.order_id)
            .where(revenue_eligible(Order.status))
        )

        if brand_id is not None:
            q = q.where(Product.brand_id == brand_id)
        if branch_id is not None:
            q = q.where(Order.bopis_store_id == branch_id)
        if category_id is not None:
            q = q.where(Product.category_id == category_id)
        if date_from is not None:
            q = q.where(Order.created_at >= date_from)
        if date_to is not None:
            q = q.where(Order.created_at <= date_to)

        q = q.group_by(Product.id, Product.title, Category.name, Product.base_price, Product.currency).order_by(desc("gross_sales"))
        sales_rows = self.db.execute(q).all()

        # 2. Collect Stock Levels
        pids = [r.product_id for r in sales_rows]
        stock_map: Dict[int, int] = {}
        if pids:
            for pid, stock in self.db.execute(
                select(ProductSKU.product_id, func.coalesce(func.sum(ProductSKU.stock_level), 0))
                .where(ProductSKU.product_id.in_(pids))
                .group_by(ProductSKU.product_id)
            ).all():
                stock_map[pid] = int(stock or 0)

        results = []
        for r in sales_rows:
            units = int(r.units_sold or 0)
            ret = int(r.returned_units or 0)
            rate = round((ret / units) * 100, 1) if units > 0 else None
            results.append({
                "product_id": r.product_id,
                "title": r.title,
                "category": r.category_name or "Uncategorized",
                "base_price": float(r.base_price or 0.0),
                "currency": r.currency or "USD",
                "units_sold": units,
                "gross_sales": float(quantize_money(to_decimal(r.gross_sales or 0))),
                "returned_units": ret,
                "return_rate": rate,
                "stock_level": stock_map.get(r.product_id, 0),
            })
        return results

    # -------------------------------------------------------------------------
    # Branch Performance
    # -------------------------------------------------------------------------
    def _compute_branch_performance(
        self,
        brand_id: Optional[int],
        date_from: Optional[datetime],
        date_to: Optional[datetime],
        filter_branch_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Branch-level commercial sales, BOPIS order counts, and on-hand stock."""
        # 1. Fetch stores
        store_q = select(StoreLocation)
        if brand_id is not None:
            store_q = store_q.where(StoreLocation.brand_id == brand_id)
        if filter_branch_id is not None:
            store_q = store_q.where(StoreLocation.id == filter_branch_id)
        stores = self.db.execute(store_q.order_by(StoreLocation.name)).scalars().all()

        if not stores:
            return []

        store_ids = [s.id for s in stores]

        # 2. Sales per branch (via BOPIS orders)
        bopis_q = (
            select(
                Order.bopis_store_id.label("store_id"),
                func.count(func.distinct(Order.id)).label("orders_count"),
                func.coalesce(func.sum(OrderItem.quantity), 0).label("units_sold"),
                func.coalesce(
                    func.sum(OrderItem.quantity * OrderItem.unit_price), 0
                ).label("gross_sales"),
            )
            .join(OrderItem, OrderItem.order_id == Order.id)
            .where(
                Order.bopis_store_id.in_(store_ids),
                revenue_eligible(Order.status),
            )
        )
        if brand_id is not None:
            bopis_q = bopis_q.where(OrderItem.brand_id == brand_id)
        if date_from is not None:
            bopis_q = bopis_q.where(Order.created_at >= date_from)
        if date_to is not None:
            bopis_q = bopis_q.where(Order.created_at <= date_to)

        bopis_q = bopis_q.group_by(Order.bopis_store_id)
        sales_by_store = {
            r.store_id: {
                "orders": int(r.orders_count or 0),
                "units": int(r.units_sold or 0),
                "gross": float(quantize_money(to_decimal(r.gross_sales or 0))),
            }
            for r in self.db.execute(bopis_q).all()
        }

        # 3. Stock per branch
        inv_q = (
            select(
                StoreInventory.store_id,
                func.coalesce(func.sum(StoreInventory.quantity), 0).label("total_units"),
                func.coalesce(func.sum(StoreInventory.reserved_quantity), 0).label("reserved_units"),
                func.count(
                    case(
                        (StoreInventory.quantity <= 5, StoreInventory.id),
                        else_=None,
                    )
                ).label("low_stock_skus"),
            )
            .where(StoreInventory.store_id.in_(store_ids))
        )
        if brand_id is not None:
            inv_q = inv_q.where(StoreInventory.brand_id == brand_id)
        inv_q = inv_q.group_by(StoreInventory.store_id)

        inv_by_store = {
            r.store_id: {
                "total_units": int(r.total_units or 0),
                "reserved_units": int(r.reserved_units or 0),
                "available_units": max(0, int(r.total_units or 0) - int(r.reserved_units or 0)),
                "low_stock_skus": int(r.low_stock_skus or 0),
            }
            for r in self.db.execute(inv_q).all()
        }

        branches = []
        for s in stores:
            sales = sales_by_store.get(s.id, {"orders": 0, "units": 0, "gross": 0.0})
            inv = inv_by_store.get(s.id, {"total_units": 0, "reserved_units": 0, "available_units": 0, "low_stock_skus": 0})
            branches.append({
                "store_id": s.id,
                "name": s.name,
                "name_ar": s.name_ar,
                "city": s.city,
                "country": s.country,
                "address": s.address,
                "is_bopis_enabled": s.is_bopis_enabled,
                "orders_count": sales["orders"],
                "units_sold": sales["units"],
                "gross_sales": sales["gross"],
                "available_stock": inv["available_units"],
                "reserved_stock": inv["reserved_units"],
                "low_stock_skus": inv["low_stock_skus"],
            })
        return branches

    # -------------------------------------------------------------------------
    # Inventory Health & Replenishment
    # -------------------------------------------------------------------------
    def _compute_inventory_health(
        self,
        brand_id: Optional[int],
        branch_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Analyzes stock levels, low-stock alerts (<= 5 units), and out-of-stock items."""
        # 1. Warehouse Sellable Stock (ProductSKU)
        sku_q = select(ProductSKU).join(Product, Product.id == ProductSKU.product_id)
        if brand_id is not None:
            sku_q = sku_q.where(Product.brand_id == brand_id)
        all_skus = self.db.execute(sku_q).scalars().all()

        total_skus = len(all_skus)
        total_warehouse_units = sum(s.stock_level for s in all_skus)
        in_stock_skus = sum(1 for s in all_skus if s.stock_level > 5)
        low_stock_skus = sum(1 for s in all_skus if 0 < s.stock_level <= 5)
        out_of_stock_skus = sum(1 for s in all_skus if s.stock_level == 0)

        # 2. Branch BOPIS Stock (StoreInventory)
        inv_q = select(StoreInventory)
        if brand_id is not None:
            inv_q = inv_q.where(StoreInventory.brand_id == brand_id)
        if branch_id is not None:
            inv_q = inv_q.where(StoreInventory.store_id == branch_id)
        branch_invs = self.db.execute(inv_q).scalars().all()
        total_branch_units = sum(i.quantity for i in branch_invs)

        # 3. Replenishment Action Items (SKUs requiring immediate order)
        low_stock_items = []
        for s in all_skus:
            if s.stock_level <= 5:
                low_stock_items.append({
                    "sku_id": s.id,
                    "sku_code": s.sku_code,
                    "product_id": s.product_id,
                    "product_title": s.product.title if s.product else "Product",
                    "size": s.size,
                    "color": s.color,
                    "stock_level": s.stock_level,
                    "status": "out_of_stock" if s.stock_level == 0 else "low_stock",
                    # A RULE OF THUMB, not a forecast.
                    #
                    # This is `20` when the SKU is out and `15 - stock` otherwise:
                    # no sales velocity, no lead time, no safety stock, no
                    # seasonality. It is useful as a starting point and
                    # misleading as a recommendation, so it travels with
                    # `reorder_basis` and the dashboard labels it as an estimate
                    # rather than printing a bare "+N units" that reads as
                    # computed advice. Deriving a real reorder point needs
                    # demand history these tables do not carry for every SKU.
                    "recommended_reorder": 20 if s.stock_level == 0 else (15 - s.stock_level),
                    "reorder_basis": "rule_of_thumb",
                })

        return {
            "total_skus": total_skus,
            "total_warehouse_units": total_warehouse_units,
            "total_branch_bopis_units": total_branch_units,
            "in_stock_count": in_stock_skus,
            "low_stock_count": low_stock_skus,
            "out_of_stock_count": out_of_stock_skus,
            "replenishment_items": low_stock_items[:15],
        }

    # -------------------------------------------------------------------------
    # Promotion Performance
    # -------------------------------------------------------------------------
    def _compute_promotions_performance(
        self,
        brand_id: Optional[int],
        date_from: Optional[datetime],
        date_to: Optional[datetime],
    ) -> List[Dict[str, Any]]:
        """Analyzes active promotions, redemption frequency, and total discounts applied."""
        promo_q = select(Promotion)
        if brand_id is not None:
            promo_q = promo_q.where(Promotion.brand_id == brand_id)
        promos = self.db.execute(promo_q).scalars().all()

        if not promos:
            return []

        # Find orders that used promo codes in period
        order_q = (
            select(
                Order.promo_code,
                func.count(func.distinct(Order.id)).label("redemptions"),
                func.coalesce(func.sum(Order.discount_amount), 0).label("total_discount"),
                func.coalesce(func.sum(Order.total_amount), 0).label("revenue_generated"),
            )
            .where(
                Order.promo_code.is_not(None),
                revenue_eligible(Order.status),
            )
        )
        if date_from is not None:
            order_q = order_q.where(Order.created_at >= date_from)
        if date_to is not None:
            order_q = order_q.where(Order.created_at <= date_to)

        order_q = order_q.group_by(Order.promo_code)
        usage_map = {
            r.promo_code.upper(): {
                "redemptions": int(r.redemptions or 0),
                "total_discount": float(quantize_money(to_decimal(r.total_discount or 0))),
                "revenue_generated": float(quantize_money(to_decimal(r.revenue_generated or 0))),
            }
            for r in self.db.execute(order_q).all()
            if r.promo_code
        }

        now = datetime.now(timezone.utc)
        results = []
        for p in promos:
            code_upper = p.code.upper()
            usage = usage_map.get(code_upper, {"redemptions": 0, "total_discount": 0.0, "revenue_generated": 0.0})

            # Check expiration
            is_expired = False
            if p.expires_at:
                exp_naive = to_naive_utc(p.expires_at)
                now_naive = to_naive_utc(now)
                if exp_naive and now_naive and exp_naive < now_naive:
                    is_expired = True

            results.append({
                "id": p.id,
                "code": p.code,
                "description": p.description,
                "discount_type": p.discount_type,
                "discount_value": p.discount_value,
                "is_active": p.is_active and not is_expired,
                "is_expired": is_expired,
                "redemptions": usage["redemptions"],
                "total_discount": usage["total_discount"],
                "revenue_generated": usage["revenue_generated"],
            })
        return results

    # -------------------------------------------------------------------------
    # Automated Business Insights
    # -------------------------------------------------------------------------
    @staticmethod
    def _generate_business_insights(
        brand_name: str,
        current_kpis: Dict[str, Any],
        growth: Dict[str, Optional[float]],
        categories: List[Dict[str, Any]],
        branches: List[Dict[str, Any]],
        inventory: Dict[str, Any],
        period_label: str,
        comparison_label: Optional[str],
        growth_basis: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """Synthesizes factual, rule-based operational insights without speculation."""
        insights = []

        # 1. Period Performance Insight
        rev_change = growth.get("gross_sales_change_pct")
        # No comparable baseline is a FACT worth stating, not a gap to hide.
        # Before this, a zero previous period produced "+100% surged" — an
        # invented success. Now the dashboard says what actually happened.
        if (
            rev_change is None
            and comparison_label
            and (growth_basis or {}).get("gross_sales") == "no_prior_baseline"
        ):
            insights.append({
                "type": "performance",
                "severity": "info",
                "title": f"First Sales Period ({period_label})",
                "message": (
                    f"{brand_name} recorded {current_kpis['currency']} "
                    f"{current_kpis['gross_sales']:,.2f} in gross sales this period. "
                    f"The preceding period ({comparison_label}) had none, so no "
                    f"growth percentage is shown — a change from zero has no "
                    f"percentage baseline."
                ),
            })
        elif rev_change is not None and comparison_label:
            direction = "surged by" if rev_change > 0 else "decreased by" if rev_change < 0 else "remained steady compared to"
            insights.append({
                "type": "performance",
                "severity": "positive" if rev_change >= 0 else "warning",
                "title": f"Revenue Trend ({period_label})",
                "message": (
                    f"{brand_name} gross sales {direction} {abs(rev_change)}% "
                    f"compared to the preceding period ({comparison_label}). "
                    f"Current period total: {current_kpis['currency']} {current_kpis['gross_sales']:,.2f}."
                ),
            })

        # 2. Category Share Insight
        if categories:
            top_cat = categories[0]
            insights.append({
                "type": "category",
                "severity": "info",
                "title": f"Leading Category: {top_cat['category_name']}",
                "message": (
                    f"{top_cat['category_name']} represents {top_cat['share_pct']}% of recorded brand sales, "
                    f"generating {current_kpis['currency']} {top_cat['gross_sales']:,.2f} across {top_cat['units_sold']} units."
                ),
            })

        # 3. Branch Performance Insight
        active_branches = [b for b in branches if b["gross_sales"] > 0]
        if active_branches:
            top_branch = max(branches, key=lambda b: b["gross_sales"])
            insights.append({
                "type": "branch",
                "severity": "info",
                "title": f"Flagship Branch: {top_branch['name']}",
                "message": (
                    f"{top_branch['name']} ({top_branch['city']}) leads branch omnichannel performance with "
                    f"{top_branch['orders_count']} completed orders and {top_branch['available_stock']} units available in stock."
                ),
            })

        # 4. Inventory Alert Insight
        out_count = inventory.get("out_of_stock_count", 0)
        low_count = inventory.get("low_stock_count", 0)
        if out_count > 0 or low_count > 0:
            insights.append({
                "type": "inventory",
                "severity": "alert" if out_count > 0 else "warning",
                "title": "Inventory Replenishment Required",
                "message": (
                    f"{out_count} SKUs are completely out of stock and {low_count} SKUs are at or below safety stock (<= 5 units). "
                    "Restocking recommended to avoid lost sales."
                ),
            })

        # 5. Virtual Try-On Impact Insight
        tryon_share = current_kpis.get("tryon_share_pct")
        if tryon_share is not None and tryon_share > 0:
            insights.append({
                "type": "vton_impact",
                "severity": "positive",
                "title": "Virtual Try-On Adoption",
                "message": (
                    f"{tryon_share}% of completed orders were assisted by Virtual Try-On / Fit Finder. "
                    f"Recorded return rate for the period stands at {current_kpis.get('return_rate') or 0}%."
                ),
            })

        return insights

    # -------------------------------------------------------------------------
    # Platform Admin Overview
    # -------------------------------------------------------------------------
    def get_admin_bi_dashboard(
        self,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        days: Optional[int] = None,
        brand_id: Optional[int] = None,
        compare: bool = True,
    ) -> Dict[str, Any]:
        """Platform-wide analytics for authorized platform administrators."""
        curr_from, curr_to, prev_from, prev_to, curr_label, prev_label = self.resolve_date_windows(
            date_from=date_from, date_to=date_to, days=days, compare=compare
        )

        # 1. Macro KPIs
        curr_kpis = self._compute_period_kpis(
            brand_id=brand_id,
            date_from=curr_from,
            date_to=curr_to,
        )

        prev_kpis = None
        growth = {}
        if prev_from is not None:
            prev_kpis = self._compute_period_kpis(
                brand_id=brand_id,
                date_from=prev_from,
                date_to=prev_to,
            )
            growth = self._calculate_growth_rates(curr_kpis, prev_kpis)

        # 2. Multi-currency GMV Breakdown (Guarding against multi-currency summing)
        in_order_window = []
        if curr_from:
            in_order_window.append(Order.created_at >= curr_from)
        if curr_to:
            in_order_window.append(Order.created_at <= curr_to)

        gmv_rows = (
            self.db.query(Order.currency, func.sum(Order.total_amount), func.count(Order.id))
            .filter(revenue_eligible(Order.status), *in_order_window)
            .group_by(Order.currency)
            .all()
        )
        gmv_by_currency = {
            str(c or "USD").upper(): float(quantize_money(to_decimal(amt or 0)))
            for c, amt, _ in gmv_rows
        }

        # 3. Cross-Brand Performance Table
        brand_q = select(BrandProfile).order_by(BrandProfile.brand_name)
        if brand_id:
            brand_q = brand_q.where(BrandProfile.id == brand_id)
        all_brands = self.db.execute(brand_q).scalars().all()

        brand_perf = []
        for b in all_brands:
            b_kpis = self._compute_period_kpis(brand_id=b.id, date_from=curr_from, date_to=curr_to)
            prod_count = self.db.query(func.count(Product.id)).filter(Product.brand_id == b.id).scalar() or 0
            store_count = self.db.query(func.count(StoreLocation.id)).filter(StoreLocation.brand_id == b.id).scalar() or 0
            brand_perf.append({
                "brand_id": b.id,
                "brand_name": b.brand_name,
                "slug": b.slug,
                "is_verified": b.is_verified,
                "products_count": prod_count,
                "stores_count": store_count,
                "orders_count": b_kpis["orders_count"],
                "gross_sales": b_kpis["gross_sales"],
                "currency": b_kpis["currency"],
                "return_rate": b_kpis["return_rate"],
            })

        # 4. Global Trends
        trend_series = self._compute_sales_trend(
            brand_id=brand_id,
            date_from=curr_from,
            date_to=curr_to,
        )

        return {
            "period": {
                "from": curr_from.isoformat() if curr_from else None,
                "to": curr_to.isoformat() if curr_to else None,
                "label": curr_label,
                "comparison_label": prev_label,
            },
            "kpis": curr_kpis,
            "comparison_kpis": prev_kpis,
            "growth": growth,
            "gmv_by_currency": gmv_by_currency,
            "brands_performance": brand_perf,
            "trends": trend_series,
            "total_brands": len(all_brands),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # -------------------------------------------------------------------------
    # CSV Export (Formula Injection Safe)
    # -------------------------------------------------------------------------
    def export_brand_bi_csv(
        self,
        brand_id: int,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        days: Optional[int] = None,
        branch_id: Optional[int] = None,
        category_id: Optional[int] = None,
    ) -> str:
        """Generates structured CSV with active filters, protected against formula injection."""
        data = self.get_brand_bi_dashboard(
            brand_id=brand_id,
            date_from=date_from,
            date_to=date_to,
            days=days,
            branch_id=branch_id,
            category_id=category_id,
            compare=False,
        )

        buf = io.StringIO()
        writer = csv.writer(buf)

        # Header metadata
        writer.writerow(["CONFIT_A — Business Intelligence & Commercial Report"])
        writer.writerow(["Brand", sanitize_csv_cell(data["brand"]["name"])])
        writer.writerow(["Period", sanitize_csv_cell(data["period"]["label"])])
        writer.writerow(["Generated At", sanitize_csv_cell(data["generated_at"])])
        writer.writerow([])

        # Section 1: Executive KPIs
        kpis = data["kpis"]
        writer.writerow(["EXECUTIVE SUMMARY & KEY PERFORMANCE INDICATORS"])
        writer.writerow(["Metric", "Value", "Currency / Unit"])
        writer.writerow(["Gross Sales", sanitize_csv_cell(f"{kpis['gross_sales']:.2f}"), kpis["currency"]])
        writer.writerow(["Net Sales (after discounts & opened returns)", sanitize_csv_cell(f"{kpis['net_sales']:.2f}"), kpis["currency"]])
        writer.writerow(["Total Orders", sanitize_csv_cell(kpis["orders_count"]), "Orders"])
        writer.writerow(["Total Units Sold", sanitize_csv_cell(kpis["units_sold"]), "Units"])
        writer.writerow(["Average Order Value (AOV)", sanitize_csv_cell(f"{kpis['average_order_value']:.2f}"), kpis["currency"]])
        writer.writerow(["Promotional Discounts Total", sanitize_csv_cell(f"{kpis['discount_total']:.2f}"), kpis["currency"]])
        writer.writerow(["Return Rate", sanitize_csv_cell(f"{kpis['return_rate']}%" if kpis['return_rate'] is not None else "N/A"), "Rate"])
        writer.writerow([])

        # Section 2: Products Performance Table
        writer.writerow(["PRODUCT SALES & PERFORMANCE"])
        writer.writerow(["Product ID", "Product Title", "Category", "Base Price", "Currency", "Units Sold", "Gross Sales", "Returned Units", "Return Rate", "Current Stock"])
        for p in data["products"]:
            writer.writerow([
                sanitize_csv_cell(p["product_id"]),
                sanitize_csv_cell(p["title"]),
                sanitize_csv_cell(p["category"]),
                sanitize_csv_cell(f"{p['base_price']:.2f}"),
                sanitize_csv_cell(p["currency"]),
                sanitize_csv_cell(p["units_sold"]),
                sanitize_csv_cell(f"{p['gross_sales']:.2f}"),
                sanitize_csv_cell(p["returned_units"]),
                sanitize_csv_cell(f"{p['return_rate']}%" if p['return_rate'] is not None else "N/A"),
                sanitize_csv_cell(p["stock_level"]),
            ])
        writer.writerow([])

        # Section 3: Branch Performance Table
        writer.writerow(["BRANCH & LOCATION PERFORMANCE"])
        writer.writerow(["Store ID", "Branch Name", "City", "Country", "BOPIS Orders", "Units Sold", "Gross Sales", "Available On-Hand Stock", "Low Stock SKUs Count"])
        for b in data["branches"]:
            writer.writerow([
                sanitize_csv_cell(b["store_id"]),
                sanitize_csv_cell(b["name"]),
                sanitize_csv_cell(b["city"]),
                sanitize_csv_cell(b["country"]),
                sanitize_csv_cell(b["orders_count"]),
                sanitize_csv_cell(b["units_sold"]),
                sanitize_csv_cell(f"{b['gross_sales']:.2f}"),
                sanitize_csv_cell(b["available_stock"]),
                sanitize_csv_cell(b["low_stock_skus"]),
            ])
        writer.writerow([])

        # Section 4: Category Share Table
        writer.writerow(["CATEGORY SALES SHARE"])
        writer.writerow(["Category ID", "Category Name", "Units Sold", "Gross Sales", "Revenue Share %"])
        for c in data["categories"]:
            writer.writerow([
                sanitize_csv_cell(c["category_id"]),
                sanitize_csv_cell(c["category_name"]),
                sanitize_csv_cell(c["units_sold"]),
                sanitize_csv_cell(f"{c['gross_sales']:.2f}"),
                sanitize_csv_cell(f"{c['share_pct']}%"),
            ])

        return buf.getvalue()

    # -------------------------------------------------------------------------
    # Professional PDF Generation (ReportLab with Logo #3 Branding)
    # -------------------------------------------------------------------------
    def render_brand_bi_pdf(
        self,
        brand_id: int,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        days: Optional[int] = None,
        branch_id: Optional[int] = None,
        category_id: Optional[int] = None,
    ) -> bytes:
        """Renders an authoritative, beautifully formatted executive BI report in PDF."""
        data = self.get_brand_bi_dashboard(
            brand_id=brand_id,
            date_from=date_from,
            date_to=date_to,
            days=days,
            branch_id=branch_id,
            category_id=category_id,
            compare=True,
        )

        from io import BytesIO
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer,
            Table, TableStyle, KeepTogether
        )

        # Official Logo #3 "Individual Grid" Palette
        CHARCOAL = colors.HexColor("#252729")
        CORAL = colors.HexColor("#EF826D")
        LILAC = colors.HexColor("#A99AD6")
        MINT = colors.HexColor("#89B799")
        GREY = colors.HexColor("#595C63")
        HAIRLINE = colors.HexColor("#E8E6E2")
        LIGHT = colors.HexColor("#F8F9FA")
        WHITE = colors.HexColor("#FFFFFF")

        PAGE = landscape(A4)
        MARGIN = 14 * mm

        meta = {
            "brand_name": data["brand"]["name"],
            "brand_id": data["brand"]["id"],
            "period": data["period"]["label"],
            "generated": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"),
        }

        def draw_logo(canvas, x: float, y: float, size: float = 16 * mm) -> None:
            canvas.saveState()
            s = size / 100.0
            canvas.translate(x, y)
            canvas.scale(s, s)
            canvas.setFillColor(CORAL)
            canvas.roundRect(0, 56, 44, 44, 12, stroke=0, fill=1)
            canvas.setFillColor(LILAC)
            canvas.roundRect(56, 56, 44, 44, 12, stroke=0, fill=1)
            canvas.setFillColor(MINT)
            canvas.roundRect(0, 0, 44, 44, 12, stroke=0, fill=1)
            canvas.setFillColor(CHARCOAL)
            canvas.circle(78, 22, 22, stroke=0, fill=1)
            canvas.restoreState()

        class _BiReportDoc(BaseDocTemplate):
            def __init__(self, buf):
                super().__init__(
                    buf,
                    pagesize=PAGE,
                    leftMargin=MARGIN,
                    rightMargin=MARGIN,
                    topMargin=MARGIN,
                    bottomMargin=16 * mm,
                    title=f"CONFIT Business Intelligence — {meta['brand_name']}",
                    author="CONFIT_A Intelligence",
                )
                first_top = 42 * mm
                self.addPageTemplates([
                    PageTemplate(
                        id="first",
                        frames=[Frame(MARGIN, self.bottomMargin, PAGE[0] - 2 * MARGIN, PAGE[1] - first_top - self.bottomMargin)],
                        onPage=self._first_page,
                        autoNextPageTemplate="rest",
                    ),
                    PageTemplate(
                        id="rest",
                        frames=[Frame(MARGIN, self.bottomMargin, PAGE[0] - 2 * MARGIN, PAGE[1] - 24 * mm - self.bottomMargin)],
                        onPage=self._later_page,
                    ),
                ])

            def _footer(self, canvas):
                canvas.saveState()
                canvas.setFont("Helvetica", 7.5)
                canvas.setFillColor(GREY)
                canvas.drawString(MARGIN, 9 * mm, f"CONFIT_A · Executive Analytics · {meta['brand_name']} · Generated: {meta['generated']}")
                canvas.drawRightString(PAGE[0] - MARGIN, 9 * mm, f"Page {canvas.getPageNumber()} of {meta.get('total_pages', '?')}")
                canvas.setStrokeColor(HAIRLINE)
                canvas.setLineWidth(0.5)
                canvas.line(MARGIN, 12 * mm, PAGE[0] - MARGIN, 12 * mm)
                canvas.restoreState()

            def _first_page(self, canvas, doc):
                canvas.saveState()
                top = PAGE[1] - MARGIN
                draw_logo(canvas, MARGIN, top - 16 * mm, 16 * mm)
                canvas.setFillColor(CHARCOAL)
                canvas.setFont("Helvetica-Bold", 15)
                canvas.drawString(MARGIN + 20 * mm, top - 6 * mm, "CONFIT_A")
                canvas.setFont("Helvetica", 7)
                canvas.setFillColor(GREY)
                canvas.drawString(MARGIN + 20 * mm, top - 10.5 * mm, "EXECUTIVE BUSINESS INTELLIGENCE")

                canvas.setFillColor(CHARCOAL)
                canvas.setFont("Helvetica-Bold", 16)
                canvas.drawRightString(PAGE[0] - MARGIN, top - 6 * mm, "Business Intelligence & Commercial Report")
                canvas.setFont("Helvetica", 9)
                canvas.setFillColor(GREY)
                canvas.drawRightString(PAGE[0] - MARGIN, top - 11 * mm, f"{meta['brand_name']} · Tenant ID: {meta['brand_id']}")
                canvas.drawRightString(PAGE[0] - MARGIN, top - 15.5 * mm, f"Reporting Period: {meta['period']}")

                canvas.setStrokeColor(HAIRLINE)
                canvas.setLineWidth(1.0)
                canvas.line(MARGIN, top - 20 * mm, PAGE[0] - MARGIN, top - 20 * mm)
                self._footer(canvas)
                canvas.restoreState()

            def _later_page(self, canvas, doc):
                canvas.saveState()
                top = PAGE[1] - MARGIN
                draw_logo(canvas, MARGIN, top - 8 * mm, 8 * mm)
                canvas.setFillColor(CHARCOAL)
                canvas.setFont("Helvetica-Bold", 9)
                canvas.drawString(MARGIN + 11 * mm, top - 5 * mm, f"CONFIT_A · {meta['brand_name']} · {meta['period']}")
                canvas.setStrokeColor(HAIRLINE)
                canvas.setLineWidth(0.5)
                canvas.line(MARGIN, top - 9 * mm, PAGE[0] - MARGIN, top - 9 * mm)
                self._footer(canvas)
                canvas.restoreState()

        ss = getSampleStyleSheet()
        body = ParagraphStyle("body", parent=ss["BodyText"], fontSize=8, leading=10, textColor=CHARCOAL)
        cell = ParagraphStyle("cell", parent=body, fontSize=7.5, leading=9)
        cell_r = ParagraphStyle("cellr", parent=cell, alignment=TA_RIGHT)
        head_s = ParagraphStyle("head", parent=cell, textColor=WHITE, fontName="Helvetica-Bold")
        head_r = ParagraphStyle("headr", parent=head_s, alignment=TA_RIGHT)
        h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=11, leading=13, textColor=CHARCOAL, spaceBefore=6, spaceAfter=4)
        note = ParagraphStyle("note", parent=body, fontSize=7, leading=9, textColor=GREY)

        story: List[Any] = []
        kpis = data["kpis"]
        cur = kpis["currency"]

        # 1. Executive Summary KPI Grid
        kpi_table_data = [[
            Paragraph("<b>Gross Sales</b><br/><br/><font size=12><b>%s %.2f</b></font>" % (cur, kpis["gross_sales"]), body),
            Paragraph("<b>Net Sales</b><br/><br/><font size=12><b>%s %.2f</b></font>" % (cur, kpis["net_sales"]), body),
            Paragraph("<b>Orders</b><br/><br/><font size=12><b>%d</b></font>" % kpis["orders_count"], body),
            Paragraph("<b>Units Sold</b><br/><br/><font size=12><b>%d</b></font>" % kpis["units_sold"], body),
            Paragraph("<b>Avg Order Value</b><br/><br/><font size=12><b>%s %.2f</b></font>" % (cur, kpis["average_order_value"]), body),
            Paragraph("<b>Return Rate</b><br/><br/><font size=12><b>%s</b></font>" % (f"{kpis['return_rate']}%" if kpis["return_rate"] is not None else "N/A"), body),
        ]]
        col_w = (PAGE[0] - 2 * MARGIN) / 6.0
        t_kpi = Table(kpi_table_data, colWidths=[col_w] * 6)
        t_kpi.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
            ("BOX", (0, 0), (-1, -1), 0.5, HAIRLINE),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, WHITE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story += [t_kpi, Spacer(1, 6)]

        # 2. Automated Business Insights Box
        if data.get("insights"):
            insight_lines = ["<b>Automated Executive Observations:</b>"]
            for ins in data["insights"][:3]:
                insight_lines.append(f"• <b>{ins['title']}:</b> {ins['message']}")
            p_insights = Paragraph("<br/>".join(insight_lines), body)
            t_ins = Table([[p_insights]], colWidths=[PAGE[0] - 2 * MARGIN])
            t_ins.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]))
            story += [t_ins, Spacer(1, 6)]

        # 3. Product Sales & Performance Table
        story.append(Paragraph("Product Sales & Stock Health", h2))
        products = data.get("products", [])
        if not products:
            story.append(Paragraph("No products recorded for this reporting scope.", note))
        else:
            p_head = ["Product Title", "Category", "Base Price", "Units Sold", f"Gross ({cur})", "Returns", "Return Rate", "Current Stock"]
            p_rows = [[Paragraph(h, head_s if i < 2 else head_r) for i, h in enumerate(p_head)]]
            for p in products[:15]:
                p_rows.append([
                    Paragraph(p["title"], cell),
                    Paragraph(p["category"], cell),
                    Paragraph(f"{p['base_price']:.2f}", cell_r),
                    Paragraph(str(p["units_sold"]), cell_r),
                    Paragraph(f"{p['gross_sales']:,.2f}", cell_r),
                    Paragraph(str(p["returned_units"]), cell_r),
                    Paragraph(f"{p['return_rate']}%" if p["return_rate"] is not None else "N/A", cell_r),
                    Paragraph(str(p["stock_level"]), cell_r),
                ])
            avail = PAGE[0] - 2 * MARGIN
            weights = [4.0, 1.8, 1.2, 1.0, 1.4, 0.9, 1.1, 1.1]
            p_widths = [avail * w / sum(weights) for w in weights]
            t_prod = Table(p_rows, colWidths=p_widths, repeatRows=1)
            t_prod.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), CHARCOAL),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("GRID", (0, 0), (-1, -1), 0.3, HAIRLINE),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            story += [t_prod, Spacer(1, 6)]

        # 4. Branch & Location Performance Table
        branches = data.get("branches", [])
        if branches:
            story.append(Paragraph("Branch & Location Performance", h2))
            b_head = ["Branch Location", "City", "BOPIS Orders", "Units Sold", f"Gross ({cur})", "Available Stock", "Low Stock SKUs"]
            b_rows = [[Paragraph(h, head_s if i < 2 else head_r) for i, h in enumerate(b_head)]]
            for b in branches:
                b_rows.append([
                    Paragraph(b["name"], cell),
                    Paragraph(b["city"], cell),
                    Paragraph(str(b["orders_count"]), cell_r),
                    Paragraph(str(b["units_sold"]), cell_r),
                    Paragraph(f"{b['gross_sales']:,.2f}", cell_r),
                    Paragraph(str(b["available_stock"]), cell_r),
                    Paragraph(str(b["low_stock_skus"]), cell_r),
                ])
            b_weights = [3.8, 1.8, 1.2, 1.2, 1.5, 1.4, 1.4]
            b_widths = [avail * w / sum(b_weights) for w in b_weights]
            t_branch = Table(b_rows, colWidths=b_widths, repeatRows=1)
            t_branch.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), CHARCOAL),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("GRID", (0, 0), (-1, -1), 0.3, HAIRLINE),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            story += [t_branch, Spacer(1, 6)]

        # 5. Methodology & Governance Footer
        story += [
            Paragraph("Data Integrity & Accounting Basis", h2),
            Paragraph(data["methodology"], note),
            Spacer(1, 3),
            Paragraph(
                "Generated by CONFIT_A Analytics Engine. All calculations strictly adhere to the unified revenue "
                "recognition policy. Protected against spreadsheet injection and unauthorized cross-tenant data leaks.",
                note,
            ),
        ]

        doc_buf = BytesIO()
        doc = _BiReportDoc(doc_buf)
        doc.build(story)
        meta["total_pages"] = doc.page
        return doc_buf.getvalue()
