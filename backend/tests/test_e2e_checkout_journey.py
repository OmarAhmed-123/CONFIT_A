"""One end-to-end consumer journey: catalogue -> cart -> checkout -> order.

The assertion that matters: the order's total equals the total the SERVER
quoted for that cart, and equals the server's own component sum. Nothing in the
journey derives a monetary value from client input — the checkout body carries
no money field at all, so the only way the figures can match is if the server
computed both.

This is the acceptance test the whole slice exists for: a shopper is shown a
number, pays that number, and the stored order agrees.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient

from backend.tests.commerce_test_isolation import cleanup_orders_fixture

_isolate_orders = cleanup_orders_fixture()


def _dec(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _register(client: TestClient) -> dict:
    email = f"journey_{uuid.uuid4().hex[:10]}@confit-test.dev"
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": "Journey Shopper"},
    )
    assert r.status_code == 201, r.text
    return {
        "Authorization": f"Bearer {r.json()['access_token']}",
        "X-Session-Token": f"journey_{uuid.uuid4().hex[:10]}",
    }


def _browsable_skus(client: TestClient, limit: int = 2):
    """Walk the catalogue the way a shopper does: list, then open a product."""
    listing = client.get("/api/v1/catalog/products").json()
    items = listing if isinstance(listing, list) else listing.get("items", [])
    picked = []
    for entry in items:
        if len(picked) >= limit:
            break
        detail = client.get(f"/api/v1/catalog/products/{entry['slug']}").json()
        sku = next((s for s in detail["skus"] if s.get("is_in_stock")), None)
        if sku:
            picked.append(sku)
    assert len(picked) == limit, "catalogue must offer at least two in-stock skus"
    return picked


def test_shopper_journey_cart_to_order_total_matches_server_quote(client: TestClient):
    headers = _register(client)
    skus = _browsable_skus(client)

    # --- browse -> add to cart -------------------------------------------
    for sku in skus:
        added = client.post(
            "/api/v1/commerce/cart/items",
            headers=headers,
            json={"product_sku_id": sku["id"], "quantity": 1},
        )
        assert added.status_code == 201, added.text

    # --- cart quote -------------------------------------------------------
    quote = client.get(
        "/api/v1/commerce/cart?shipping_method=express", headers=headers
    ).json()
    assert quote["items_count"] == 2
    assert quote["currency"]

    # --- checkout: note there is NO money field in this payload ----------
    body = {
        "payment_method": "cod",
        "fulfillment_type": "delivery",
        "recipient_name": "Journey Shopper",
        "phone": "+971501234567",
        "address_line": "12 Al Wasl Road",
        "city": "Dubai",
        "country": "AE",
        "shipping_method": "express",
        "idempotency_key": str(uuid.uuid4()),
    }
    assert not any(k for k in body if "amount" in k or k in ("total", "subtotal", "price"))

    placed = client.post("/api/v1/commerce/checkout", headers=headers, json=body)
    assert placed.status_code == 200, placed.text
    order = placed.json()

    # --- the shopper's order page ----------------------------------------
    detail = client.get(f"/api/v1/commerce/orders/{order['order_number']}", headers=headers)
    assert detail.status_code == 200, detail.text
    stored = detail.json()

    # --- THE assertions ---------------------------------------------------
    # 1. What was quoted is what was charged.
    assert _dec(stored["total_amount"]) == _dec(quote["total"]), (
        f"quoted {quote['total']} {quote['currency']}, charged "
        f"{stored['total_amount']} {stored['currency']}"
    )
    # 2. What is stored equals the server's own component sum.
    components = (
        _dec(stored["subtotal_amount"])
        - _dec(stored["discount_amount"])
        + _dec(stored["tax_amount"])
        + _dec(stored["shipping_amount"])
    )
    assert _dec(stored["total_amount"]) == components
    # 3. Shipping followed the documented rule for the express method — free at
    #    or above the threshold, the express fee below it. (Two items clear the
    #    threshold, so this asserts the rule rather than a fixed number.)
    from backend.app.core.config import settings
    from backend.app.core.shipping import compute_shipping_fee

    expected_shipping = compute_shipping_fee(
        Decimal(str(stored["subtotal_amount"])),
        Decimal(str(stored["discount_amount"])),
        fulfillment="delivery",
        shipping_method="express",
    )
    assert _dec(stored["shipping_amount"]) == _dec(expected_shipping), (
        f"express shipping {stored['shipping_amount']} != rule {expected_shipping} "
        f"(threshold {settings.FREE_SHIPPING_THRESHOLD})"
    )
    # 4. The cart is consumed and the shopper cannot check out twice.
    assert client.get("/api/v1/commerce/cart", headers=headers).json()["items_count"] == 0
    # A retry carrying the same idempotency key replays the SAME order (200), it
    # does not place a second one. Distinct from the empty-cart guard, which is
    # covered in test_cus01/test_checkout_rejects suites.
    again = client.post("/api/v1/commerce/checkout", headers=headers, json=body)
    assert again.status_code == 200, again.text
    assert again.json()["order_number"] == order["order_number"], (
        "the retry created a second order instead of replaying the first"
    )


def test_journey_is_idempotent_for_the_same_key(client: TestClient):
    """A retried checkout returns the same order rather than charging twice."""
    headers = _register(client)
    sku = _browsable_skus(client, limit=1)[0]
    client.post(
        "/api/v1/commerce/cart/items",
        headers=headers,
        json={"product_sku_id": sku["id"], "quantity": 1},
    )
    body = {
        "payment_method": "cod",
        "fulfillment_type": "delivery",
        "recipient_name": "Journey Shopper",
        "phone": "+971501234567",
        "address_line": "12 Al Wasl Road",
        "city": "Dubai",
        "country": "AE",
        "shipping_method": "standard",
        "idempotency_key": f"journey-{uuid.uuid4()}",
    }
    first = client.post("/api/v1/commerce/checkout", headers=headers, json=body)
    assert first.status_code == 200, first.text
    second = client.post("/api/v1/commerce/checkout", headers=headers, json=body)
    assert second.status_code == 200, second.text
    assert second.json()["order_number"] == first.json()["order_number"]
    assert _dec(second.json()["total_amount"]) == _dec(first.json()["total_amount"])


def test_journey_is_demo_mode_and_never_claims_a_real_charge(client: TestClient):
    """No PSP is wired: the order must say so rather than pretend it was paid."""
    headers = _register(client)
    sku = _browsable_skus(client, limit=1)[0]
    client.post(
        "/api/v1/commerce/cart/items",
        headers=headers,
        json={"product_sku_id": sku["id"], "quantity": 1},
    )
    order = client.post(
        "/api/v1/commerce/checkout",
        headers=headers,
        json={
            "payment_method": "cod",
            "fulfillment_type": "delivery",
            "recipient_name": "Journey Shopper",
            "phone": "+971501234567",
            "address_line": "12 Al Wasl Road",
            "city": "Dubai",
            "country": "AE",
            "shipping_method": "standard",
        },
    ).json()
    assert order["payment_status"] != "paid", (
        "a demo-mode order must never report a completed charge"
    )
