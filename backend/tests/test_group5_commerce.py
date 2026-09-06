"""Group 5 commerce, payments, and fulfillment — domain and API contracts.

External PSPs are not called. PAYMENTS_LIVE defaults to false and the demo
adapter is an explicit non-live path. These tests exercise real service and
repository logic against the seeded catalog.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.tests.conftest import TestingSessionLocal
from backend.app.models.commerce import Order


def _login(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "shopper@confit.io", "password": "Password123!"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _empty_cart(client: TestClient, headers: dict) -> None:
    cart = client.get("/api/v1/commerce/cart", headers=headers).json()
    for item in list(cart.get("items") or []):
        client.delete(f"/api/v1/commerce/cart/items/{item['id']}", headers=headers)


def _auth(client: TestClient, session: str = "g5_sess") -> dict:
    return {
        "Authorization": f"Bearer {_login(client)}",
        "X-Session-Token": session,
    }


def _first_product_and_sku(client: TestClient):
    products = client.get("/api/v1/catalog/products").json()
    assert products
    detail = client.get(f"/api/v1/catalog/products/{products[0]['id']}").json()
    sku = next(s for s in detail["skus"] if s["is_in_stock"])
    return products[0], sku, detail


def test_product_detail_does_not_invent_fit_or_style_scores(client: TestClient) -> None:
    products = client.get("/api/v1/catalog/products").json()
    assert products
    detail = client.get(f"/api/v1/catalog/products/{products[0]['id']}").json()
    assert detail.get("ai_fit_score") is None
    assert detail.get("style_compatibility_score") is None
    assert detail.get("fit_available") is False
    assert isinstance(detail.get("related_outfits"), list)
    bnpl = detail.get("bnpl") or {}
    assert (bnpl.get("provider") or "").lower() in {"tabby", "tamara", "afterpay", "klarna", "klarna"}


def test_product_detail_fit_uses_usp_when_authenticated(client: TestClient) -> None:
    headers = {"Authorization": f"Bearer {_login(client)}"}
    products = client.get("/api/v1/catalog/products").json()
    detail = client.get(
        f"/api/v1/catalog/products/{products[0]['id']}", headers=headers
    ).json()
    if detail.get("ai_fit_score") is not None:
        assert detail["ai_fit_score"] not in {94, 95}
        assert 40 <= detail["ai_fit_score"] <= 99
        assert detail.get("recommended_size")
        assert detail.get("fit_available") is True


def test_multi_brand_cart_and_server_promo(client: TestClient) -> None:
    headers = _auth(client, "g5_multi_brand")
    _empty_cart(client, headers)
    listing = client.get("/api/v1/catalog/products").json()
    brands = {item["brand_name"] for item in listing}
    assert len(brands) >= 2
    first = listing[0]
    second = next(item for item in listing if item["brand_name"] != first["brand_name"])
    sku_a = client.get(f"/api/v1/catalog/products/{first['id']}").json()["skus"][0]
    sku_b = client.get(f"/api/v1/catalog/products/{second['id']}").json()["skus"][0]

    add_a = client.post(
        "/api/v1/commerce/cart/items",
        json={"product_sku_id": sku_a["id"], "quantity": 1},
        headers=headers,
    )
    add_b = client.post(
        "/api/v1/commerce/cart/items",
        json={"product_sku_id": sku_b["id"], "quantity": 1},
        headers=headers,
    )
    assert add_a.status_code in {200, 201}, add_a.text
    assert add_b.status_code in {200, 201}, add_b.text
    cart = client.get("/api/v1/commerce/cart", headers=headers).json()
    cart_brands = {item["brand_name"] for item in cart["items"]}
    assert len(cart_brands) >= 2
    assert cart["fit_summary"]
    assert all("size_confirmed" in row and "size" in row for row in cart["fit_summary"])

    applied = client.post(
        "/api/v1/commerce/cart/promo",
        json={"promo_code": "CONFIT10"},
        headers=headers,
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["discount_amount"] > 0
    assert applied.json()["promo_code"] == "CONFIT10"

    bogus = client.post(
        "/api/v1/commerce/cart/promo",
        json={"promo_code": "NOTREAL"},
        headers=headers,
    )
    assert bogus.status_code == 422


def test_cart_item_idor_blocked(client: TestClient) -> None:
    headers = _auth(client, "g5_idor")
    _empty_cart(client, headers)
    _, sku, _ = _first_product_and_sku(client)
    client.post(
        "/api/v1/commerce/cart/items",
        json={"product_sku_id": sku["id"], "quantity": 1},
        headers=headers,
    )
    foreign = client.put(
        "/api/v1/commerce/cart/items/999999",
        json={"quantity": 2},
        headers=headers,
    )
    assert foreign.status_code == 404


def test_guest_checkout_requires_email_then_succeeds(client: TestClient) -> None:
    headers = {"X-Session-Token": "g5_guest_cod"}
    _, sku, _ = _first_product_and_sku(client)
    added = client.post(
        "/api/v1/commerce/cart/items",
        json={"product_sku_id": sku["id"], "quantity": 1},
        headers=headers,
    )
    assert added.status_code in {200, 201}, added.text

    denied = client.post(
        "/api/v1/commerce/checkout",
        headers=headers,
        json={
            "payment_method": "cod",
            "fulfillment_type": "delivery",
            "recipient_name": "Guest Shopper",
            "phone": "+971500000000",
            "address_line": "1 Corniche",
            "city": "Abu Dhabi",
            "country": "AE",
        },
    )
    assert denied.status_code == 401

    created = client.post(
        "/api/v1/commerce/checkout",
        headers=headers,
        json={
            "payment_method": "cod",
            "fulfillment_type": "delivery",
            "guest_email": "guest.checkout@example.com",
            "idempotency_key": "guest-cod-1",
            "recipient_name": "Guest Shopper",
            "phone": "+971500000000",
            "address_line": "1 Corniche",
            "city": "Abu Dhabi",
            "country": "AE",
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["order_number"].startswith("CONF-")
    assert body["payment_status"] == "pending"
    # PAY-01: COD fulfilment starts immediately (status 'processing'); the cash
    # settles only at handover (payment_status flips to 'paid' at picked_up/
    # delivered — see test_pay01_fulfillment_gate.py).
    assert body["status"] in {"payment_pending", "pending", "placed", "processing"}
    assert body["guest_email"] == "guest.checkout@example.com"
    assert body.get("payment_mode") == "demo"


def test_checkout_idempotency_returns_same_order(client: TestClient) -> None:
    headers = _auth(client, "g5_idem")
    _empty_cart(client, headers)
    products = client.get("/api/v1/catalog/products").json()
    sku = client.get(f"/api/v1/catalog/products/{products[1]['id']}").json()["skus"][0]
    client.post(
        "/api/v1/commerce/cart/items",
        json={"product_sku_id": sku["id"], "quantity": 1},
        headers=headers,
    )
    payload = {
        "payment_method": "card",
        "fulfillment_type": "delivery",
        "idempotency_key": "shopper-card-once",
        "recipient_name": "Lina Rahman",
        "phone": "+971501234567",
        "address_line": "12 Al Wasl Road",
        "city": "Dubai",
        "country": "AE",
    }
    first = client.post("/api/v1/commerce/checkout", json=payload, headers=headers)
    second = client.post("/api/v1/commerce/checkout", json=payload, headers=headers)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["order_number"] == second.json()["order_number"]


def test_client_cannot_set_paid_or_override_totals(client: TestClient) -> None:
    headers = _auth(client, "g5_totals")
    _empty_cart(client, headers)
    products = client.get("/api/v1/catalog/products").json()
    sku = client.get(f"/api/v1/catalog/products/{products[2]['id']}").json()["skus"][0]
    client.post(
        "/api/v1/commerce/cart/items",
        json={"product_sku_id": sku["id"], "quantity": 1},
        headers=headers,
    )
    created = client.post(
        "/api/v1/commerce/checkout",
        json={
            "payment_method": "cod",
            "fulfillment_type": "delivery",
            "recipient_name": "Lina Rahman",
            "phone": "+971501234567",
            "address_line": "12 Al Wasl Road",
            "city": "Dubai",
            "country": "AE",
            "total": 0.01,
            "discount_amount": 9999,
        },
        headers=headers,
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["payment_status"] != "paid"
    assert body["total_amount"] > 1.0
    assert body["discount_amount"] < 9999


def test_return_get_is_not_hardcoded_and_ineligible_is_rejected(client: TestClient) -> None:
    headers = _auth(client, "g5_return")
    _empty_cart(client, headers)
    missing = client.get("/api/v1/returns/999999", headers=headers)
    assert missing.status_code == 404
    assert "ret-" not in missing.text.lower()

    products = client.get("/api/v1/catalog/products").json()
    sku = client.get(f"/api/v1/catalog/products/{products[3]['id']}").json()["skus"][0]
    client.post(
        "/api/v1/commerce/cart/items",
        json={"product_sku_id": sku["id"], "quantity": 1},
        headers=headers,
    )
    order = client.post(
        "/api/v1/commerce/checkout",
        json={
            "payment_method": "card",
            "fulfillment_type": "delivery",
            "recipient_name": "Lina Rahman",
            "phone": "+971501234567",
            "address_line": "12 Al Wasl Road",
            "city": "Dubai",
            "country": "AE",
        },
        headers=headers,
    ).json()
    attempted = client.post(
        "/api/v1/commerce/returns",
        json={
            "order_id": order["id"],
            "reason": "Changed Mind",
            "item_ids": [order["items"][0]["id"]],
        },
        headers=headers,
    )
    assert attempted.status_code in {400, 409, 422}

    db = TestingSessionLocal()
    try:
        row = db.query(Order).filter(Order.id == order["id"]).first()
        assert row is not None
        row.status = "delivered"
        db.commit()
    finally:
        db.close()

    created = client.post(
        "/api/v1/commerce/returns",
        json={
            "order_id": order["id"],
            "reason": "Changed Mind",
            "item_ids": [order["items"][0]["id"]],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["return_number"].startswith("RET-")
    assert "/api/v1/returns/labels/" in body["return_label_url"]
    fetched = client.get(f"/api/v1/returns/{body['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


def test_webhook_rejects_unverified_signature(client: TestClient) -> None:
    response = client.post(
        "/api/v1/payments/webhooks/stripe",
        content=b'{"id":"evt_x","type":"payment_intent.succeeded"}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 401


def test_bopis_checkout_uses_real_store_and_no_fake_tracking(client: TestClient) -> None:
    headers = _auth(client, "g5_bopis")
    _empty_cart(client, headers)
    _, sku, _ = _first_product_and_sku(client)
    stores = client.get(f"/api/v1/catalog/skus/{sku['id']}/stores").json()
    assert stores
    store_id = stores[0]["store_id"]
    client.post(
        "/api/v1/commerce/cart/items",
        json={"product_sku_id": sku["id"], "quantity": 1},
        headers=headers,
    )
    created = client.post(
        "/api/v1/commerce/checkout",
        json={
            "payment_method": "card",
            "fulfillment_type": "bopis",
            "bopis_store_id": store_id,
            "recipient_name": "Lina Rahman",
            "phone": "+971501234567",
            "city": "Dubai",
            "country": "AE",
        },
        headers=headers,
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["fulfillment_type"] == "bopis"
    assert body.get("fulfillment_groups")
    assert body.get("bopis_pickup_code", "").startswith("PICKUP-")
    tracking = client.get(
        f"/api/v1/commerce/orders/{body['order_number']}/tracking"
    ).json()
    assert tracking["carrier"] in (None, "")
    assert tracking.get("tracking_number") in (None, "")
    assert "confit express" not in (tracking.get("carrier") or "").lower()
    assert tracking["bopis_store_info"]
    assert tracking["bopis_store_info"]["pickup_code"] == body["bopis_pickup_code"]


def test_tracking_does_not_invent_carrier_milestones(client: TestClient) -> None:
    headers = _auth(client, "g5_track")
    _empty_cart(client, headers)
    products = client.get("/api/v1/catalog/products").json()
    sku = client.get(f"/api/v1/catalog/products/{products[4]['id']}").json()["skus"][0]
    client.post(
        "/api/v1/commerce/cart/items",
        json={"product_sku_id": sku["id"], "quantity": 1},
        headers=headers,
    )
    order = client.post(
        "/api/v1/commerce/checkout",
        json={
            "payment_method": "bnpl_tabby",
            "fulfillment_type": "delivery",
            "recipient_name": "Lina Rahman",
            "phone": "+971501234567",
            "address_line": "12 Al Wasl Road",
            "city": "Dubai",
            "country": "AE",
        },
        headers=headers,
    ).json()
    track = client.get(f"/api/v1/commerce/orders/{order['order_number']}/tracking").json()
    assert len(track["timeline"]) > 0
    assert track["current_status"] in {"placed", "processing", "payment_pending"}
    completed = [m for m in track["timeline"] if m["is_completed"]]
    # A just-placed order must not pretent to be delivered.
    delivered = next(m for m in track["timeline"] if m["status_key"] == "delivered")
    assert delivered["is_completed"] is False
    assert completed  # at least "placed" from the order event
