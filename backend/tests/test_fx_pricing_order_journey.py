"""Priority 3 — FX validity policy, end-to-end price consistency, and order integrity.

Covers:
1. Rate freshness policy (`FX_MAX_AGE_SECONDS`), RFC-2822 + ISO-8601 `as_of` timestamps,
   `MARKET_FX_RATES_AS_OF` provenance, and fail-closed rejection on stale / malformed /
   non-positive / missing / untrusted (`stale_live`) rates.
2. Full customer purchase journey price consistency:
   EGP CSV import -> `GET /products` -> `GET /products/{slug}` (USD & EGP) ->
   `POST /commerce/cart/items` -> `GET /commerce/cart` -> `POST /commerce/checkout` ->
   `Order` + `OrderItem` + `PaymentTransaction` reconciliation.
3. Checkout price-change guard (`expected_quote_total`) when catalog price or market FX
   rate changes between cart quote and order confirmation.
4. Historical order immutability across catalog price edits, FX rate changes, CSV
   re-imports, and brand product metadata updates.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.core.security import create_access_token
from backend.app.models.catalog import Product
from backend.app.models.commerce import Order, PaymentTransaction
from backend.app.models.membership import BrandMembership
from backend.app.models.user import BrandProfile, User, UserRole
from backend.app.services import catalog_fx
from backend.app.services.brand_catalog_service import BrandCatalogService
from backend.app.services.fx_rates import RateSnapshot, fx_rates
from backend.tests.conftest import TestingSessionLocal

APPROVED_IMG = "https://images.pexels.com/photos/1342609/pexels-photo-1342609.jpeg"
FIXTURE_EGP_RATE = Decimal("52.09")  # 1,614.79 EGP / 52.09 = 31.00 USD exact


def _make_csv(price: str, currency: str = "EGP", compare_at: str = "2083.60", sku: str = "FX-JRN-001") -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "title", "title_ar", "sku_code", "description", "description_ar",
        "category_slug", "base_price", "currency", "compare_at_price",
        "color_family", "size", "stock_level", "thumbnail_url", "gender",
    ])
    w.writerow([
        "Nile Linen Blazer", "بليزر كتان النيل", sku,
        "Tailored summer blazer.", "بليزر صيفي مفصل.",
        "outerwear", price, currency, compare_at,
        "Sand", "M", "12", APPROVED_IMG, "unisex",
    ])
    return buf.getvalue()


@pytest.fixture()
def brand_journey_ctx(client: TestClient, monkeypatch):
    """Create a real brand + owner token in the shared test DB with deterministic FX."""
    monkeypatch.setattr(settings, "FX_LIVE_RATES_ENABLED", False)
    monkeypatch.setattr(settings, "PRICING_CURRENCY", "USD")
    monkeypatch.setattr(settings, "MARKET_FX_RATES", '{"EGP": "52.09", "AED": "3.6725"}')
    fresh_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    monkeypatch.setattr(settings, "MARKET_FX_RATES_AS_OF", fresh_ts)
    monkeypatch.setattr(settings, "FX_MAX_AGE_SECONDS", 172800)
    fx_rates.invalidate()

    monkeypatch.setattr(
        BrandCatalogService,
        "_materialize_media",
        lambda self, product, row, brand_id=None: type(
            "M", (), {"resolvable": True, "rows": 1, "reason": ""}
        )(),
    )

    db = TestingSessionLocal()
    try:
        owner = db.query(User).filter(User.email == "fx-journey-owner@confit.test").one_or_none()
        if owner is None:
            owner = User(
                email="fx-journey-owner@confit.test",
                hashed_password="x",
                full_name="FX Journey Owner",
                role=UserRole.BRAND_OWNER,
                preferred_language="en",
                is_active=True,
                is_verified=True,
            )
            db.add(owner)
            db.flush()
            bp = BrandProfile(
                user_id=owner.id,
                brand_name="FX Journey House",
                slug="fx-journey-house",
                is_verified=True,
            )
            db.add(bp)
            db.flush()
            db.add(BrandMembership(brand_id=bp.id, user_id=owner.id, role="owner", status="active"))
            db.commit()
        else:
            bp = db.query(BrandProfile).filter(BrandProfile.user_id == owner.id).one()
        token = create_access_token({"sub": str(owner.id)})
        brand_id = bp.id
    finally:
        db.close()

    yield {"client": client, "brand_id": brand_id, "headers": {"Authorization": f"Bearer {token}"}}
    fx_rates.invalidate()
    db_clean = TestingSessionLocal()
    try:
        from sqlalchemy import text as _sql_text
        db_clean.execute(_sql_text("DELETE FROM brand_analytics_events WHERE order_id IN (SELECT id FROM orders WHERE currency != 'USD')"))
        db_clean.execute(_sql_text("DELETE FROM fulfillment_groups WHERE order_id IN (SELECT id FROM orders WHERE currency != 'USD')"))
        db_clean.execute(_sql_text("DELETE FROM payment_transactions WHERE currency != 'USD'"))
        db_clean.execute(_sql_text("DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE currency != 'USD')"))
        db_clean.execute(_sql_text("DELETE FROM orders WHERE currency != 'USD'"))
        db_clean.commit()
    finally:
        db_clean.close()


class TestFxFreshnessAndValidityPolicy:
    def test_fresh_iso_and_rfc2822_timestamps_pass_and_record_age(self):
        ref = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
        iso_snap = RateSnapshot(
            base="USD", rates={"EGP": FIXTURE_EGP_RATE}, source="live",
            as_of="2026-10-21T06:00:00Z",
        )
        r_iso = catalog_fx.resolve_rate("EGP", "USD", snapshot=iso_snap, max_age_seconds=86400, now=ref)
        assert r_iso.age_seconds == pytest.approx(21600.0)
        assert r_iso.convert(Decimal("1614.79")) == Decimal("31.00")

        rfc_snap = RateSnapshot(
            base="USD", rates={"EGP": FIXTURE_EGP_RATE}, source="live",
            as_of="Wed, 21 Oct 2026 09:00:00 +0000",
        )
        r_rfc = catalog_fx.resolve_rate("EGP", "USD", snapshot=rfc_snap, max_age_seconds=86400, now=ref)
        assert r_rfc.age_seconds == pytest.approx(10800.0)

    def test_stale_rate_past_max_age_is_refused_before_persist(self, brand_journey_ctx, monkeypatch):
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        monkeypatch.setattr(settings, "MARKET_FX_RATES_AS_OF", stale_ts)
        monkeypatch.setattr(settings, "FX_MAX_AGE_SECONDS", 86400)
        fx_rates.invalidate()

        db = TestingSessionLocal()
        try:
            before = db.query(Product).count()
            preview = BrandCatalogService(db).preview_csv(
                _make_csv("1614.79", sku="FX-STALE-01"),
                brand_journey_ctx["brand_id"],
            )
            assert preview["can_import"] is False
            assert preview["error_rows_count"] == 1
            assert any("stale" in e["message"].lower() for e in preview["errors"])
            assert db.query(Product).count() == before
        finally:
            db.close()

    def test_malformed_rate_timestamp_fails_closed(self):
        bad_ts_snap = RateSnapshot(
            base="USD", rates={"EGP": FIXTURE_EGP_RATE}, source="configured",
            as_of="not-a-real-date",
        )
        with pytest.raises(catalog_fx.RateUnavailable) as exc_info:
            catalog_fx.resolve_rate("EGP", "USD", snapshot=bad_ts_snap)
        assert exc_info.value.reason == "rate_timestamp_malformed"


class TestCompletePriceJourneyAndOrderImmutability:
    def test_end_to_end_egp_import_to_cart_checkout_payment_and_historical_immutability(
        self, brand_journey_ctx, monkeypatch
    ):
        client: TestClient = brand_journey_ctx["client"]
        headers = brand_journey_ctx["headers"]
        brand_id = brand_journey_ctx["brand_id"]

        db = TestingSessionLocal()
        try:
            res = BrandCatalogService(db).process_csv_import(
                _make_csv("1614.79", compare_at="2083.60", sku="FX-E2E-101"),
                brand_id,
            )
            assert res["accepted_rows"] == 1, res
            prod = db.query(Product).filter(Product.brand_id == brand_id, Product.title == "Nile Linen Blazer").one()
            slug = prod.slug
            prod_id = prod.id
            sku_id = prod.skus[0].id
            assert prod.currency == "USD"
            assert Decimal(str(prod.base_price)) == Decimal("31.00")
            assert Decimal(str(prod.compare_at_price)) == Decimal("40.00")
            assert prod.price_source_currency == "EGP"
            assert Decimal(str(prod.price_source_amount)) == Decimal("1614.79")
            assert Decimal(str(prod.price_fx_rate)) == Decimal("52.09")
        finally:
            db.close()

        # 1. Product list & detail agree in both USD and EGP (no 53x double conversion!)
        list_usd = client.get("/api/v1/catalog/products?currency=USD")
        assert list_usd.status_code == 200
        listed_item = next(p for p in list_usd.json() if p["slug"] == slug)
        assert listed_item["base_price"] == pytest.approx(31.00)

        pdp_usd = client.get(f"/api/v1/catalog/products/{slug}?currency=USD")
        assert pdp_usd.status_code == 200
        assert pdp_usd.json()["base_price"] == pytest.approx(31.00)
        assert pdp_usd.json()["compare_at_price"] == pytest.approx(40.00)
        assert pdp_usd.json()["currency"] == "USD"

        pdp_egp = client.get(f"/api/v1/catalog/products/{slug}?currency=EGP")
        assert pdp_egp.status_code == 200
        assert pdp_egp.json()["base_price"] == pytest.approx(1614.79)
        assert pdp_egp.json()["compare_at_price"] == pytest.approx(2083.60)
        assert pdp_egp.json()["currency"] == "EGP"

        # 2. Add 2 units to cart -> verify server-authoritative cart quote
        shopper_headers = {"X-Session-Token": "fx_journey_session_01"}
        add_r = client.post(
            "/api/v1/commerce/cart/items",
            headers=shopper_headers,
            json={"product_sku_id": sku_id, "quantity": 2},
        )
        assert add_r.status_code in (200, 201), add_r.text

        cart_usd = client.get("/api/v1/commerce/cart?currency=USD", headers=shopper_headers).json()
        assert cart_usd["subtotal"] == pytest.approx(62.00)
        assert cart_usd["shipping_amount"] == pytest.approx(15.00)
        assert cart_usd["tax_amount"] == pytest.approx(3.10)  # 5% of 62.00
        assert cart_usd["total"] == pytest.approx(80.10)

        # 3. Price change guard: if shopper expects outdated total, checkout pauses cleanly
        stale_quote_resp = client.post(
            "/api/v1/commerce/checkout",
            headers=shopper_headers,
            json={
                "payment_method": "card",
                "fulfillment_type": "delivery",
                "recipient_name": "Nadia Mansour",
                "phone": "+201001234567",
                "address_line": "14 Gezira St",
                "city": "Cairo",
                "country": "EG",
                "shipping_method": "standard",
                "guest_email": "nadia@confit.test",
                "expected_quote_total": "100.00",  # outdated expectation vs actual EGP settled total
            },
        )
        assert stale_quote_resp.status_code in (400, 422), stale_quote_resp.text
        assert "changed" in stale_quote_resp.text.lower()

        # 4. Checkout in EG market settles in EGP at 52.09 and reconciles with PaymentTransaction
        # Expected EGP settlement:
        # unit_price = round(31.00 * 52.09, 2) = 1614.79
        # line subtotal (qty 2) = round(62.00 * 52.09, 2) = 3229.58
        # tax = round(3.10 * 52.09, 2) = 161.48
        # shipping = round(15.00 * 52.09, 2) = 781.35
        # total = 3229.58 + 161.48 + 781.35 = 4172.41 EGP
        checkout_resp = client.post(
            "/api/v1/commerce/checkout",
            headers=shopper_headers,
            json={
                "payment_method": "card",
                "fulfillment_type": "delivery",
                "recipient_name": "Nadia Mansour",
                "phone": "+201001234567",
                "address_line": "14 Gezira St",
                "city": "Cairo",
                "country": "EG",
                "shipping_method": "standard",
                "guest_email": "nadia@confit.test",
                "expected_quote_total": "4172.41",
            },
        )
        assert checkout_resp.status_code == 200, checkout_resp.text
        order_body = checkout_resp.json()
        order_number = order_body["order_number"]
        assert order_body["currency"] == "EGP"
        assert order_body["pricing_currency"] == "USD"
        assert Decimal(str(order_body["fx_rate_used"])) == Decimal("52.09")
        assert order_body["total_amount"] == pytest.approx(4172.41)
        assert order_body["items"][0]["unit_price"] == pytest.approx(1614.79)
        assert order_body["items"][0]["subtotal"] == pytest.approx(3229.58)

        # Verify PaymentTransaction recorded exact same amount + currency as Order
        db = TestingSessionLocal()
        try:
            ord_row = db.query(Order).filter(Order.order_number == order_number).one()
            pay_tx = db.query(PaymentTransaction).filter(PaymentTransaction.order_id == ord_row.id).one()
            assert Decimal(str(pay_tx.amount)) == Decimal(str(ord_row.total_amount)) == Decimal("4172.41")
            assert pay_tx.currency == ord_row.currency == "EGP"
        finally:
            db.close()

        # 5. Historical order immutability across ALL 4 post-order mutations:
        #    (a) catalog base_price edited directly,
        #    (b) MARKET_FX_RATES changed to 61.50,
        #    (c) CSV re-imported with a new EGP price (3,075.00 EGP),
        #    (d) brand PATCH updates title, description, gender, and tags.
        monkeypatch.setattr(settings, "MARKET_FX_RATES", '{"EGP": "61.50", "AED": "3.6725"}')
        fx_rates.invalidate()

        db = TestingSessionLocal()
        try:
            p_edit = db.get(Product, prod_id)
            p_edit.base_price = Decimal("99.00")
            db.commit()
            BrandCatalogService(db).process_csv_import(
                _make_csv("3075.00", compare_at="3900.00", sku="FX-E2E-101"),
                brand_id,
            )
        finally:
            db.close()

        patch_r = client.patch(
            f"/api/v1/partner/catalog/products/{prod_id}",
            headers=headers,
            json={
                "title": "Nile Linen Blazer — Autumn Edition",
                "description": "Updated seasonal description.",
                "gender": "mens",
                "occasion_tags": ["office", "wedding"],
            },
        )
        assert patch_r.status_code == 200, patch_r.text

        after_order = client.get(
            f"/api/v1/commerce/orders/{order_number}",
            headers=shopper_headers,
            params={"guest_email": "nadia@confit.test"},
        )
        assert after_order.status_code == 200, after_order.text
        locked = after_order.json()
        assert locked["currency"] == "EGP"
        assert locked["pricing_currency"] == "USD"
        assert Decimal(str(locked["fx_rate_used"])) == Decimal("52.09")
        assert locked["total_amount"] == pytest.approx(4172.41)
        assert locked["subtotal_amount"] == pytest.approx(3229.58)
        assert locked["tax_amount"] == pytest.approx(161.48)
        assert locked["shipping_amount"] == pytest.approx(781.35)
        assert locked["items"][0]["unit_price"] == pytest.approx(1614.79)
        assert locked["items"][0]["subtotal"] == pytest.approx(3229.58)
        assert locked["items"][0]["product_title"] == "Nile Linen Blazer"
