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


# ---------------------------------------------------------------------------
# Idempotency-key ownership (2026-09-22)
#
# `orders.idempotency_key` is UNIQUE table-wide and the replay lookup was
# global, with no ownership assertion on the returned order. GET
# /orders/{n} DOES assert ownership (`assert_order_access`); the replay path
# did not, so a caller who sent another shopper's key received that shopper's
# order. These tests hold the replay path to the rule the rest of commerce
# already follows. Legitimate same-caller replay above must keep working.
# ---------------------------------------------------------------------------


def _register_shopper(client: TestClient, email: str) -> dict:
    """A fresh account, so the test owns both sides of any cross-account call."""
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": "Idem Owner"},
    )
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Password123!"}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _fill_cart(client: TestClient, headers: dict) -> None:
    """One in-stock SKU into the cart identified by `headers` (201 Created)."""
    sku = client.get("/api/v1/catalog/products").json()[0]
    detail = client.get(f"/api/v1/catalog/products/{sku['id']}").json()
    in_stock = next(s for s in detail["skus"] if s["is_in_stock"])
    added = client.post(
        "/api/v1/commerce/cart/items",
        json={"product_sku_id": in_stock["id"], "quantity": 1},
        headers=headers,
    )
    assert added.status_code in (200, 201), added.text


def _place_order(client: TestClient, headers: dict, key: str, session: str) -> dict:
    h = {**headers, "X-Session-Token": session}
    _fill_cart(client, h)
    csrf = client.cookies.get("confit_csrf")
    if csrf:
        h = {**h, "X-CSRF-Token": csrf}
    placed = client.post(
        "/api/v1/commerce/checkout",
        json={
            "payment_method": "cod",
            "fulfillment_type": "delivery",
            "idempotency_key": key,
            "recipient_name": "Idem Owner",
            "phone": "+971500000123",
            "address_line": "1 Test Road",
            "city": "Dubai",
            "country": "AE",
        },
        headers=h,
    )
    assert placed.status_code == 200, placed.text
    return placed.json()


def test_idempotency_key_does_not_disclose_another_shoppers_order(
    client: TestClient,
) -> None:
    """Account B must not receive account A's order by sending A's key."""
    owner = _register_shopper(client, "idem.owner@confit-test.dev")
    intruder = _register_shopper(client, "idem.intruder@confit-test.dev")

    # A places a real order and the key is spent.
    victim_order = _place_order(client, owner, "key-owned-by-a", "sess_idem_a")
    assert victim_order["order_number"]

    # B replays it. Same key, different account.
    response = client.post(
        "/api/v1/commerce/checkout",
        json={
            "payment_method": "cod",
            "fulfillment_type": "delivery",
            "idempotency_key": "key-owned-by-a",
            "recipient_name": "Intruder",
            "phone": "+971500000999",
            "address_line": "9 Other Road",
            "city": "Abu Dhabi",
            "country": "AE",
        },
        headers={**intruder, "X-Session-Token": "sess_idem_b"},
    )
    assert response.status_code == 409, (
        "a spent key belonging to another shopper must not replay their order: "
        + response.text
    )
    assert response.json().get("error", {}).get("code") == "IDEMPOTENCY_KEY_CONFLICT"
    # The refusal must not leak the order, or even confirm it exists.
    assert victim_order["order_number"] not in response.text
    assert "+971500000123" not in response.text
    assert "1 Test Road" not in response.text


def test_guest_idempotency_key_does_not_cross_guest_sessions(client: TestClient) -> None:
    """A guest key is scoped to the guest session that spent it."""
    email = "idem.guest@confit-test.dev"
    _fill_cart(client, {"X-Session-Token": "sess_idem_guest_1"})
    first = client.post(
        "/api/v1/commerce/checkout",
        json={
            "payment_method": "cod",
            "fulfillment_type": "delivery",
            "guest_email": email,
            "idempotency_key": "guest-owned-key",
            "recipient_name": "Guest One",
            "phone": "+971500000111",
            "address_line": "1 Guest Road",
            "city": "Dubai",
            "country": "AE",
        },
        headers={"X-Session-Token": "sess_idem_guest_1"},
    )
    assert first.status_code == 200, first.text
    order_number = first.json()["order_number"]

    # A DIFFERENT guest session sends the same key.
    crossed = client.post(
        "/api/v1/commerce/checkout",
        json={
            "payment_method": "cod",
            "fulfillment_type": "delivery",
            "guest_email": "someone.else@confit-test.dev",
            "idempotency_key": "guest-owned-key",
            "recipient_name": "Guest Two",
            "phone": "+971500000222",
            "address_line": "2 Guest Road",
            "city": "Dubai",
            "country": "AE",
        },
        headers={"X-Session-Token": "sess_idem_guest_2"},
    )
    assert crossed.status_code == 409, crossed.text
    assert order_number not in crossed.text

    # The ORIGINAL session still replays its own order (no over-blocking).
    replay = client.post(
        "/api/v1/commerce/checkout",
        json={
            "payment_method": "cod",
            "fulfillment_type": "delivery",
            "guest_email": email,
            "idempotency_key": "guest-owned-key",
            "recipient_name": "Guest One",
            "phone": "+971500000111",
            "address_line": "1 Guest Road",
            "city": "Dubai",
            "country": "AE",
        },
        headers={"X-Session-Token": "sess_idem_guest_1"},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["order_number"] == order_number


def test_signed_in_shopper_cannot_replay_a_guest_orders_key(client: TestClient) -> None:
    """Boundary: an account never inherits a guest order by knowing its key."""
    _fill_cart(client, {"X-Session-Token": "sess_boundary_guest"})
    guest = client.post(
        "/api/v1/commerce/checkout",
        json={
            "payment_method": "cod",
            "fulfillment_type": "delivery",
            "guest_email": "boundary.guest@confit-test.dev",
            "idempotency_key": "boundary-guest-key",
            "recipient_name": "Boundary Guest",
            "phone": "+971500000333",
            "address_line": "3 Boundary Road",
            "city": "Dubai",
            "country": "AE",
        },
        headers={"X-Session-Token": "sess_boundary_guest"},
    )
    assert guest.status_code == 200, guest.text

    shopper = _register_shopper(client, "boundary.shopper@confit-test.dev")
    attempt = client.post(
        "/api/v1/commerce/checkout",
        json={
            "payment_method": "cod",
            "fulfillment_type": "delivery",
            "idempotency_key": "boundary-guest-key",
            "recipient_name": "Boundary Shopper",
            "phone": "+971500000444",
            "address_line": "4 Boundary Road",
            "city": "Dubai",
            "country": "AE",
        },
        headers={**shopper, "X-Session-Token": "sess_boundary_shopper"},
    )
    assert attempt.status_code == 409, attempt.text
    assert guest.json()["order_number"] not in attempt.text


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


def test_concurrent_key_race_does_not_disclose_another_shoppers_order(
    client: TestClient, monkeypatch
) -> None:
    """The IntegrityError branch is the SECOND way a spent key is discovered.

    Two shoppers can both pass the pre-flight replay check and then race on the
    UNIQUE constraint; the loser lands in the `except IntegrityError` handler,
    which returned the matching order just as unconditionally as the pre-flight
    path did.

    Reproducing that needs the exact interleaving, so the lookup is scripted:
    the FIRST call (pre-flight) sees nothing, the insert then loses the race,
    and the SECOND call (inside the handler) sees the winner's committed row.
    A first attempt at this test simply posted a duplicate key and asserted 409
    — which the PRE-FLIGHT path raises on its own, so it passed against the
    unguarded handler too and proved nothing (mutation M23 survived). `calls`
    is asserted below so the test cannot silently stop reaching the branch it
    is named after.
    """
    import sqlalchemy
    from backend.app.repositories.commerce_repository import CommerceRepository

    owner = _register_shopper(client, "race.owner@confit-test.dev")
    victim_order = _place_order(client, owner, "key-raced", "sess_race_a")

    intruder = _register_shopper(client, "race.intruder@confit-test.dev")
    _fill_cart(client, {**intruder, "X-Session-Token": "sess_race_b"})

    real_lookup = CommerceRepository.get_order_by_idempotency
    real_create_order = CommerceRepository.create_order
    calls = {"n": 0}

    def _racing_lookup(self, key):
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # pre-flight: the winner has not committed yet
        return real_lookup(self, key)  # handler: the winner's row is now visible

    def _lose_the_race(self, *args, **kwargs):
        raise sqlalchemy.exc.IntegrityError("stmt", {}, Exception("duplicate key"))

    monkeypatch.setattr(CommerceRepository, "get_order_by_idempotency", _racing_lookup)
    monkeypatch.setattr(CommerceRepository, "create_order", _lose_the_race)

    raced = client.post(
        "/api/v1/commerce/checkout",
        json={
            "payment_method": "cod",
            "fulfillment_type": "delivery",
            "idempotency_key": "key-raced",
            "recipient_name": "Racer",
            "phone": "+971500000777",
            "address_line": "7 Race Road",
            "city": "Dubai",
            "country": "AE",
        },
        headers={**intruder, "X-Session-Token": "sess_race_b"},
    )

    assert calls["n"] >= 2, (
        "the race handler was never reached — the assertions below would be "
        "vacuous (this is what let mutation M23 survive the first draft)"
    )
    assert raced.status_code == 409, (
        "the IntegrityError branch must not hand over the order that won the race: "
        + raced.text
    )
    assert victim_order["order_number"] not in raced.text
    assert "+971500000123" not in raced.text
