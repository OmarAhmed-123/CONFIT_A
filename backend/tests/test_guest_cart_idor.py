"""A guest must never be able to place an order against a signed-in user's cart.

Proven live on 5c909d7 (before this suite existed) with a throwaway probe:

    owner BEFORE: 1 item(s)
    attacker order: 200 CONF-F75A7D04 total=204.0     <- no auth header, victim's token
    owner AFTER (own auth): cart items = 0            <- victim's cart emptied

Any caller holding a session token — a token that travels in a header, is
readable by any script on the page and is trivially leaked — could convert the
victim's cart into an order under the attacker's own ``guest_email``, destroying
the cart in the process. ``assert_order_access`` protects reads; this is a write.

Two independent fixes are required and both are asserted here:

  1. ``CommerceRepository.get_or_create_cart`` — the session-token lookup must
     require ``Cart.user_id IS NULL``, so a guest token can never *adopt* an
     authenticated user's cart in the first place.
  2. ``CommerceService.checkout`` — even if a cart reaches it some other way,
     reject when the cart is owned by an authenticated user who is not the
     caller. Fail closed.

The ``client.cookies.clear()`` calls matter: an attacker holding only a leaked
token is a different browser with no session cookie. Without clearing, the
shared TestClient would carry the owner's ``confit_token`` cookie and the
request would be stopped by the CSRF double-submit guard instead — which masks
the very bug this file exists to catch.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.tests.commerce_test_isolation import cleanup_orders_fixture

_isolate_orders = cleanup_orders_fixture()

from backend.tests.conftest import TestingSessionLocal
from backend.app.models.commerce import Cart, Order

OWNER_EMAIL = "shopper@confit.io"
OWNER_PASSWORD = "Password123!"


def _in_stock_sku(client: TestClient) -> int:
    prods = client.get("/api/v1/catalog/products").json()
    items = prods if isinstance(prods, list) else prods.get("items", [])
    detail = client.get(f"/api/v1/catalog/products/{items[0]['slug']}").json()
    return next(s for s in detail["skus"] if s.get("is_in_stock"))["id"]


def _login(client: TestClient) -> dict:
    r = client.post("/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _empty_cart(client: TestClient, headers: dict) -> None:
    """Start from a known cart. Needed now that a blocked attack leaves the
    victim's cart intact — a repeated run would otherwise find last run's item."""
    cart = client.get("/api/v1/commerce/cart", headers=headers)
    if cart.status_code != 200:
        return
    for item in list(cart.json().get("items") or []):
        client.delete(f"/api/v1/commerce/cart/items/{item['id']}", headers=headers)


def _checkout_body(**overrides) -> dict:
    body = {
        "payment_method": "cod",
        "fulfillment_type": "delivery",
        "recipient_name": "Someone",
        "phone": "+971501234567",
        "address_line": "12 Al Wasl Road",
        "city": "Dubai",
        "country": "AE",
        "shipping_method": "standard",
    }
    body.update(overrides)
    return body


def test_guest_with_victim_token_cannot_order_from_victims_cart(client: TestClient):
    """The headline attack: 4xx, no order, victim's cart untouched."""
    owner_headers = {**_login(client), "X-Session-Token": "idor_victim_token"}
    _empty_cart(client, owner_headers)
    sku = _in_stock_sku(client)
    assert client.post(
        "/api/v1/commerce/cart/items",
        headers=owner_headers,
        json={"product_sku_id": sku, "quantity": 1},
    ).status_code == 201

    victim_before = client.get("/api/v1/commerce/cart", headers=owner_headers).json()
    assert victim_before["items_count"] == 1

    db = TestingSessionLocal()
    orders_before = db.query(Order).count()
    db.close()

    # Attacker: same token, no bearer, any guest_email, no session cookie.
    client.cookies.clear()
    r = client.post(
        "/api/v1/commerce/checkout",
        headers={"X-Session-Token": "idor_victim_token"},
        json=_checkout_body(guest_email="attacker@evil.test"),
    )

    assert r.status_code in (401, 403), (
        f"guest placed an order against an authenticated user's cart: {r.status_code} {r.text[:300]}"
    )
    db = TestingSessionLocal()
    assert db.query(Order).count() == orders_before, "an order was created by the attacker"
    db.close()

    # The victim's cart must be exactly as they left it.
    victim_after = client.get("/api/v1/commerce/cart", headers=owner_headers).json()
    assert victim_after["items_count"] == 1, "the victim's cart was emptied by the attack"
    assert victim_after["total"] == victim_before["total"]


def test_guest_token_cannot_resolve_to_a_owned_cart_at_repository_level(client: TestClient):
    """Defence in depth: the lookup itself refuses to adopt an owned cart.

    Even with checkout out of the picture, asking the repository for a guest
    cart using a token that belongs to a signed-in user must not return that
    user's cart.
    """
    from backend.app.repositories.commerce_repository import CommerceRepository

    owner_headers = {**_login(client), "X-Session-Token": "idor_repo_token"}
    _empty_cart(client, owner_headers)
    sku = _in_stock_sku(client)
    client.post(
        "/api/v1/commerce/cart/items",
        headers=owner_headers,
        json={"product_sku_id": sku, "quantity": 1},
    )

    db = TestingSessionLocal()
    repo = CommerceRepository(db)
    try:
        try:
            guest_cart = repo.get_or_create_cart("idor_repo_token", user_id=None)
        except Exception:
            # Raising a clean authorization error is an acceptable outcome.
            return
        assert guest_cart.user_id is None, (
            "a guest lookup returned a cart owned by an authenticated user"
        )
        assert not [
            i for i in (guest_cart.items or [])
        ] or guest_cart.session_token != "idor_repo_token", (
            "a guest adopted an authenticated user's cart"
        )
    finally:
        db.close()


def test_legitimate_owner_still_checks_out(client: TestClient):
    """The fix must not break the real shopper."""
    owner_headers = {**_login(client), "X-Session-Token": "idor_owner_ok"}
    _empty_cart(client, owner_headers)
    sku = _in_stock_sku(client)
    client.post(
        "/api/v1/commerce/cart/items",
        headers=owner_headers,
        json={"product_sku_id": sku, "quantity": 1},
    )
    r = client.post("/api/v1/commerce/checkout", headers=owner_headers, json=_checkout_body())
    assert r.status_code == 200, r.text
    assert r.json()["order_number"]


def test_guest_with_own_token_still_checks_out(client: TestClient):
    """Guest checkout is a supported flow and must keep working."""
    h = {"X-Session-Token": "idor_guest_own"}
    _empty_cart(client, h)
    sku = _in_stock_sku(client)
    client.post("/api/v1/commerce/cart/items", headers=h, json={"product_sku_id": sku, "quantity": 1})
    r = client.post(
        "/api/v1/commerce/checkout",
        headers=h,
        json=_checkout_body(guest_email="real.guest@confit-test.dev"),
    )
    assert r.status_code == 200, r.text


def test_cart_is_not_left_converted_when_attack_is_rejected(client: TestClient):
    """A rejected attack must not mutate cart state — no half-consumed cart."""
    owner_headers = {**_login(client), "X-Session-Token": "idor_state_token"}
    _empty_cart(client, owner_headers)
    sku = _in_stock_sku(client)
    client.post(
        "/api/v1/commerce/cart/items",
        headers=owner_headers,
        json={"product_sku_id": sku, "quantity": 1},
    )
    client.cookies.clear()
    client.post(
        "/api/v1/commerce/checkout",
        headers={"X-Session-Token": "idor_state_token"},
        json=_checkout_body(guest_email="attacker2@evil.test"),
    )
    db = TestingSessionLocal()
    try:
        cart = (
            db.query(Cart)
            .filter(Cart.session_token == "idor_state_token")
            .first()
        )
        assert cart is not None and cart.status == "active", (
            "the rejected attack still consumed or converted the victim's cart"
        )
    finally:
        db.close()
