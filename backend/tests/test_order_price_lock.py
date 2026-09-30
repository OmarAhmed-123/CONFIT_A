"""An order's money must be frozen at creation — amount, currency AND rate.

WHAT WAS ALREADY TRUE
---------------------
`orders` persists total/subtotal/tax/shipping/discount and `order_items`
persists unit_price and subtotal, and `get_order` reads those columns back
verbatim. So the AMOUNTS were already locked. These tests pin that down so a
future refactor that recomputes an order from live catalogue prices fails
loudly instead of silently repricing history.

WHAT WAS MISSING (migration 0028)
---------------------------------
The order recorded "EGP 9,376.57" but not "converted from a USD price book at
52.092039". With live rates (services/fx_rates.py) that rate lives in a
6-hour in-process cache and is unrecoverable minutes later, so a settled
total could not be audited or re-checked. It was also one refactor away from
a real defect: `MONEY_FIELDS` includes `total_amount` and `unit_price`, so
routing an order through `present()` would have re-converted a locked order.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.app.models.catalog import Product, ProductSKU
from backend.app.models.commerce import Order
from backend.tests.conftest import TestingSessionLocal


@pytest.fixture
def db_session(catalog_state_guard):
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


def _buyable_sku(db) -> ProductSKU:
    sku = (
        db.query(ProductSKU)
        .filter(ProductSKU.stock_level > 5, ProductSKU.is_in_stock.is_(True))
        .first()
    )
    assert sku is not None
    return sku


def _place_order(client, db, session_token: str) -> dict:
    sku = _buyable_sku(db)
    add = client.post(
        "/api/v1/commerce/cart/items",
        json={"product_sku_id": sku.id, "quantity": 1},
        headers={"X-Session-Token": session_token},
    )
    assert add.status_code == 201, add.text
    res = client.post(
        "/api/v1/commerce/checkout",
        json={
            "payment_method": "cod",
            "fulfillment_type": "delivery",
            "recipient_name": "QA Price Lock",
            "phone": "+201000000000",
            "address_line": "1 Test Street",
            "city": "Cairo",
            "country": "EG",
            "guest_email": "qa-pricelock@confit-portal-qa.example.com",
        },
        headers={"X-Session-Token": session_token},
    )
    assert res.status_code in (200, 201), res.text
    return res.json()


# ── the lock itself ──────────────────────────────────────────────────────────

def test_a_later_catalogue_price_change_does_not_move_a_settled_order(client, db_session):
    """The core guarantee the shopper is owed."""
    order = _place_order(client, db_session, "lock-a")
    number = order["order_number"]
    locked_total = order["total_amount"]
    locked_unit = order["items"][0]["unit_price"]
    product_id = order["items"][0]["product_id"]

    product = db_session.get(Product, product_id)
    product.base_price = Decimal(str(product.base_price)) * 3
    for sku in product.skus:
        sku.price_override = None
    db_session.commit()

    again = client.get(f"/api/v1/commerce/orders/{number}")
    assert again.status_code == 200, again.text
    body = again.json()
    assert body["total_amount"] == locked_total
    assert body["items"][0]["unit_price"] == locked_unit


def test_the_order_records_the_rate_that_produced_its_total(client, db_session):
    """Provenance, not just the result: amount + currency + source
    denomination + rate makes the order self-describing and auditable."""
    order = _place_order(client, db_session, "lock-b")
    row = db_session.query(Order).filter(Order.order_number == order["order_number"]).one()

    assert row.currency, "an order must always state its currency"
    assert row.pricing_currency, "an order must state what it was converted FROM"
    assert row.fx_rate_used is not None, "an order must state the rate it used"
    assert Decimal(str(row.fx_rate_used)) > 0


def test_an_unconverted_order_records_rate_1_not_null(client, db_session):
    """With no FX configured (the suite's hermetic default) settlement is the
    identity function — and that fact must be RECORDED as 1, so "no conversion
    happened" is distinguishable from "nobody wrote the rate down"."""
    order = _place_order(client, db_session, "lock-c")
    row = db_session.query(Order).filter(Order.order_number == order["order_number"]).one()

    assert row.pricing_currency == row.currency
    assert Decimal(str(row.fx_rate_used)) == Decimal("1")


def test_the_rate_is_exposed_on_the_api_contract(client, db_session):
    order = _place_order(client, db_session, "lock-d")
    body = client.get(f"/api/v1/commerce/orders/{order['order_number']}").json()
    assert body["pricing_currency"] == body["currency"]
    assert float(body["fx_rate_used"]) == 1.0


def test_stored_total_equals_the_sum_of_its_stored_parts(client, db_session):
    """Internal consistency of the frozen figures — a lock that locks
    mutually contradictory numbers is not a lock."""
    order = _place_order(client, db_session, "lock-e")
    row = db_session.query(Order).filter(Order.order_number == order["order_number"]).one()

    expected = (
        Decimal(str(row.subtotal_amount))
        - Decimal(str(row.discount_amount or 0))
        + Decimal(str(row.tax_amount or 0))
        + Decimal(str(row.shipping_amount or 0))
    )
    assert Decimal(str(row.total_amount)) == expected


def test_order_line_prices_are_decimal_exact_not_float_rounded(client, db_session):
    order = _place_order(client, db_session, "lock-f")
    row = db_session.query(Order).filter(Order.order_number == order["order_number"]).one()
    for item in row.items:
        assert Decimal(str(item.subtotal)) == Decimal(str(item.unit_price)) * item.quantity


# ── the refactor guard ───────────────────────────────────────────────────────

def test_presenting_an_order_payload_is_a_no_op_in_its_own_currency(client, db_session):
    """`MONEY_FIELDS` covers total_amount/unit_price/subtotal. If an order
    payload is ever routed through the presentation layer, the idempotence
    rule (convert FROM the payload's declared currency) must make it a no-op
    rather than repricing settled history."""
    from backend.app.services.pricing_presentation import present, resolve_presentation

    order = _place_order(client, db_session, "lock-g")
    fx = resolve_presentation(order["currency"])
    assert present(order, fx) == order
