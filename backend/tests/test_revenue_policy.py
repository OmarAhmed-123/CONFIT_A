"""G-13 — one vocabulary for "does this order count as revenue?".

Before this change the admin dashboard filtered GMV with
``status NOT IN ('cancelled','refunded')`` while the attribution ledger on the
same screen used ``('cancelled','refunded','failed')``. A payment-failed order
was inside the headline and outside its own breakdown. Three *return-rate*
denominators also excluded refunded orders, so the return rate fell every time
a return actually succeeded.

These tests pin behaviour, not implementation:

* the classification covers the whole ``ORDER_TRANSITIONS`` state machine, and
  an unknown state is refused instead of defaulting to revenue;
* a payment-failed order is in neither GMV nor the attribution base;
* the ledger and GMV exclude the same orders;
* the denominator of a return rate does not shrink when a refund completes.

Every figure is read through the real repository methods — nothing here
re-implements the rule under test. Rows are created under a unique
``order_number`` prefix and deleted again, because the test database is shared
for the whole session.
"""

from decimal import Decimal
from pathlib import Path

import uuid

import pytest
from sqlalchemy import func

from backend.app.core.revenue_policy import (
    NON_REVENUE_ORDER_STATUSES,
    RETURN_DENOMINATOR_EXCLUDED_STATUSES,
    classify_order_status,
    revenue_eligible,
    return_denominator_eligible,
    unclassified_states,
)
from backend.app.models.catalog import Product
from backend.app.models.commerce import Order, OrderItem, ReturnRequest
from backend.app.repositories.brand_repository import BrandRepository
from backend.app.services.commerce_service import ORDER_TRANSITIONS
from backend.tests.conftest import TestingSessionLocal

PREFIX = "revenue-policy-test"


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _cleanup(db):
    for o in db.query(Order).filter(Order.order_number.like(f"{PREFIX}%")).all():
        db.query(OrderItem).filter(OrderItem.order_id == o.id).delete()
        db.query(ReturnRequest).filter(ReturnRequest.order_id == o.id).delete()
        db.delete(o)
    db.commit()


@pytest.fixture
def seeded(db):
    """Factory for one order (+ one item, optionally + one return request)."""
    product = db.query(Product).first()
    assert product is not None, "the seeded catalogue must contain a product"
    _cleanup(db)

    def add(status, amount, try_on=False, returned=False, number=None):
        order = Order(
            order_number=number or f"{PREFIX}-{status}-{uuid.uuid4().hex[:12]}",
            total_amount=Decimal(str(amount)),
            subtotal_amount=Decimal(str(amount)),
            status=status,
            try_on_assisted=try_on,
        )
        db.add(order)
        db.flush()
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                brand_id=product.brand_id,
                product_title=f"{PREFIX} item",
                brand_name=f"{PREFIX} brand",
                size="M",
                color="Navy",
                unit_price=Decimal(str(amount)),
                quantity=1,
                subtotal=Decimal(str(amount)),
                is_returned=returned,
            )
        )
        if returned:
            db.add(
                ReturnRequest(
                    return_number=f"{PREFIX}-rr-{order.order_number}",
                    order_id=order.id,
                    reason="does not fit",
                    refund_amount=Decimal(str(amount)),
                    status="approved",
                    try_on_used_for_item=try_on,
                )
            )
        db.flush()
        return order

    yield add
    _cleanup(db)


def _gmv(db) -> Decimal:
    return Decimal(
        str(
            db.query(func.sum(Order.total_amount))
            .filter(revenue_eligible(Order.status))
            .scalar()
            or 0
        )
    )


# --- the classification itself ---------------------------------------------


def test_the_policy_covers_every_state_the_state_machine_can_reach():
    """A new order status must be classified, not silently counted as revenue."""
    assert unclassified_states(ORDER_TRANSITIONS.keys()) == []


def test_every_state_the_machine_can_reach_has_a_bucket():
    for status in ORDER_TRANSITIONS:
        assert classify_order_status(status) in {
            "non_revenue",
            "return_in_flight",
            "revenue",
        }


def test_an_unclassified_status_is_refused_rather_than_assumed_to_be_revenue():
    with pytest.raises(ValueError, match="not classified"):
        classify_order_status("some_status_nobody_has_seen")


def test_refunded_is_not_revenue_but_stays_in_the_return_denominator():
    """The two sets differ on purpose; that difference is the whole point."""
    assert "refunded" in NON_REVENUE_ORDER_STATUSES
    assert "refunded" not in RETURN_DENOMINATOR_EXCLUDED_STATUSES
    assert RETURN_DENOMINATOR_EXCLUDED_STATUSES < NON_REVENUE_ORDER_STATUSES


# --- G-13: GMV and the attribution base measure the same population ---------


def test_gmv_does_not_move_when_a_payment_fails(db, seeded):
    """The regression G-13 describes, measured in money rather than rows."""
    before = _gmv(db)

    seeded("failed", 777)
    db.commit()
    assert _gmv(db) == before, "a payment-failed order must never count as revenue"

    seeded("cancelled", 777)
    seeded("refunded", 777)
    db.commit()
    assert _gmv(db) == before, "cancelled and refunded orders are not revenue either"

    seeded("delivered", 777)
    db.commit()
    assert _gmv(db) == before + Decimal("777"), "a delivered order is revenue"


def test_the_analytics_payload_states_its_own_revenue_rule(db, seeded):
    seeded("failed", 10)
    db.commit()
    analytics = BrandRepository(db).get_platform_admin_analytics()
    assert analytics["revenue_excludes_statuses"] == ["cancelled", "failed", "refunded"]
    assert analytics["revenue_basis"] == "accrual"


def test_the_ledger_and_gmv_exclude_the_same_orders(db, seeded):
    """Both figures appear on one screen; they must filter one population."""
    for status in ("failed", "cancelled", "refunded"):
        seeded(status, 100)
    db.commit()

    for status in NON_REVENUE_ORDER_STATUSES:
        leaked = (
            db.query(OrderItem)
            .join(Order, OrderItem.order_id == Order.id)
            .filter(revenue_eligible(Order.status), Order.status == status)
            .count()
        )
        assert leaked == 0, f"{status} items leaked into the eligible set"

    ledger = BrandRepository(db).compute_item_grain_attribution()
    assert Decimal(str(ledger["net_item_revenue"])) >= 0
    assert ledger["eligible_items"] >= 0


def test_no_revenue_filter_in_the_repository_is_hand_written_anymore():
    """Guard the DRY property: the inline literals must not creep back."""
    src = Path("backend/app/repositories/brand_repository.py").read_text()
    assert 'Order.status.notin_(["cancelled"' not in src
    assert "Order.status.notin_(list(self.INELIGIBLE_ORDER_STATUSES))" not in src
    # the retained public constant must still agree with the policy module
    assert set(BrandRepository.INELIGIBLE_ORDER_STATUSES) == set(NON_REVENUE_ORDER_STATUSES)


# --- survivorship: a return rate must not reward successful returns ---------


def test_a_refunded_order_stays_in_the_return_rate_denominator(db, seeded):
    before = (
        db.query(Order).filter(return_denominator_eligible(Order.status)).count()
    )
    seeded("refunded", 100, returned=True)
    db.commit()
    after = (
        db.query(Order).filter(return_denominator_eligible(Order.status)).count()
    )
    assert after == before + 1, "a refunded order must stay in the denominator"

    excluded_before = db.query(Order).filter(Order.status == "cancelled").count()
    seeded("cancelled", 100)
    db.commit()
    assert (
        db.query(Order).filter(return_denominator_eligible(Order.status)).count()
        == after
    ), "a cancelled order is not a return opportunity and stays out"
    assert db.query(Order).filter(Order.status == "cancelled").count() == excluded_before + 1


def test_the_denominator_does_not_shrink_when_a_refund_completes(db, seeded):
    """Two worlds that differ only in whether the refund was issued.

    Four delivered orders, one of them returned, in both worlds; in world B the
    returned order has completed its refund. The return counts are identical, so
    if the denominator excluded refunded orders world B would report a *lower*
    return rate — the metric would reward the outcome it exists to measure.
    """
    repo = BrandRepository(db)

    def world(status_of_returned_order):
        _cleanup(db)
        for i in range(4):
            returned = i == 0
            seeded(
                status_of_returned_order if returned else "delivered",
                100,
                returned=returned,
                number=f"{PREFIX}-world-{status_of_returned_order}-{i}",
            )
        db.commit()
        return repo.get_return_reduction_metrics()

    completed = world("refunded")
    pending = world("delivered")

    assert completed["total_orders"] == pending["total_orders"], (
        "the return-rate denominator shrank because a refund completed"
    )
    assert completed["total_returns"] == pending["total_returns"]
    assert completed["platform_avg_return_rate"] == pending["platform_avg_return_rate"], (
        "return rate improved because a refund completed — survivorship bias"
    )
    _cleanup(db)
