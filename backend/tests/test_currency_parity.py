"""Currency parity across the cart quote and the order (CUS-02 / CUS-03 / CUS-12).

The audit left these three "needs-test-to-confirm": the same
``MarketPaymentCapabilityRegistry.resolve_settlement`` is used on both
surfaces, but the two call it with DIFFERENT INPUTS — the cart resolves
``settings.MARKET``, checkout resolves the delivery destination from the
request body. If a shopper's destination is not their market, the cart quotes
one currency and the order settles in another.

These tests convert that open question into a verdict by driving the real
configuration:

* same market as destination  -> the two surfaces must agree exactly
* destination differs         -> the cart must be quotable in the destination
                                 currency, so the shopper is not shown EGP and
                                 charged AED
* no treasury rate configured -> both surfaces fail SAFE to the pricing
                                 currency, and still agree

They also pin CUS-03/CUS-12: no double conversion anywhere (the historical bug
was a line priced 180.00 USD surfacing as roughly 48x too much after the
presentation layer converted an amount that had already been converted).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import settings


# These tests check out in a CONVERTED market, leaving EGP/AED orders behind.
# A mixed-currency ledger makes the revenue-attribution reporting suites return
# nothing at all, so clean up behind ourselves (see commerce_test_isolation).
from backend.tests.commerce_test_isolation import cleanup_orders_fixture

_isolate_orders = cleanup_orders_fixture()


def _in_stock_sku(client: TestClient) -> int:
    prods = client.get("/api/v1/catalog/products").json()
    items = prods if isinstance(prods, list) else prods.get("items", [])
    detail = client.get(f"/api/v1/catalog/products/{items[0]['slug']}").json()
    return next(s for s in detail["skus"] if s.get("is_in_stock"))["id"]


def _body(**overrides) -> dict:
    body = {
        "payment_method": "cod",
        "fulfillment_type": "delivery",
        "recipient_name": "Currency Shopper",
        "phone": "+971501234567",
        "address_line": "12 Al Wasl Road",
        "city": "Cairo",
        "shipping_method": "standard",
        "guest_email": "currency.shopper@confit-test.dev",
    }
    body.update(overrides)
    return body


def _dec(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _quote(client: TestClient, headers: dict, **params) -> dict:
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = "/api/v1/commerce/cart" + (f"?{qs}" if qs else "")
    r = client.get(url, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _order_total_is_internally_consistent(order: dict) -> None:
    """subtotal - discount + tax + shipping == total, exactly, in the ORDER's currency."""
    exact = (
        _dec(order["subtotal_amount"])
        - _dec(order["discount_amount"])
        + _dec(order["tax_amount"])
        + _dec(order["shipping_amount"])
    )
    assert _dec(order["total_amount"]) == exact, (
        f"{order['currency']}: components do not sum to the total "
        f"({exact} vs {order['total_amount']})"
    )


@pytest.fixture()
def egp_rates(monkeypatch):
    monkeypatch.setattr(settings, "MARKET", "EG")
    monkeypatch.setattr(settings, "MARKET_FX_RATES", '{"EGP": "48.5", "AED": "3.6725"}')
    yield


def test_same_market_cart_and_order_settle_in_the_same_currency(client: TestClient, egp_rates):
    """Destination == market: the two surfaces must agree, currency and amount."""
    h = {"X-Session-Token": "ccy_same_market"}
    client.post("/api/v1/commerce/cart/items", headers=h,
                json={"product_sku_id": _in_stock_sku(client), "quantity": 1})

    quoted = _quote(client, h, shipping_method="standard")
    order = client.post("/api/v1/commerce/checkout", headers=h, json=_body(country="EG")).json()

    assert quoted["currency"] == "EGP", quoted["currency"]
    assert order["currency"] == "EGP", order["currency"]
    assert _dec(quoted["total"]) == _dec(order["total_amount"]), (
        f"cart quoted {quoted['total']} {quoted['currency']} but the order charged "
        f"{order['total_amount']} {order['currency']}"
    )
    _order_total_is_internally_consistent(order)


def test_cart_can_quote_the_destination_currency(client: TestClient, egp_rates):
    """Destination != market: the cart must be able to quote what checkout will charge."""
    h = {"X-Session-Token": "ccy_destination"}
    client.post("/api/v1/commerce/cart/items", headers=h,
                json={"product_sku_id": _in_stock_sku(client), "quantity": 1})

    quoted = _quote(client, h, shipping_method="standard", country="AE")
    order = client.post("/api/v1/commerce/checkout", headers=h, json=_body(country="AE")).json()

    assert order["currency"] == "AED", order["currency"]
    assert quoted["currency"] == order["currency"], (
        f"cart quoted in {quoted['currency']} but the order settles in {order['currency']} "
        "— the shopper is shown one currency and charged in another"
    )
    assert _dec(quoted["total"]) == _dec(order["total_amount"])


def test_without_a_treasury_rate_both_surfaces_fail_safe_together(client: TestClient, monkeypatch):
    """No rate configured: fall back to the pricing currency on BOTH surfaces."""
    monkeypatch.setattr(settings, "MARKET", "EG")
    monkeypatch.setattr(settings, "MARKET_FX_RATES", "{}")

    h = {"X-Session-Token": "ccy_no_rate"}
    client.post("/api/v1/commerce/cart/items", headers=h,
                json={"product_sku_id": _in_stock_sku(client), "quantity": 1})
    quoted = _quote(client, h, shipping_method="standard")
    order = client.post("/api/v1/commerce/checkout", headers=h, json=_body(country="EG")).json()

    pricing = settings.PRICING_CURRENCY.strip().upper()
    assert quoted["currency"] == pricing
    assert order["currency"] == pricing
    assert _dec(quoted["total"]) == _dec(order["total_amount"])


def test_no_double_conversion_of_line_items(client: TestClient, egp_rates):
    """CUS-03/CUS-12: unit_price * quantity must equal subtotal in the quoted currency.

    The historical bug converted an already-converted amount, so a line would
    surface at roughly rate-squared. This pins that a converted line is
    internally consistent.
    """
    h = {"X-Session-Token": "ccy_double_conv"}
    client.post("/api/v1/commerce/cart/items", headers=h,
                json={"product_sku_id": _in_stock_sku(client), "quantity": 2})
    cart = _quote(client, h, shipping_method="standard")

    assert cart["currency"] == "EGP"
    for line in cart["items"]:
        expected = _dec(Decimal(str(line["unit_price"])) * line["quantity"])
        assert _dec(line["subtotal"]) == expected, (
            f"line subtotal {line['subtotal']} != unit_price x quantity {expected} "
            "— double conversion"
        )
    assert _dec(cart["subtotal"]) == _dec(sum(Decimal(str(l["subtotal"])) for l in cart["items"]))


def test_cart_total_is_internally_consistent_in_a_converted_market(client: TestClient, egp_rates):
    h = {"X-Session-Token": "ccy_cart_consistent"}
    client.post("/api/v1/commerce/cart/items", headers=h,
                json={"product_sku_id": _in_stock_sku(client), "quantity": 1})
    cart = _quote(client, h, shipping_method="standard")
    exact = (
        _dec(cart["subtotal"]) - _dec(cart["discount_amount"])
        + _dec(cart["tax_amount"]) + _dec(cart["shipping_amount"])
    )
    assert _dec(cart["total"]) == exact


def test_converted_amounts_keep_cent_precision(client: TestClient, egp_rates):
    """Every converted figure is still 2dp — no 11882.500000001 in the contract."""
    h = {"X-Session-Token": "ccy_precision"}
    client.post("/api/v1/commerce/cart/items", headers=h,
                json={"product_sku_id": _in_stock_sku(client), "quantity": 3})
    cart = _quote(client, h, shipping_method="standard")
    for field in ("subtotal", "discount_amount", "tax_amount", "shipping_amount", "total"):
        value = Decimal(str(cart[field]))
        assert value == value.quantize(Decimal("0.01")), f"{field} = {cart[field]}"
