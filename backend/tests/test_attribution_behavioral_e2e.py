"""Behavioral (DB-backed) attribution tests — NOT simulations.

The existing test_visual_search_extended.py re-implements the attribution rule
inside the test itself, so it would still pass if production code were deleted.
These tests exercise the real BrandRepository / BrandAnalyticsEvent path against
the real test database, and are designed to FAIL under the mutations named in
section 30 of the audit brief.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from backend.app.core.money import to_decimal, money_sum
from backend.app.models.catalog_import import BrandAnalyticsEvent
from backend.app.repositories.brand_repository import BrandRepository
from backend.tests.conftest import TestingSessionLocal


@pytest.fixture
def db():
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _brand_and_products(db):
    from backend.app.models.catalog import Product
    prods = db.query(Product).limit(4).all()
    assert len(prods) >= 2, "seed data must contain products"
    return prods


class TestPurchaseEventLineageIsItemGrain:
    def test_revenue_amount_is_item_subtotal_not_order_total(self, db):
        """Multi-brand order: each event carries only its own item subtotal."""
        repo = BrandRepository(db)
        prods = _brand_and_products(db)
        a, b = prods[0], prods[1]
        tag = f"audit_{datetime.now(timezone.utc).timestamp()}"

        ea = repo.create_analytics_event(
            brand_id=a.brand_id, event_type="purchase", attribution_source="visual_search",
            product_id=a.id, order_id=None, revenue_amount=Decimal("300.00"),
            idempotency_key=f"{tag}_a")
        eb = repo.create_analytics_event(
            brand_id=b.brand_id, event_type="purchase", attribution_source="organic",
            product_id=b.id, order_id=None, revenue_amount=Decimal("700.00"),
            idempotency_key=f"{tag}_b")

        assert to_decimal(ea.revenue_amount) == Decimal("300.00")
        assert to_decimal(eb.revenue_amount) == Decimal("700.00")
        # Order-level revenue (1000) must never appear on a single brand's event
        assert to_decimal(ea.revenue_amount) != Decimal("1000.00")
        assert isinstance(ea.revenue_amount, Decimal), "revenue must persist as Decimal (NUMERIC)"

    def test_idempotency_key_prevents_duplicate_revenue(self, db):
        repo = BrandRepository(db)
        p = _brand_and_products(db)[0]
        key = f"dup_{datetime.now(timezone.utc).timestamp()}"
        e1 = repo.create_analytics_event(
            brand_id=p.brand_id, event_type="purchase", attribution_source="visual_search",
            product_id=p.id, revenue_amount=Decimal("123.45"), idempotency_key=key)
        e2 = repo.create_analytics_event(
            brand_id=p.brand_id, event_type="purchase", attribution_source="visual_search",
            product_id=p.id, revenue_amount=Decimal("123.45"), idempotency_key=key)
        assert e1.id == e2.id
        cnt = db.query(BrandAnalyticsEvent).filter(BrandAnalyticsEvent.event_id == key).count()
        assert cnt == 1


class TestVisualSearchProductIdentitySemantics:
    """Fails if product_id matching is removed from the attribution lookup."""

    def test_view_of_product_a_does_not_attribute_product_b(self, db):
        repo = BrandRepository(db)
        prods = _brand_and_products(db)
        a, b = prods[0], prods[1]
        uid = 999321
        repo.create_analytics_event(
            brand_id=a.brand_id, event_type="view", attribution_source="visual_search",
            product_id=a.id, user_id=uid,
            idempotency_key=f"view_a_{uid}_{datetime.now(timezone.utc).timestamp()}")

        assert repo.get_recent_visual_search_for_user(uid, 30, product_id=a.id) is True
        assert repo.get_recent_visual_search_for_user(uid, 30, product_id=b.id) is False

    def test_other_user_search_does_not_attribute(self, db):
        repo = BrandRepository(db)
        a = _brand_and_products(db)[0]
        ux, uy = 999401, 999402
        repo.create_analytics_event(
            brand_id=a.brand_id, event_type="view", attribution_source="visual_search",
            product_id=a.id, user_id=ux,
            idempotency_key=f"view_ux_{datetime.now(timezone.utc).timestamp()}")
        assert repo.get_recent_visual_search_for_user(ux, 30, product_id=a.id) is True
        assert repo.get_recent_visual_search_for_user(uy, 30, product_id=a.id) is False

    def test_expired_window_not_attributed(self, db):
        repo = BrandRepository(db)
        a = _brand_and_products(db)[0]
        uid = 999501
        ev = repo.create_analytics_event(
            brand_id=a.brand_id, event_type="view", attribution_source="visual_search",
            product_id=a.id, user_id=uid,
            idempotency_key=f"view_old_{datetime.now(timezone.utc).timestamp()}")
        ev.created_at = datetime.now(timezone.utc) - timedelta(days=31)
        db.commit()
        assert repo.get_recent_visual_search_for_user(uid, 30, product_id=a.id) is False

    def test_organic_source_view_does_not_grant_visual_attribution(self, db):
        repo = BrandRepository(db)
        a = _brand_and_products(db)[0]
        uid = 999601
        repo.create_analytics_event(
            brand_id=a.brand_id, event_type="view", attribution_source="organic",
            product_id=a.id, user_id=uid,
            idempotency_key=f"view_org_{datetime.now(timezone.utc).timestamp()}")
        assert repo.get_recent_visual_search_for_user(uid, 30, product_id=a.id) is False

    def test_attribution_lookup_still_filters_product_id_in_source(self):
        """Guard: section 30 mutation — deleting product_id filter must fail here."""
        import inspect
        from backend.app.services import commerce_service
        src = inspect.getsource(commerce_service)
        assert "BrandAnalyticsEvent.product_id == product_id" in src


class TestRevenueConservationItemGrain:
    def test_attributed_plus_organic_equals_eligible_item_subtotal(self, db):
        """Real query path: channel split must reconcile to item-grain subtotal."""
        repo = BrandRepository(db)
        result = repo.get_revenue_attribution()
        rb = result["revenue_attribution"]
        parts = money_sum([rb["ai_virtual_stylist"], rb["outfit_builder"],
                           rb["visual_search"], rb["organic_discovery"]])

        from backend.app.models.commerce import Order, OrderItem
        eligible = db.query(OrderItem).join(Order).filter(
            Order.status.notin_(["cancelled", "refunded"])).all()
        eligible_subtotal = money_sum([i.subtotal for i in eligible])
        assert to_decimal(result["attribution_base_item_subtotal"]) == eligible_subtotal

        assert parts == eligible_subtotal, (
            f"channel split {parts} != eligible item subtotal {eligible_subtotal}")

    def test_order_level_and_item_level_reported_separately(self, db):
        repo = BrandRepository(db)
        result = repo.get_revenue_attribution()
        from backend.app.models.commerce import Order, OrderItem
        gmv = money_sum([o.total_amount for o in db.query(Order).filter(
            Order.status.notin_(["cancelled", "refunded"])).all()])
        # total_gmv is order-grain (includes tax/shipping) and must NOT be the
        # base for the item-grain channel split.
        assert to_decimal(result["total_gmv"]) == gmv
        assert "ITEM-LEVEL" in result["attribution_methodology"]
        assert "Revenue from authoritative Order.total_amount" not in result["attribution_methodology"]
