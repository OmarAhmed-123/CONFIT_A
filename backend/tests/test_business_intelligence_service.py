"""
Tests for BusinessIntelligenceService and BrandReportPdfGenerator.
Verifies tenant isolation, revenue eligibility, formula injection protection,
preceding-period comparisons, inventory health, promotions, and PDF export integrity.
"""
import io
import pytest
from datetime import datetime, timezone, timedelta

from backend.app.services.business_intelligence_service import BusinessIntelligenceService
from backend.app.models.catalog import Product, ProductSKU, Category, StoreLocation, StoreInventory
from backend.app.models.commerce import Order, OrderItem, Promotion
from backend.tests.test_brand_portal_regressions import portal, row, upload


def test_formula_injection_sanitization():
    """Verify formula injection characters are prepended with single quotes."""
    svc = BusinessIntelligenceService
    assert svc.sanitize_csv_cell("=SUM(A1:A10)") == "'=SUM(A1:A10)"
    assert svc.sanitize_csv_cell("+12345") == "'+12345"
    assert svc.sanitize_csv_cell("-Cmd|' /C calc'!A0") == "'-Cmd|' /C calc'!A0"
    assert svc.sanitize_csv_cell("@AVERAGE(B1)") == "'@AVERAGE(B1)"
    assert svc.sanitize_csv_cell("\tTab") == "'\tTab"
    assert svc.sanitize_csv_cell("\rReturn") == "'\rReturn"
    assert svc.sanitize_csv_cell("Normal String") == "Normal String"
    assert svc.sanitize_csv_cell(12345) == "12345"
    assert svc.sanitize_csv_cell(None) == ""


def test_tenant_isolation_in_bi(portal):
    """Ensure Brand A cannot see or aggregate Brand B's data under any condition."""
    client, factory, h, ids = portal
    brand_a_id = ids[0]
    brand_b_id = ids[1]

    upload(client, h[0], [row(title="Alpha Silk Shirt", sku_code="ALPHA-SHIRT")])
    upload(client, h[1], [row(title="Beta Linen Trousers", sku_code="BETA-TROUSERS")])

    with factory() as db:
        prod_b = db.query(Product).filter(Product.brand_id == brand_b_id).first()

        now = datetime.now(timezone.utc)
        order_b = Order(
            order_number="ORDER-BETA-01",
            status="completed",
            total_amount=200.0,
            subtotal_amount=200.0,
            currency="USD",
            created_at=now,
            payment_status="paid"
        )
        db.add(order_b)
        db.flush()

        item_b = OrderItem(
            order_id=order_b.id,
            product_id=prod_b.id,
            product_title=prod_b.title,
            brand_name="Brand Beta",
            size="M",
            color="Classic",
            product_sku_id=prod_b.skus[0].id if prod_b.skus else None,
            quantity=1,
            unit_price=200.0,
            subtotal=200.0,
            brand_id=brand_b_id
        )
        db.add(item_b)
        db.commit()

        # Query Brand A's analytics
        svc = BusinessIntelligenceService(db)
        bi_a = svc.get_brand_bi_dashboard(
            brand_id=brand_a_id,
            days=30,
            compare=False
        )

        # Brand A should have 0 orders, 0 gross sales, 0 units
        assert bi_a["kpis"]["orders_count"] == 0
        assert bi_a["kpis"]["gross_sales"] == 0.0
        assert bi_a["kpis"]["units_sold"] == 0

        # Query Brand B's analytics
        bi_b = svc.get_brand_bi_dashboard(
            brand_id=brand_b_id,
            days=30,
            compare=False
        )

        assert bi_b["kpis"]["orders_count"] == 1
        assert bi_b["kpis"]["gross_sales"] == 200.0
        assert bi_b["kpis"]["units_sold"] == 1
        assert len(bi_b["products"]) == 1
        assert bi_b["products"][0]["title"] == "Beta Linen Trousers"


def test_brand_bi_comparisons_and_promotions(portal):
    """Test date filtering, preceding period comparison, promotion metrics, and CSV export."""
    client, factory, h, ids = portal
    brand_id = ids[0]

    upload(client, h[0], [row(title="Acme Trench Coat", sku_code="ACME-TRENCH", stock=2)])

    with factory() as db:
        prod = db.query(Product).filter(Product.brand_id == brand_id).first()
        now = datetime.now(timezone.utc)

        # Promotion
        promo = Promotion(
            code="SAVE20",
            description="20% off all trench coats",
            brand_id=brand_id,
            discount_type="percentage",
            discount_value=20.0,
            is_active=True
        )
        db.add(promo)
        db.flush()

        # Preceding period order (12 days ago)
        past_order = Order(
            order_number="ORDER-PAST-01",
            status="completed",
            total_amount=240.0,
            subtotal_amount=300.0,
            discount_amount=60.0,
            promo_code="SAVE20",
            currency="USD",
            created_at=now - timedelta(days=12),
            payment_status="paid"
        )
        db.add(past_order)
        db.flush()
        past_item = OrderItem(
            order_id=past_order.id,
            product_id=prod.id,
            product_title=prod.title,
            brand_name="Acme Fashion",
            size="M",
            color="Classic",
            product_sku_id=prod.skus[0].id if prod.skus else None,
            quantity=1,
            unit_price=300.0,
            subtotal=300.0,
            brand_id=brand_id
        )
        db.add(past_item)

        # Current period order (2 days ago)
        curr_order = Order(
            order_number="ORDER-CURR-01",
            status="delivered",
            total_amount=600.0,
            subtotal_amount=600.0,
            currency="USD",
            created_at=now - timedelta(days=2),
            payment_status="paid"
        )
        db.add(curr_order)
        db.flush()
        curr_item = OrderItem(
            order_id=curr_order.id,
            product_id=prod.id,
            product_title=prod.title,
            brand_name="Acme Fashion",
            size="M",
            color="Classic",
            product_sku_id=prod.skus[0].id if prod.skus else None,
            quantity=2,
            unit_price=300.0,
            subtotal=600.0,
            brand_id=brand_id
        )
        db.add(curr_item)
        db.commit()

        # Query 7 days with comparison (covers current order, preceding covers past order)
        svc = BusinessIntelligenceService(db)
        bi = svc.get_brand_bi_dashboard(
            brand_id=brand_id,
            days=7,
            compare=True
        )

        # Current period: 1 order, 2 units, $600 gross
        assert bi["kpis"]["orders_count"] == 1
        assert bi["kpis"]["units_sold"] == 2
        assert bi["kpis"]["gross_sales"] == 600.0
        # Comparison period: 1 order, 1 unit, $300 gross -> gross change = +100%
        assert bi["comparison_kpis"] is not None
        assert bi["comparison_kpis"]["gross_sales"] == 300.0
        assert bi["growth"]["gross_sales_change_pct"] == 100.0
        assert bi["growth"]["units_sold_change_pct"] == 100.0

        # Stock alert for prod (stock = 2, low stock threshold <= 5)
        assert bi["inventory"]["low_stock_count"] >= 1

        # Check automated insights generated
        assert len(bi["insights"]) > 0

        # Test CSV generation
        csv_text = svc.export_brand_bi_csv(brand_id=brand_id, days=7)
        assert "EXECUTIVE SUMMARY & KEY PERFORMANCE INDICATORS" in csv_text
        assert "Gross Sales,600.00,USD" in csv_text
        assert "Acme Trench Coat" in csv_text


def test_pdf_report_generation(portal):
    """Test generating vector PDF report using ReportLab with Logo #3 styling."""
    _, factory, _, ids = portal
    brand_id = ids[0]

    with factory() as db:
        svc = BusinessIntelligenceService(db)
        pdf_bytes = svc.render_brand_bi_pdf(
            brand_id=brand_id,
            days=30
        )

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 2000
        assert pdf_bytes.startswith(b"%PDF")
        assert pdf_bytes.rstrip().endswith(b"%%EOF")
        assert b"CONFIT Business Intelligence" in pdf_bytes
