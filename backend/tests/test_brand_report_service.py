"""Contract tests for brand product/sales reporting and its PDF rendering.

The report is invoice-adjacent: a brand reads these numbers as a statement of
what it sold. So the properties pinned here are the ones that would make the
document dishonest if they broke -- undefined rates presented as zero, cancelled
orders counted as revenue, another tenant's sales leaking in, or a large
catalog silently failing to render.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import Base
from backend.app.models.catalog import (Category, Product, ProductSKU,
                                        StoreInventory, StoreLocation)
from backend.app.models.commerce import Order, OrderItem
from backend.app.models.user import BrandProfile, User, UserRole
from backend.app.services.brand_report_service import BrandReportService


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine)
    db = S()
    yield db
    db.close()


def _tenant(db, name, email):
    u = User(email=email, hashed_password="x", full_name=name,
             role=UserRole.BRAND_MANAGER, preferred_language="en",
             is_active=True, is_verified=True)
    db.add(u); db.flush()
    bp = BrandProfile(user_id=u.id, brand_name=name, slug=name.lower().replace(" ", "-"))
    db.add(bp); db.flush()
    return bp


def _product(db, bp, cat, title, price="100.00"):
    p = Product(brand_id=bp.id, category_id=cat.id, title=title, title_ar=title,
                slug=f"{bp.id}-{title}".lower().replace(" ", "-"),
                description="d", description_ar="d", base_price=Decimal(price),
                currency="AED", color_family="Navy",
                thumbnail_url="https://example.com/a.jpg", is_active=True)
    db.add(p); db.flush()
    sku = ProductSKU(product_id=p.id, brand_id=bp.id, sku_code=f"S-{p.id}",
                     size="M", color="Navy", stock_level=10, is_in_stock=True)
    db.add(sku); db.flush()
    return p, sku


def _order(db, bp, product, sku, qty, price, status="processing", returned=False,
           created=None):
    amount = Decimal(price) * qty
    o = Order(user_id=1,
              order_number=f"O-{bp.id}-{product.id}-{qty}-{status}-{returned}-{id(product)}",
              status=status, total_amount=amount, subtotal_amount=amount,
              discount_amount=Decimal("0.00"), tax_amount=Decimal("0.00"),
              shipping_amount=Decimal("0.00"), currency="AED",
              payment_method="card", payment_status="paid", payment_installments=1,
              payment_mode="test", fulfillment_type="ship", shipping_method="standard",
              try_on_assisted=False, stylist_assisted=False,
              created_at=created or datetime.now(timezone.utc),
              updated_at=created or datetime.now(timezone.utc))
    db.add(o); db.flush()
    oi = OrderItem(order_id=o.id, product_sku_id=sku.id, product_id=product.id,
                   brand_id=bp.id, product_title=product.title, brand_name=bp.brand_name,
                   size="M", color="Navy", unit_price=Decimal(price), quantity=qty,
                   subtotal=Decimal(price) * qty, is_returned=returned)
    db.add(oi); db.flush()
    return o


@pytest.fixture()
def world(session):
    cat = Category(name="Outerwear", name_ar="خارجي", slug="outerwear")
    session.add(cat); session.flush()
    a = _tenant(session, "Tenant A", "a@example.com")
    b = _tenant(session, "Tenant B", "b@example.com")
    pa, sa = _product(session, a, cat, "A Coat", "200.00")
    pb, sb = _product(session, b, cat, "B Coat", "300.00")
    session.commit()
    return dict(cat=cat, a=a, b=b, pa=pa, sa=sa, pb=pb, sb=sb)


class TestRevenueCorrectness:
    def test_units_and_gross_come_from_order_lines(self, session, world):
        _order(session, world["a"], world["pa"], world["sa"], 3, "200.00")
        session.commit()
        rep = BrandReportService(session).build_product_sales_report(world["a"].id)
        assert rep["totals"]["units_sold"] == 3
        assert rep["totals"]["gross_sales"] == Decimal("600.00")

    def test_cancelled_and_refunded_orders_are_excluded(self, session, world):
        _order(session, world["a"], world["pa"], world["sa"], 2, "200.00")
        _order(session, world["a"], world["pa"], world["sa"], 5, "200.00",
               status="cancelled")
        _order(session, world["a"], world["pa"], world["sa"], 7, "200.00",
               status="refunded")
        session.commit()
        rep = BrandReportService(session).build_product_sales_report(world["a"].id)
        assert rep["totals"]["units_sold"] == 2, "non-revenue orders must not count"
        assert rep["totals"]["gross_sales"] == Decimal("400.00")

    def test_returns_reduce_net_but_not_gross(self, session, world):
        _order(session, world["a"], world["pa"], world["sa"], 4, "200.00")
        _order(session, world["a"], world["pa"], world["sa"], 1, "200.00",
               returned=True)
        session.commit()
        rep = BrandReportService(session).build_product_sales_report(world["a"].id)
        assert rep["totals"]["units_sold"] == 5
        assert rep["totals"]["gross_sales"] == Decimal("1000.00")
        assert rep["totals"]["net_sales"] == Decimal("800.00")
        assert rep["totals"]["returned_units"] == 1


class TestZeroDenominatorIsNeverAPercentage:
    def test_return_rate_is_none_when_nothing_sold(self, session, world):
        rep = BrandReportService(session).build_product_sales_report(world["a"].id)
        assert rep["totals"]["units_sold"] == 0
        assert rep["totals"]["return_rate"] is None, (
            "a rate with an empty denominator is undefined, not 0% and not 100%")
        assert rep["rows"][0]["return_rate"] is None

    def test_zero_returns_is_a_real_zero_not_none(self, session, world):
        """Distinguish 'nothing returned' from 'not measurable'."""
        _order(session, world["a"], world["pa"], world["sa"], 2, "200.00")
        session.commit()
        rep = BrandReportService(session).build_product_sales_report(world["a"].id)
        assert rep["totals"]["return_rate"] == 0.0


class TestTenantIsolation:
    def test_report_contains_only_the_requested_brand(self, session, world):
        _order(session, world["a"], world["pa"], world["sa"], 2, "200.00")
        _order(session, world["b"], world["pb"], world["sb"], 9, "300.00")
        session.commit()
        rep_a = BrandReportService(session).build_product_sales_report(world["a"].id)
        assert rep_a["totals"]["units_sold"] == 2, "B's 9 units must not appear"
        assert {r["title"] for r in rep_a["rows"]} == {"A Coat"}
        rep_b = BrandReportService(session).build_product_sales_report(world["b"].id)
        assert rep_b["totals"]["units_sold"] == 9

    def test_bopis_stock_from_another_tenants_store_is_not_counted(self, session, world):
        """The cross-tenant inventory leak must not reappear via the report."""
        store_b = StoreLocation(brand_id=world["b"].id, name="B Store", name_ar="B",
                                address="x", city="Dubai", country="UAE",
                                latitude=25.0, longitude=55.0, is_bopis_enabled=True)
        session.add(store_b); session.flush()
        # A row that points B's store at A's SKU: the exact leak shape.
        session.add(StoreInventory(store_id=store_b.id, sku_id=world["sa"].id,
                                   brand_id=world["a"].id, quantity=99,
                                   reserved_quantity=0))
        session.commit()
        rep_a = BrandReportService(session).build_product_sales_report(world["a"].id)
        assert rep_a["rows"][0]["bopis_quantity"] == 0, (
            "stock held in another tenant's store must never be reported as ours")


class TestFilters:
    def test_date_range_excludes_orders_outside_it(self, session, world):
        old = datetime.now(timezone.utc) - timedelta(days=90)
        _order(session, world["a"], world["pa"], world["sa"], 5, "200.00", created=old)
        _order(session, world["a"], world["pa"], world["sa"], 2, "200.00")
        session.commit()
        svc = BrandReportService(session)
        recent = svc.build_product_sales_report(
            world["a"].id, date_from=datetime.now(timezone.utc) - timedelta(days=7))
        assert recent["totals"]["units_sold"] == 2
        everything = svc.build_product_sales_report(world["a"].id)
        assert everything["totals"]["units_sold"] == 7

    def test_include_zero_sales_toggle(self, session, world):
        svc = BrandReportService(session)
        assert len(svc.build_product_sales_report(world["a"].id)["rows"]) == 1
        assert svc.build_product_sales_report(
            world["a"].id, include_zero_sales=False)["rows"] == []

    def test_unknown_brand_is_rejected(self, session):
        with pytest.raises(ValueError):
            BrandReportService(session).build_product_sales_report(999999)


class TestPdfRendering:
    def test_pdf_renders_with_real_data(self, session, world):
        from backend.app.services.brand_report_pdf import render_report_pdf
        _order(session, world["a"], world["pa"], world["sa"], 3, "200.00")
        session.commit()
        data = BrandReportService(session).build_product_sales_report(world["a"].id)
        pdf = render_report_pdf(data)
        assert pdf.startswith(b"%PDF-"), "must be a real PDF"
        assert len(pdf) > 1500

    def test_pdf_renders_for_an_empty_catalog(self, session, world):
        """No data must produce an honest page, not a crash."""
        from backend.app.services.brand_report_pdf import render_report_pdf
        data = BrandReportService(session).build_product_sales_report(
            world["a"].id, include_zero_sales=False)
        assert data["rows"] == []
        pdf = render_report_pdf(data)
        assert pdf.startswith(b"%PDF-")

    def test_pdf_paginates_a_large_catalog(self, session, world):
        """A big dataset must flow across pages instead of raising LayoutError."""
        from backend.app.services.brand_report_pdf import render_report_pdf
        data = BrandReportService(session).build_product_sales_report(world["a"].id)
        row = dict(data["rows"][0])
        data["rows"] = []
        for i in range(400):
            r = dict(row)
            r["product_id"] = 1000 + i
            r["title"] = ("A Very Long Product Title That Must Wrap Inside Its "
                          "Cell Without Breaking The Table " * 2)[:150] + f" #{i}"
            data["rows"].append(r)
        pdf = render_report_pdf(data)
        assert pdf.startswith(b"%PDF-")
        assert len(pdf) > 20000
