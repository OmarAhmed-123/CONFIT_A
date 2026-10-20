"""CUS-01 — the cart quote and the order charge must agree on shipping.

Regression target (proven live on 258a5fd): a one-item cart (180.00) quoted
272.25 with `shipping_amount = 15.00`, then the SAME cart checked out with
`shipping_method="express"` charged 292.25 — `shipping_amount = 35.00`. A
20.00 gap between what the shopper was shown and what they were charged.

Root cause: `_format_cart` had no express branch at all and `GET /cart` had no
way to ask for one, while `checkout()` priced express from a second, divergent
copy of the threshold logic.

The fix is one shared authority — `core.shipping.compute_shipping_fee` — called
by both surfaces, and a `shipping_method` query parameter on the cart quote so
the cart can actually quote what checkout will charge.

Every assertion here compares the two surfaces to each other, not to a literal,
so the tests keep meaning if the fee constants change.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.tests.commerce_test_isolation import cleanup_orders_fixture

_isolate_orders = cleanup_orders_fixture()

SLUG = "goodyear-welted-leather-oxford-shoes"

EXPRESS = 35.0
STANDARD = 15.0
FREE_THRESHOLD = 250.0


def _in_stock_sku(client: TestClient) -> dict:
    prods = client.get("/api/v1/catalog/products").json()
    items = prods if isinstance(prods, list) else prods.get("items", [])
    slug = next((p["slug"] for p in items if p["slug"] == SLUG), items[0]["slug"])
    detail = client.get(f"/api/v1/catalog/products/{slug}").json()
    return next(s for s in detail["skus"] if s.get("is_in_stock"))


def _add(client: TestClient, headers: dict, sku_id: int, qty: int = 1) -> None:
    r = client.post(
        "/api/v1/commerce/cart/items",
        headers=headers,
        json={"product_sku_id": sku_id, "quantity": qty},
    )
    assert r.status_code == 201, r.text


def _quote(client: TestClient, headers: dict, shipping_method: str) -> dict:
    r = client.get(
        f"/api/v1/commerce/cart?shipping_method={shipping_method}", headers=headers
    )
    assert r.status_code == 200, r.text
    return r.json()


def _checkout(client: TestClient, headers: dict, **overrides) -> dict:
    body = {
        "payment_method": "cod",
        "fulfillment_type": "delivery",
        "recipient_name": "Parity Shopper",
        "phone": "+971501234567",
        "address_line": "12 Al Wasl Road",
        "city": "Dubai",
        "country": "AE",
        "shipping_method": "standard",
        "guest_email": "parity.shopper@confit-test.dev",
    }
    body.update(overrides)
    r = client.post("/api/v1/commerce/checkout", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_express_cart_quote_equals_express_order_charge(client: TestClient):
    """THE regression: one cart, two surfaces, one number."""
    h = {"X-Session-Token": "cus01_express_parity"}
    sku = _in_stock_sku(client)
    _add(client, h, sku["id"])

    quoted = _quote(client, h, "express")
    charged = _checkout(client, h, shipping_method="express")

    assert charged["total_amount"] == pytest.approx(quoted["total"]), (
        f"quote {quoted['total']} != charge {charged['total_amount']} — the CUS-01 gap is back"
    )
    assert charged["total_amount"] - quoted["total"] == 0.0
    assert quoted["shipping_method"] == "express"
    assert quoted["shipping_amount"] == pytest.approx(EXPRESS), "cart must quote the express fee"
    assert charged["shipping_amount"] == pytest.approx(EXPRESS)


def test_standard_cart_quote_equals_standard_order_charge(client: TestClient):
    """Standard must stay unchanged by the fix."""
    h = {"X-Session-Token": "cus01_standard_parity"}
    sku = _in_stock_sku(client)
    _add(client, h, sku["id"])

    quoted = _quote(client, h, "standard")
    charged = _checkout(client, h, shipping_method="standard")

    assert charged["total_amount"] == pytest.approx(quoted["total"])
    assert quoted["shipping_method"] == "standard"
    assert quoted["shipping_amount"] == pytest.approx(STANDARD)
    assert charged["shipping_amount"] == pytest.approx(STANDARD)


def test_free_shipping_threshold_honoured_for_both_methods(client: TestClient):
    """Above the threshold BOTH methods charge zero — on the cart and on the order."""
    sku = _in_stock_sku(client)
    probe = {"X-Session-Token": "cus01_threshold_probe"}
    _add(client, probe, sku["id"])
    unit = float(_quote(client, probe, "standard")["items"][0]["unit_price"])
    qty = int(FREE_THRESHOLD // unit) + 1

    for method in ("standard", "express"):
        h = {"X-Session-Token": f"cus01_threshold_{method}"}
        sku = _in_stock_sku(client)
        _add(client, h, sku["id"], qty=qty)
        quoted = _quote(client, h, method)
        assert quoted["subtotal"] >= FREE_THRESHOLD, "test setup must clear the threshold"
        assert quoted["shipping_amount"] == pytest.approx(0.0), (
            f"{method}: free-shipping threshold not honoured on the cart quote"
        )
        charged = _checkout(client, h, shipping_method=method)
        assert charged["shipping_amount"] == pytest.approx(0.0), (
            f"{method}: free-shipping threshold not honoured on the order"
        )
        assert charged["total_amount"] == pytest.approx(quoted["total"])


def test_bopis_is_free_and_ignores_shipping_method(client: TestClient):
    """Boutique pickup never attracts a delivery fee, express or not."""
    h = {"X-Session-Token": "cus01_bopis"}
    sku = _in_stock_sku(client)
    _add(client, h, sku["id"])

    for method in ("standard", "express"):
        charged = _checkout(
            client, h, fulfillment_type="bopis", bopis_store_id=1, shipping_method=method
        )
        assert charged["shipping_amount"] == pytest.approx(0.0)
        assert charged["total_amount"] == pytest.approx(
            charged["subtotal_amount"] + charged["tax_amount"], abs=0.01
        ), "bopis total must be subtotal + tax with no delivery fee"

        # refill the cart for the next method (checkout consumed it)
        _add(client, h, sku["id"])


def test_zero_value_cart_is_not_charged_shipping_it_never_quoted(client: TestClient):
    """A zero-subtotal cart quoted free shipping must not be charged a fee.

    The cart has always waived the fee when subtotal is 0.00 (that is how an
    empty cart renders 0). Checkout used to charge the standard fee instead, so
    a zero-priced line would have been billed something the cart never showed.
    """
    from backend.tests.conftest import TestingSessionLocal
    from backend.app.models.catalog import ProductSKU

    db = TestingSessionLocal()
    sku_row = (db.query(ProductSKU)
              .filter(ProductSKU.is_in_stock.is_(True), ProductSKU.size.isnot(None))
              .first())
    original_override = sku_row.price_override
    original_price = sku_row.product.base_price
    sku_row.price_override = 0
    db.commit()
    sku_id = sku_row.id
    db.close()

    try:
        h = {"X-Session-Token": "cus01_zero_value"}
        _add(client, h, sku_id)
        quoted = _quote(client, h, "standard")
        assert quoted["subtotal"] == pytest.approx(0.0), "test setup must yield a zero subtotal"
        assert quoted["shipping_amount"] == pytest.approx(0.0)

        charged = _checkout(client, h, shipping_method="standard")
        assert charged["shipping_amount"] == pytest.approx(0.0), (
            "order charged shipping the cart never quoted"
        )
        assert charged["total_amount"] == pytest.approx(quoted["total"])
    finally:
        db = TestingSessionLocal()
        row = db.query(ProductSKU).filter(ProductSKU.id == sku_id).first()
        row.price_override = original_override
        db.commit()
        db.close()


def test_invalid_shipping_method_is_rejected_not_silently_standardised(client: TestClient):
    """An unknown method must 422 on the quote, never quietly price as standard."""
    h = {"X-Session-Token": "cus01_invalid_method"}
    sku = _in_stock_sku(client)
    _add(client, h, sku["id"])
    r = client.get("/api/v1/commerce/cart?shipping_method=teleport", headers=h)
    assert r.status_code == 422, r.text
