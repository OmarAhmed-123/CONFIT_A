"""AUDIT-2026-09-06 P0 regression: the returning guest must be able to shop again.

Live evidence that motivated this suite (preview, 2026-09-06): after one
successful guest checkout, every subsequent cart operation for that browser
returned 500 — GET /commerce/cart, POST /commerce/cart/items, and a second
checkout. Root cause: ``carts.session_token`` is UNIQUE + NOT NULL, the
converted cart row kept holding the (client-persisted) token forever, and
``get_or_create_cart`` then tried to INSERT a duplicate token row
(sqlalchemy IntegrityError: UNIQUE constraint failed: carts.session_token).

The fix releases the token when a cart leaves 'active' (deterministic
``<token>::converted::<cart_id>`` rename; the ORIGINAL token stays recorded
on the order via Order.guest_session_token) and makes get_or_create_cart
race-safe against concurrent same-token inserts.
"""

import pytest
from fastapi.testclient import TestClient

SLUG = "goodyear-welted-leather-oxford-shoes"


def _in_stock_sku(client: TestClient) -> int:
    prods = client.get("/api/v1/catalog/products").json()
    items = prods if isinstance(prods, list) else prods.get("items", [])
    slug = next((p["slug"] for p in items if p["slug"] == SLUG), items[0]["slug"])
    detail = client.get(f"/api/v1/catalog/products/{slug}").json()
    sku = next(s for s in detail["skus"] if s.get("is_in_stock"))
    return sku["id"]


def _checkout_body(sku_id: int) -> dict:
    return {
        "payment_method": "card",
        "fulfillment_type": "delivery",
        "recipient_name": "Returning Guest",
        "phone": "+201000000000",
        "address_line": "12 Nile Street",
        "city": "Cairo",
        "country": "UAE",
        "guest_email": "returning.guest@confit-test.dev",
        "shipping_method": "standard",
    }


def test_returning_guest_can_shop_again_after_checkout(client: TestClient):
    """The exact P0 repro: checkout -> same session token -> cart must work."""
    h = {"X-Session-Token": "sess_regress_returning_1"}
    sku = _in_stock_sku(client)

    assert client.post("/api/v1/commerce/cart/items", headers=h,
                       json={"product_sku_id": sku, "quantity": 1}).status_code == 201
    first = client.post("/api/v1/commerce/checkout", headers=h, json=_checkout_body(sku))
    assert first.status_code == 200
    order_no = first.json()["order_number"]

    # BEFORE the fix both of these were 500 (UNIQUE constraint) forever.
    cart_after = client.get("/api/v1/commerce/cart", headers=h)
    assert cart_after.status_code == 200, cart_after.text
    assert cart_after.json()["items_count"] == 0

    re_add = client.post("/api/v1/commerce/cart/items", headers=h,
                         json={"product_sku_id": sku, "quantity": 1})
    assert re_add.status_code == 201, re_add.text

    second = client.post("/api/v1/commerce/checkout", headers=h, json=_checkout_body(sku))
    assert second.status_code == 200, second.text
    assert second.json()["order_number"] != order_no


def test_duplicate_checkout_is_an_honest_422_not_a_500(client: TestClient):
    """Replaying checkout without an idempotency key must degrade to a
    controlled validation error on the (now empty) fresh cart — never an
    unhandled 500."""
    h = {"X-Session-Token": "sess_regress_dup_checkout"}
    sku = _in_stock_sku(client)
    client.post("/api/v1/commerce/cart/items", headers=h,
                json={"product_sku_id": sku, "quantity": 1})
    body = _checkout_body(sku)
    first = client.post("/api/v1/commerce/checkout", headers=h, json=body)
    assert first.status_code == 200
    replay = client.post("/api/v1/commerce/checkout", headers=h, json=body)
    assert replay.status_code == 422, replay.text
    assert "empty" in replay.json()["error"]["message"].lower()


def test_checkout_with_idempotency_key_replays_the_same_order(client: TestClient):
    h = {"X-Session-Token": "sess_regress_idem"}
    sku = _in_stock_sku(client)
    client.post("/api/v1/commerce/cart/items", headers=h,
                json={"product_sku_id": sku, "quantity": 1})
    body = {**_checkout_body(sku), "idempotency_key": "regression-idem-key-1"}
    first = client.post("/api/v1/commerce/checkout", headers=h, json=body)
    assert first.status_code == 200
    client.post("/api/v1/commerce/cart/items", headers=h,
                json={"product_sku_id": sku, "quantity": 1})
    replay = client.post("/api/v1/commerce/checkout", headers=h, json=body)
    assert replay.status_code == 200
    assert replay.json()["order_number"] == first.json()["order_number"]


def test_converted_cart_keeps_traceable_token_and_order_keeps_original(client: TestClient):
    """The rename must stay traceable: converted row prefix = original token,
    and the order row carries the ORIGINAL guest token."""
    from backend.tests.conftest import TestingSessionLocal
    from backend.app.models.commerce import Cart, Order

    h = {"X-Session-Token": "sess_regress_trace_9"}
    sku = _in_stock_sku(client)
    client.post("/api/v1/commerce/cart/items", headers=h,
                json={"product_sku_id": sku, "quantity": 1})
    order = client.post("/api/v1/commerce/checkout", headers=h, json=_checkout_body(sku)).json()

    db = TestingSessionLocal()
    try:
        converted = db.query(Cart).filter(Cart.status == "converted").order_by(Cart.id.desc()).first()
        assert converted is not None
        assert converted.session_token.startswith("sess_regress_trace_9::converted::")
        order_row = db.query(Order).filter(Order.order_number == order["order_number"]).first()
        assert order_row.guest_session_token == "sess_regress_trace_9"
    finally:
        db.close()


def test_token_freed_after_guest_merge_allows_post_logout_guest_cart(client: TestClient):
    """Login-merge converts the guest row too; after logout the same browser
    token must be able to open a fresh guest cart (was a latent 500)."""
    from backend.tests.conftest import TestingSessionLocal
    from backend.app.models.commerce import Cart

    # register a dedicated user so we own both sides of the merge
    email = "merge.then.guest@confit-test.dev"
    client.post("/api/v1/auth/register", json={
        "email": email, "password": "Password123!", "full_name": "Merge Guest"
    })
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    assert login.status_code == 200
    auth = {"Authorization": f"Bearer {login.json()['access_token']}"}

    h = {"X-Session-Token": "sess_regress_merge_5"}
    sku = _in_stock_sku(client)
    client.post("/api/v1/commerce/cart/items", headers=h,
                json={"product_sku_id": sku, "quantity": 1})
    # authenticated POSTs require the CSRF round-trip cookie -> header
    csrf = client.cookies.get("confit_csrf")
    merged = client.post("/api/v1/commerce/cart/merge",
                         headers={**auth, "X-CSRF-Token": csrf},
                         json={"guest_token": "sess_regress_merge_5"})
    assert merged.status_code == 200, merged.text

    # same browser token, now anonymous again (post-logout) -> must be 200
    fresh = client.get("/api/v1/commerce/cart", headers=h)
    assert fresh.status_code == 200, fresh.text
    # the client still carries the login csrf cookie -> header required
    h_post = {**h, "X-CSRF-Token": client.cookies.get("confit_csrf")}
    re_add = client.post("/api/v1/commerce/cart/items", headers=h_post,
                         json={"product_sku_id": sku, "quantity": 1})
    assert re_add.status_code == 201, re_add.text
