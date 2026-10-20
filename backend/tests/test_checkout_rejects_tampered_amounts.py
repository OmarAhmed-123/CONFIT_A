"""A client-supplied money field must be REFUSED, not silently ignored.

``CheckoutRequest`` never had a monetary field, and every figure was already
derived server-side from the database, so a tampered ``total`` could not change
what was charged. But without ``extra="forbid"`` the field was accepted and
dropped on the floor: the API answered **200** while quietly discarding what the
caller asked for. A shopper (or an integration) that sends ``total`` gets no
signal that its value was meaningless, and a security review reading the code
cannot tell "ignored" from "honoured" without tracing the whole path.

Constitution Principle II wants an honest error at the boundary. These tests
pin the contract: unknown fields are a hard 422, and nothing is created.

Deliberate contract tightening — silent-ignore -> explicit reject. The
frontend was verified clean before this was flipped (exactly 13 known fields,
built field by field, no spread), so no real client is broken by it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.tests.conftest import TestingSessionLocal
from backend.app.models.commerce import Order


def _in_stock_sku(client: TestClient) -> int:
    prods = client.get("/api/v1/catalog/products").json()
    items = prods if isinstance(prods, list) else prods.get("items", [])
    detail = client.get(f"/api/v1/catalog/products/{items[0]['slug']}").json()
    return next(s for s in detail["skus"] if s.get("is_in_stock"))["id"]


def _body(**overrides) -> dict:
    body = {
        "payment_method": "cod",
        "fulfillment_type": "delivery",
        "recipient_name": "Hardened Shopper",
        "phone": "+971501234567",
        "address_line": "12 Al Wasl Road",
        "city": "Dubai",
        "country": "AE",
        "shipping_method": "standard",
        "guest_email": "hardened@confit-test.dev",
    }
    body.update(overrides)
    return body


@pytest.mark.parametrize(
    "field,value",
    [
        ("total", 0.01),
        ("total_amount", 0.01),
        ("subtotal", 0.01),
        ("discount_amount", 9999),
        ("tax_amount", 0.0),
        ("shipping_amount", 0.0),
        ("currency", "XYZ"),
        ("payment_status", "paid"),
        ("made_up_field", "anything"),
    ],
)
def test_unknown_or_monetary_fields_are_rejected(client: TestClient, field, value):
    """422, not 200-and-shrug."""
    h = {"X-Session-Token": f"tamper_{field}"}
    client.post("/api/v1/commerce/cart/items", headers=h,
                json={"product_sku_id": _in_stock_sku(client), "quantity": 1})

    db = TestingSessionLocal()
    before = db.query(Order).count()
    db.close()

    r = client.post("/api/v1/commerce/checkout", headers=h, json=_body(**{field: value}))
    assert r.status_code == 422, (
        f"checkout accepted a client-supplied '{field}' with {r.status_code} "
        f"— it must be rejected, not silently ignored: {r.text[:200]}"
    )

    db = TestingSessionLocal()
    assert db.query(Order).count() == before, f"a rejected '{field}' still created an order"
    db.close()


def test_rejection_names_the_offending_field(client: TestClient):
    """An honest error must be actionable, not a bare 422."""
    h = {"X-Session-Token": "tamper_named"}
    client.post("/api/v1/commerce/cart/items", headers=h,
                json={"product_sku_id": _in_stock_sku(client), "quantity": 1})
    r = client.post("/api/v1/commerce/checkout", headers=h, json=_body(total=0.01))
    assert r.status_code == 422
    assert "total" in r.text, f"the error must name the offending field: {r.text[:300]}"


def test_valid_payload_still_succeeds_after_tightening(client: TestClient):
    """The 13 real fields must keep working — this is not a lockout."""
    h = {"X-Session-Token": "tamper_valid_still_works"}
    client.post("/api/v1/commerce/cart/items", headers=h,
                json={"product_sku_id": _in_stock_sku(client), "quantity": 1})
    r = client.post("/api/v1/commerce/checkout", headers=h, json=_body())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["order_number"]
    # Money is still authoritative and still server-computed.
    assert body["total_amount"] == pytest.approx(
        body["subtotal_amount"] - body["discount_amount"]
        + body["tax_amount"] + body["shipping_amount"],
        abs=0.01,
    )
