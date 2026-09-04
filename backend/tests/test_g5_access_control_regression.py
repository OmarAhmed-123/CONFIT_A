"""Group 5 access-control regression tests.

Two broken-access-control defects were found (Root cause: the commerce
controllers exposed order/secondary resources without the ownership check that
the sibling routes enforce, so an authenticated user could read another
customer's data by guessing/observing a resource identifier):

1. ``GET /commerce/orders/{order_number}/tracking`` had no authorization check,
   while the sibling ``GET /commerce/orders/{order_number}`` route enforced
   ``assert_order_access``. Any authenticated user could read another
   customer's fulfilment/tracking details (pickup code, store address,
   shipment info) with no check.

2. ``GET /checkout/sessions/{token}`` guest branch was a no-op (``pass``), so a
   guest could read a checkout session that was created under a *different*
   guest session token. The confirm path had the same root-cause class.

These tests are written against the *secure* contract: an authenticated user
must be denied cross-customer access (403), while the owner and the guest
capability path (unguessable order number for anonymous guests) keep working.
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def _register(client: TestClient, email: str, full_name: str) -> str:
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": full_name},
    )
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


def _login(client: TestClient, email: str) -> str:
    r = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _headers(auth_token: str, session_token: str) -> dict:
    """Build auth/session headers. Session token is passed as a variable so the
    test source never hardcodes a high-entropy literal next to a token key (the
    gitleaks generic-api-key scanner must not flag a test fixture as a secret)."""
    return {
        "Authorization": f"Bearer {auth_token}",
        "X-Session-Token": session_token,
    }


def _guest_headers(session_token: str) -> dict:
    return {"X-Session-Token": session_token}


def _empty_cart(client: TestClient, headers: dict) -> None:
    cart = client.get("/api/v1/commerce/cart", headers=headers).json()
    for item in list(cart.get("items") or []):
        client.delete(f"/api/v1/commerce/cart/items/{item['id']}", headers=headers)


def _first_in_stock_sku(client: TestClient) -> dict:
    products = client.get("/api/v1/catalog/products").json()
    assert products, "seeded catalog is empty"
    detail = client.get(f"/api/v1/catalog/products/{products[0]['id']}").json()
    return next(s for s in detail["skus"] if s["is_in_stock"])


def _checkout_one_item(client: TestClient, headers: dict) -> dict:
    _empty_cart(client, headers)
    sku = _first_in_stock_sku(client)
    added = client.post(
        "/api/v1/commerce/cart/items",
        json={"product_sku_id": sku["id"], "quantity": 1},
        headers=headers,
    )
    assert added.status_code in {200, 201}, added.text
    r = client.post(
        "/api/v1/commerce/checkout",
        headers=headers,
        json={
            "payment_method": "card",
            "fulfillment_type": "delivery",
            "recipient_name": "Test Buyer",
            "phone": "+971500000000",
            "address_line": "1 Corniche",
            "city": "Dubai",
            "country": "AE",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_order_tracking_blocks_cross_user_access(client: TestClient) -> None:
    owner = _login(client, "shopper@confit.io")
    owner_h = _headers(owner, "g5ac_owner")
    order = _checkout_one_item(client, owner_h)
    order_number = order["order_number"]

    # The owner can read their own tracking.
    ok = client.get(
        f"/api/v1/commerce/orders/{order_number}/tracking", headers=owner_h
    )
    assert ok.status_code == 200, ok.text

    # An anonymous guest with the (unguessable) order number is still allowed —
    # this is the intended capability model, and it must not regress.
    guest = client.get(f"/api/v1/commerce/orders/{order_number}/tracking")
    assert guest.status_code == 200, guest.text

    # A *different* authenticated consumer must be denied.
    intruder_email = f"g5ac_intruder_{uuid.uuid4().hex[:6]}@confit.io"
    intruder_token = _register(client, intruder_email, "Intruder Buyer")
    intruder_h = _headers(intruder_token, "g5ac_intruder_session")
    denied = client.get(
        f"/api/v1/commerce/orders/{order_number}/tracking", headers=intruder_h
    )
    assert denied.status_code == 403, denied.text


def test_checkout_session_guest_ownership_enforced(client: TestClient) -> None:
    session_token = f"g5ac_cs_guest_{uuid.uuid4().hex[:6]}"
    headers = _guest_headers(session_token)
    sku = _first_in_stock_sku(client)
    added = client.post(
        "/api/v1/commerce/cart/items",
        json={"product_sku_id": sku["id"], "quantity": 1},
        headers=headers,
    )
    assert added.status_code in {200, 201}, added.text

    created = client.post(
        "/api/v1/checkout/sessions",
        headers=headers,
        json={
            "payment_method": "card",
            "fulfillment_type": "delivery",
            "guest_email": f"g5ac_cs_{uuid.uuid4().hex[:6]}@example.com",
            "recipient_name": "Guest Buyer",
            "phone": "+971500000000",
            "address_line": "1 Corniche",
            "city": "Dubai",
            "country": "AE",
        },
    )
    assert created.status_code == 200, created.text
    checkout_token = created.json()["checkout_token"]

    # The owner (matching guest session token) can read it.
    ok = client.get(
        f"/api/v1/checkout/sessions/{checkout_token}", headers=headers
    )
    assert ok.status_code == 200, ok.text

    # A *different* guest session token must be denied.
    other_headers = _guest_headers(f"{session_token}_OTHER")
    denied = client.get(
        f"/api/v1/checkout/sessions/{checkout_token}", headers=other_headers
    )
    assert denied.status_code == 403, denied.text


def test_checkout_session_confirm_guest_ownership_enforced(client: TestClient) -> None:
    session_token = f"g5ac_confirm_{uuid.uuid4().hex[:6]}"
    headers = _guest_headers(session_token)
    sku = _first_in_stock_sku(client)
    added = client.post(
        "/api/v1/commerce/cart/items",
        json={"product_sku_id": sku["id"], "quantity": 1},
        headers=headers,
    )
    assert added.status_code in {200, 201}, added.text

    created = client.post(
        "/api/v1/checkout/sessions",
        headers=headers,
        json={
            "payment_method": "cod",
            "fulfillment_type": "delivery",
            "guest_email": f"g5ac_conf_{uuid.uuid4().hex[:6]}@example.com",
            "recipient_name": "Guest Buyer",
            "phone": "+971500000000",
            "address_line": "1 Corniche",
            "city": "Dubai",
            "country": "AE",
        },
    )
    assert created.status_code == 200, created.text
    checkout_token = created.json()["checkout_token"]

    confirm_payload = {
        "payment_method": "cod",
        "fulfillment_type": "delivery",
        "guest_email": "g5ac_conf@example.com",
        "recipient_name": "Guest Buyer",
        "phone": "+971500000000",
        "address_line": "1 Corniche",
        "city": "Dubai",
        "country": "AE",
    }

    # A mismatched guest session token must be denied (session stays active).
    other_headers = _guest_headers(f"{session_token}_OTHER")
    denied = client.post(
        f"/api/v1/checkout/sessions/{checkout_token}/confirm",
        headers=other_headers,
        json=confirm_payload,
    )
    assert denied.status_code == 403, denied.text

    # The owner (matching session token) may confirm.
    ok = client.post(
        f"/api/v1/checkout/sessions/{checkout_token}/confirm",
        headers=headers,
        json=confirm_payload,
    )
    assert ok.status_code == 200, ok.text
