"""Keep the shared test database as you found it.

The commerce suites really check out against one shared SQLite database, so
anything a test creates is visible to every test that runs afterwards. Two
existing reporting suites aggregate over the WHOLE order table and are
sensitive to what they find there:

* ``BrandRepository.get_revenue_attribution()`` reports nothing at all
  (``currency=None``, every channel ``None``) once orders exist in more than one
  currency — correct for a mixed ledger, but a converted EGP/AED order left
  behind by a currency test blanks unrelated reporting tests.
* ``test_group6_*`` asserts the attributed sum does not exceed total GMV by more
  than 100, an allowance for discount. That tolerance holds for the handful of
  orders the original suites create; it does not hold once a promo suite adds
  several deeply-discounted orders.

Neither of those is a defect to fix in the reporting code from here. The right
move is for the tests that create the extra rows to remove them again, which is
what this helper does: snapshot the order high-water mark and the catalog stock
before the test, then delete exactly the orders created since and restore stock.
Orders created by every other suite are untouched.
"""

from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import text

from backend.tests.conftest import TestingSessionLocal


def snapshot() -> Dict[str, Any]:
    """Capture the state to restore afterwards."""
    db = TestingSessionLocal()
    try:
        return {
            "stock": db.execute(
                text("select id, stock_level, is_in_stock from product_skus")
            ).all(),
            "max_order_id": db.execute(
                text("select coalesce(max(id), 0) from orders")
            ).scalar(),
        }
    finally:
        db.close()


def restore(state: Dict[str, Any]) -> None:
    """Neutralise orders created since ``snapshot()`` and restore catalog stock.

    The orders are marked ``cancelled`` rather than deleted. ``revenue_eligible``
    excludes cancelled/failed/refunded, so a cancelled order drops out of every
    GMV, revenue and attribution figure — which is all these suites need — while
    every ``order_items`` / ``payment_transactions`` / ``fulfillment_groups`` row
    stays attached to a real parent.

    Deleting the rows instead was tried first and rejected: ORM-deleting an
    order elsewhere in the suite re-points its children's ``order_id`` to NULL,
    which those NOT NULL columns refuse, so leftover deleted parents broke
    unrelated tests. Not deleting is both simpler and safer.
    """
    db = TestingSessionLocal()
    try:
        db.execute(
            text(
                "update orders set status = 'cancelled' "
                "where id > :m and status not in ('cancelled', 'failed', 'refunded')"
            ),
            {"m": state["max_order_id"]},
        )
        for sku_id, stock_level, is_in_stock in state["stock"]:
            db.execute(
                text("update product_skus set stock_level = :s, is_in_stock = :i where id = :id"),
                {"s": stock_level, "i": is_in_stock, "id": sku_id},
            )
        db.commit()
    finally:
        db.close()


def cleanup_orders_fixture():
    """A pytest fixture body usable via ``@pytest.fixture(autouse=True)``."""
    import pytest

    @pytest.fixture(autouse=True)
    def _isolate_orders():
        state = snapshot()
        yield
        restore(state)

    return _isolate_orders
