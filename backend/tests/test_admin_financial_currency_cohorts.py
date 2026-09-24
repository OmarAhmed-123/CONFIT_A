"""Re-audit gates: currency, time-window and return-cohort correctness.

Findings measured 2026-09-24:
* Admin GMV added different currencies and the UI printed one '$' total.
* windowed GMV was paired with an all-time item-attribution ledger.
* return denominators counted eligible Orders, while numerators counted every
  ReturnRequest (different population and different cohort flag); duplicate
  requests could exceed 100% and rejected/excluded returns were included.

The tests use real repository queries against an isolated database. No helper
re-implements the production calculations.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base
from backend.app.core.timeutils import TimeRange
from backend.app.models.commerce import Order, OrderItem, ReturnRequest
from backend.app.repositories.brand_repository import BrandRepository


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/currency_cohorts.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _order(db, amount: str, currency: str, *, tryon=False, status="delivered",
           created_at: datetime | None = None) -> Order:
    order = Order(
        order_number=f"SEM-{uuid.uuid4().hex[:10].upper()}",
        user_id=None,
        total_amount=Decimal(amount), subtotal_amount=Decimal(amount),
        discount_amount=0, tax_amount=0, shipping_amount=0,
        currency=currency, payment_method="cod", payment_status="pending",
        fulfillment_type="delivery", status=status,
        try_on_assisted=tryon,
        created_at=created_at or datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(order)
    db.flush()
    return order


def _item(db, order: Order, amount: str) -> OrderItem:
    # Isolated SQLite deliberately does not enforce FKs. Product/brand ids are
    # irrelevant to this test; the real NOT NULL/order relationship remains.
    item = OrderItem(
        order_id=order.id, product_id=999001, brand_id=999001,
        product_title="Semantic item", brand_name="Semantic brand",
        size="M", color="black", unit_price=Decimal(amount), quantity=1,
        subtotal=Decimal(amount), is_returned=False,
    )
    db.add(item)
    db.flush()
    return item


def _return(db, order: Order, *, status="requested", tryon_flag=False) -> ReturnRequest:
    req = ReturnRequest(
        return_number=f"RET-{uuid.uuid4().hex[:10].upper()}",
        order_id=order.id, user_id=None, reason="fit",
        refund_amount=order.total_amount, status=status,
        try_on_used_for_item=tryon_flag,
    )
    db.add(req)
    db.flush()
    return req


class TestCurrencySemantics:
    def test_mixed_currency_never_publishes_a_fake_combined_total(self, db):
        _order(db, "100.00", "USD")
        _order(db, "5000.00", "EGP")
        db.commit()

        overview = BrandRepository(db).get_platform_admin_analytics()
        assert overview["currency_status"] == "mixed_currencies"
        assert overview["currency"] is None
        assert overview["total_gmv"] is None, "USD + EGP must never become one number"
        assert overview["gmv_by_currency"] == {"EGP": 5000.0, "USD": 100.0}
        assert all(value is None for value in overview["revenue_attribution"].values())

        attribution = BrandRepository(db).get_revenue_attribution()
        assert attribution["currency_status"] == "mixed_currencies"
        assert attribution["total_gmv"] is None
        assert attribution["gmv_by_currency"] == {"EGP": 5000.0, "USD": 100.0}

    def test_single_currency_keeps_backward_compatible_flat_amount(self, db):
        _order(db, "100.25", "EGP")
        _order(db, "49.75", "EGP")
        db.commit()
        overview = BrandRepository(db).get_platform_admin_analytics()
        assert overview["currency_status"] == "single_currency"
        assert overview["currency"] == "EGP"
        assert overview["total_gmv"] == 150.0
        assert overview["gmv_by_currency"] == {"EGP": 150.0}

    def test_attribution_uses_the_same_order_window_as_gmv(self, db):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        old = _order(db, "100.00", "USD", created_at=now - timedelta(days=90))
        _item(db, old, "100.00")  # no event -> organic, still real attribution
        recent = _order(db, "200.00", "USD", created_at=now - timedelta(days=2))
        _item(db, recent, "200.00")
        db.commit()

        data = BrandRepository(db).get_platform_admin_analytics(time_range=TimeRange.resolve(days=30))
        assert data["total_gmv"] == 200.0
        assert data["attribution_by_currency"]["USD"]["organic_discovery"] == 200.0
        assert data["revenue_attribution"]["organic_discovery"] == 200.0


class TestReturnCohortBoundaries:
    def test_duplicate_returns_count_one_order_and_use_order_cohort_flag(self, db):
        tryon = _order(db, "100", "USD", tryon=True)
        # Deliberately opposite request flag: cohort membership MUST come from
        # the same Order.try_on_assisted field used by the denominator.
        _return(db, tryon, tryon_flag=False)
        _return(db, tryon, tryon_flag=False)
        non = _order(db, "100", "USD", tryon=False)
        db.commit()

        data = BrandRepository(db).get_return_reduction_metrics()
        assert data["tryon_orders"] == 1
        assert data["tryon_returns"] == 1, "two requests for one order count once"
        assert data["return_rate_tryon_users"] == 100.0
        assert data["non_tryon_orders"] == 1
        assert data["non_tryon_returns"] == 0
        assert data["return_rate_non_tryon_users"] == 0.0

    def test_rejected_and_ineligible_order_returns_are_excluded(self, db):
        eligible = _order(db, "100", "USD", tryon=False)
        _return(db, eligible, status="rejected")
        cancelled = _order(db, "100", "USD", tryon=False, status="cancelled")
        _return(db, cancelled, status="requested")
        db.commit()

        data = BrandRepository(db).get_return_reduction_metrics()
        assert data["total_orders"] == 1
        assert data["total_returns"] == 0
        assert data["return_rate_non_tryon_users"] == 0.0

    def test_platform_window_groups_numerator_and_denominator_by_order_created_at(self, db):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        old = _order(db, "100", "USD", tryon=False, created_at=now - timedelta(days=90))
        _return(db, old)
        recent = _order(db, "100", "USD", tryon=False, created_at=now - timedelta(days=2))
        db.commit()

        data = BrandRepository(db).get_platform_admin_analytics(time_range=TimeRange.resolve(days=30))
        assert data["total_orders"] == 1
        assert data["platform_avg_return_rate"] == 0.0
        assert data["return_rate_non_tryon_users"] == 0.0
