"""A discount the database records must be visible in the order API.

THE DEFECT, FOUND BY AUDITING PRODUCTION
-----------------------------------------
Order CONF-6CA549BB on production:

    database :  order_discount 18.00, sum(line discounts) 18.00  CONSERVED
    API      :  items[0].discount_amount -> null

Migration 0025 apportioned the discount per line and the allocation was
correct. `OrderItemOut` simply never listed the field, so every line
reported no discount. Neither the shopper nor the brand could see where
the 18.00 went. The value existed; the contract hid it.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from backend.app.models.commerce import Order, OrderItem
from backend.app.schemas.commerce import OrderItemOut


def test_schema_exposes_the_allocated_discount():
    assert "discount_amount" in OrderItemOut.model_fields
    assert "net_amount" in OrderItemOut.model_fields


def test_net_is_derived_on_the_server_not_left_to_the_client():
    """A client that forgets to subtract shows the pre-discount figure."""
    line = OrderItemOut(
        id=1, product_id=1, product_title="X", brand_name="B", size="M",
        color="Navy", unit_price=100.0, quantity=2, subtotal=200.0,
        discount_amount=18.0, is_returned=False,
    )
    assert line.net_amount == 182.0


def test_net_equals_subtotal_when_nothing_was_discounted():
    line = OrderItemOut(
        id=1, product_id=1, product_title="X", brand_name="B", size="M",
        color="Navy", unit_price=100.0, quantity=1, subtotal=100.0,
        is_returned=False,
    )
    assert line.discount_amount == 0.0
    assert line.net_amount == 100.0


def test_order_api_reports_the_line_discount_it_stored(client: TestClient) -> None:
    """End to end: place a discounted order, then read it back."""
    import uuid

    email = f"disc.vis.{uuid.uuid4().hex[:8]}@confit-test.example.com"
    client.post("/api/v1/auth/register", json={
        "email": email, "password": "Password123!", "full_name": "Disc Vis"})
    token = client.post("/api/v1/auth/login", json={
        "email": email, "password": "Password123!"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}",
               "X-Session-Token": f"s-{uuid.uuid4().hex[:8]}"}

    products = client.get("/api/v1/catalog/products").json()
    detail = client.get(f"/api/v1/catalog/products/{products[0]['id']}").json()
    sku = next((s for s in detail["skus"] if s["is_in_stock"]), detail["skus"][0])
    client.post("/api/v1/commerce/cart/items",
                json={"product_sku_id": sku["id"], "quantity": 2}, headers=headers)
    promo = client.post("/api/v1/commerce/cart/promo",
                        json={"promo_code": "CONFIT10"}, headers=headers)
    assert promo.status_code == 200, promo.text

    placed = client.post("/api/v1/commerce/checkout", json={
        "payment_method": "card", "fulfillment_type": "delivery",
        "idempotency_key": f"vis-{uuid.uuid4().hex[:8]}", "promo_code": "CONFIT10",
        "recipient_name": "Disc Vis", "phone": "+971501234567",
        "address_line": "1 Test St", "city": "Dubai", "country": "AE",
    }, headers=headers)
    assert placed.status_code == 200, placed.text
    order_number = placed.json()["order_number"]

    body = client.get(f"/api/v1/commerce/orders/{order_number}",
                      headers=headers).json()
    items = body.get("items") or []
    assert items, "the order returned no lines"

    total_line_discount = sum(Decimal(str(i["discount_amount"])) for i in items)
    assert total_line_discount > 0, (
        "the order carried a discount but every line reported 0 — the "
        "allocation is invisible in the API"
    )
    assert total_line_discount == Decimal(str(body["discount_amount"])), (
        "line discounts must sum to the order discount, exactly"
    )
    for item in items:
        assert item["net_amount"] == round(
            item["subtotal"] - item["discount_amount"], 2
        )
