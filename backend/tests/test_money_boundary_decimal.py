"""Money must cross the JSON boundary as an exact 2-decimal-place value.

Honest status note (do not overclaim): the previous implementation was
``OrderItemOut.net_amount = round(float(subtotal) - float(discount or 0.0), 2)``
— a float subtraction inside the response model. I probed for an observable
drift inside ``NUMERIC(12,2)`` and could not find one: a double's ulp at
1e10 is ~2e-6, far below half a cent, so a 2dp difference always rounds back
exactly, and a scan of every numeric field in cart and order payloads found no
value with more than 2 decimal places.

So these tests are NOT red on the old code, and I am not going to pretend
otherwise. What they pin is structural: money is a ``Decimal`` inside the
schema too, quantised once with ROUND_HALF_UP, with no float arithmetic
reachable. The one thing they DO catch is a float *representation* artifact
sneaking in through coercion — e.g. a value that arrives as ``0.1`` and would
otherwise surface as ``0.30000000000000004``-style noise, or an unquantised
third decimal reaching the client.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.tests.commerce_test_isolation import cleanup_orders_fixture

_isolate_orders = cleanup_orders_fixture()

from backend.app.schemas.commerce import CartOut, OrderItemOut


def _in_stock_sku(client: TestClient) -> int:
    prods = client.get("/api/v1/catalog/products").json()
    items = prods if isinstance(prods, list) else prods.get("items", [])
    detail = client.get(f"/api/v1/catalog/products/{items[0]['slug']}").json()
    return next(s for s in detail["skus"] if s.get("is_in_stock"))["id"]


def _body(**overrides) -> dict:
    body = {
        "payment_method": "cod",
        "fulfillment_type": "delivery",
        "recipient_name": "Cent Shopper",
        "phone": "+971501234567",
        "address_line": "12 Al Wasl Road",
        "city": "Dubai",
        "country": "AE",
        "shipping_method": "standard",
        "guest_email": "cent.shopper@confit-test.dev",
    }
    body.update(overrides)
    return body


def test_every_money_value_in_the_contract_is_exactly_two_decimals(client: TestClient):
    """Sweep the whole cart payload, then the whole order payload."""
    h = {"X-Session-Token": "money_boundary_sweep"}
    client.post("/api/v1/commerce/cart/items", headers=h,
                json={"product_sku_id": _in_stock_sku(client), "quantity": 2})

    offenders = []

    def scan(node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                scan(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                scan(v, f"{path}[{i}]")
        elif isinstance(node, float):
            as_dec = Decimal(str(node))
            if as_dec != as_dec.quantize(Decimal("0.01")):
                offenders.append((path, node))

    scan(client.get("/api/v1/commerce/cart", headers=h).json())
    scan(client.post("/api/v1/commerce/checkout", headers=h, json=_body()).json())

    assert not offenders, f"money reached the client with sub-cent precision: {offenders}"


def test_net_amount_is_exactly_subtotal_minus_discount(client: TestClient):
    """The served net must equal the exact Decimal difference, not a float one."""
    h = {"X-Session-Token": "money_boundary_net"}
    client.post("/api/v1/commerce/cart/items", headers=h,
                json={"product_sku_id": _in_stock_sku(client), "quantity": 3})
    order = client.post("/api/v1/commerce/checkout", headers=h, json=_body()).json()

    for line in order["items"]:
        expected = Decimal(str(line["subtotal"])) - Decimal(str(line["discount_amount"]))
        assert Decimal(str(line["net_amount"])) == expected.quantize(Decimal("0.01")), (
            f"net_amount {line['net_amount']} != subtotal - discount {expected}"
        )


def test_order_total_equals_the_exact_sum_of_its_components(client: TestClient):
    """subtotal - discount + tax + shipping, compared as Decimals, not floats."""
    h = {"X-Session-Token": "money_boundary_total"}
    client.post("/api/v1/commerce/cart/items", headers=h,
                json={"product_sku_id": _in_stock_sku(client), "quantity": 1})
    order = client.post("/api/v1/commerce/checkout", headers=h, json=_body()).json()

    exact = (
        Decimal(str(order["subtotal_amount"]))
        - Decimal(str(order["discount_amount"]))
        + Decimal(str(order["tax_amount"]))
        + Decimal(str(order["shipping_amount"]))
    ).quantize(Decimal("0.01"))
    assert Decimal(str(order["total_amount"])) == exact


@pytest.mark.parametrize(
    "subtotal,discount,expected",
    [
        ("0.30", "0.10", "0.20"),          # classic float-noise territory
        ("0.10", "0.00", "0.10"),
        ("245.00", "18.00", "227.00"),
        ("9999999999.99", "0.01", "9999999999.98"),  # top of NUMERIC(12,2)
        ("1.01", "1.00", "0.01"),
    ],
)
def test_net_amount_is_exact_for_cent_sensitive_values(subtotal, discount, expected):
    """Model-level: the derivation is Decimal arithmetic, not float."""
    line = OrderItemOut(
        id=1, product_id=1, product_title="t", brand_name="b", size="41",
        color="black", quantity=1, is_returned=False,
        unit_price=Decimal(subtotal), subtotal=Decimal(subtotal),
        discount_amount=Decimal(discount),
    )
    assert Decimal(str(line.net_amount)) == Decimal(expected)


def test_money_fields_are_declared_as_decimal_not_float():
    """The schema type itself is the guarantee — assert it, don't assume it."""
    for name in ("unit_price", "subtotal", "discount_amount", "net_amount"):
        annotation = str(OrderItemOut.model_fields[name].annotation)
        assert "Decimal" in annotation, f"OrderItemOut.{name} is still {annotation}"
    for name in ("subtotal", "discount_amount", "tax_amount", "shipping_amount", "total"):
        annotation = str(CartOut.model_fields[name].annotation)
        assert "Decimal" in annotation, f"CartOut.{name} is still {annotation}"


def test_a_large_but_legal_amount_survives_the_round_trip(client: TestClient):
    """A near-limit amount must round-trip through JSON without losing a cent."""
    from backend.tests.conftest import TestingSessionLocal
    from backend.app.models.catalog import ProductSKU

    db = TestingSessionLocal()
    row = (
        db.query(ProductSKU)
        .filter(ProductSKU.is_in_stock.is_(True), ProductSKU.size.isnot(None))
        .first()
    )
    original = row.price_override
    row.price_override = Decimal("9000000000.01")
    db.commit()
    sku_id = row.id
    db.close()

    try:
        h = {"X-Session-Token": "money_boundary_large"}
        client.post("/api/v1/commerce/cart/items", headers=h,
                    json={"product_sku_id": sku_id, "quantity": 1})
        resp = client.get("/api/v1/commerce/cart", headers=h)
        assert resp.status_code == 200, resp.text
        cart = resp.json()
        assert Decimal(str(cart["items"][0]["unit_price"])) == Decimal("9000000000.01")
        assert Decimal(str(cart["subtotal"])) == Decimal("9000000000.01")
    finally:
        db = TestingSessionLocal()
        row = db.query(ProductSKU).filter(ProductSKU.id == sku_id).first()
        row.price_override = original
        db.commit()
        db.close()
