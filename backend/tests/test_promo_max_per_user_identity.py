"""``max_per_user`` must cap one natural person, not one login.

Proven live on 5c909d7 with a throwaway probe:

    authed #1 with promo   -> 200 discount=18.0
    guest #2, same email   -> 200 discount=18.0   <- allowance spent twice

``_resolve_promo`` counted redemptions with ``count_redemptions(promo.id,
user_id=user_id)``. Guest orders store ``guest_email`` with ``user_id=None``, so
the guest redemption was invisible to the counter. Worse, the guard read
``if user_id and promo.max_per_user`` — a guest was exempt from ``max_per_user``
entirely and could reuse a code without limit.

Identity now spans both links the schema records (``user_id`` and
``guest_email``), so the allowance follows the person across the sign-in
boundary in both directions.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.tests.conftest import TestingSessionLocal
from backend.tests.commerce_test_isolation import cleanup_orders_fixture
from backend.app.models.commerce import Promotion

# These tests check out DISCOUNTED orders. Leave none behind: a pre-existing
# reporting suite asserts attributed revenue does not exceed total GMV by more
# than 100 (its allowance for discount), which deeply-discounted leftover
# orders would blow through. See commerce_test_isolation for the full why.
_isolate_orders = cleanup_orders_fixture()

OWNER_EMAIL = "shopper@confit.io"
OWNER_PASSWORD = "Password123!"


@pytest.fixture()
def once_promo(request):
    """A one-per-person percent promo, deleted again afterwards."""
    code = f"ONCE_{request.node.name[:14].upper()}"
    db = TestingSessionLocal()
    now = datetime.now(timezone.utc)
    promo = Promotion(
        code=code,
        description="one per person",
        discount_type="percent",
        discount_value=10.0,
        currency="USD",
        is_active=True,
        max_per_user=1,
        starts_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=30),
    )
    db.add(promo)
    db.commit()
    yield code
    db = TestingSessionLocal()
    from backend.app.models.commerce import PromotionRedemption

    row = db.query(Promotion).filter(Promotion.code == code).first()
    if row:
        db.query(PromotionRedemption).filter(PromotionRedemption.promotion_id == row.id).delete()
        db.delete(row)
        db.commit()
    db.close()


def _in_stock_sku(client: TestClient) -> int:
    prods = client.get("/api/v1/catalog/products").json()
    items = prods if isinstance(prods, list) else prods.get("items", [])
    detail = client.get(f"/api/v1/catalog/products/{items[0]['slug']}").json()
    return next(s for s in detail["skus"] if s.get("is_in_stock"))["id"]


def _body(**overrides) -> dict:
    body = {
        "payment_method": "cod",
        "fulfillment_type": "delivery",
        "recipient_name": "Promo Shopper",
        "phone": "+971501234567",
        "address_line": "12 Al Wasl Road",
        "city": "Dubai",
        "country": "AE",
        "shipping_method": "standard",
    }
    body.update(overrides)
    return body


def _authed_headers(client: TestClient, session: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}", "X-Session-Token": session}


def _fill(client: TestClient, headers: dict) -> None:
    sku = _in_stock_sku(client)
    r = client.post(
        "/api/v1/commerce/cart/items",
        headers=headers,
        json={"product_sku_id": sku, "quantity": 1},
    )
    assert r.status_code == 201, r.text


def test_signed_in_user_cannot_reset_allowance_as_guest(client: TestClient, once_promo):
    """The headline bypass: authed redemption, then guest redemption, same person."""
    authed = _authed_headers(client, "promo_ident_authed")
    _fill(client, authed)
    first = client.post(
        "/api/v1/commerce/checkout", headers=authed, json=_body(promo_code=once_promo)
    )
    assert first.status_code == 200, first.text
    assert first.json()["discount_amount"] > 0, "the first redemption must be discounted"

    # Same human, now as a guest under the same email, in a different browser.
    client.cookies.clear()
    guest = {"X-Session-Token": "promo_ident_guest"}
    _fill(client, guest)
    second = client.post(
        "/api/v1/commerce/checkout",
        headers=guest,
        json=_body(promo_code=once_promo, guest_email=OWNER_EMAIL),
    )
    assert second.status_code >= 400, (
        f"max_per_user was reset by checking out as a guest: {second.status_code} "
        f"discount={second.json().get('discount_amount')}"
    )


def test_guest_allowance_is_not_reset_by_signing_in(client: TestClient, once_promo):
    """The same bypass in the other direction: guest first, then signed in."""
    guest = {"X-Session-Token": "promo_ident_guest_first"}
    _fill(client, guest)
    first = client.post(
        "/api/v1/commerce/checkout",
        headers=guest,
        json=_body(promo_code=once_promo, guest_email=OWNER_EMAIL),
    )
    assert first.status_code == 200, first.text
    assert first.json()["discount_amount"] > 0

    client.cookies.clear()
    authed = _authed_headers(client, "promo_ident_authed_second")
    _fill(client, authed)
    second = client.post(
        "/api/v1/commerce/checkout", headers=authed, json=_body(promo_code=once_promo)
    )
    assert second.status_code >= 400, (
        "a guest redemption did not count against the signed-in allowance"
    )


def test_guest_cannot_reuse_a_guest_code_indefinitely(client: TestClient, once_promo):
    """A guest was previously exempt from max_per_user altogether."""
    for attempt in range(2):
        h = {"X-Session-Token": f"promo_ident_repeat_{attempt}"}
        _fill(client, h)
        r = client.post(
            "/api/v1/commerce/checkout",
            headers=h,
            json=_body(promo_code=once_promo, guest_email=OWNER_EMAIL),
        )
        if attempt == 0:
            assert r.status_code == 200, r.text
        else:
            assert r.status_code >= 400, "a guest reused a max_per_user=1 code"


def test_different_people_are_not_blocked(client: TestClient, once_promo):
    """Per-user means per user: a second person must still get the discount."""
    first = {"X-Session-Token": "promo_ident_person_a"}
    _fill(client, first)
    a = client.post(
        "/api/v1/commerce/checkout",
        headers=first,
        json=_body(promo_code=once_promo, guest_email="person.a@confit-test.dev"),
    )
    assert a.status_code == 200 and a.json()["discount_amount"] > 0, a.text

    second = {"X-Session-Token": "promo_ident_person_b"}
    _fill(client, second)
    b = client.post(
        "/api/v1/commerce/checkout",
        headers=second,
        json=_body(promo_code=once_promo, guest_email="person.b@confit-test.dev"),
    )
    assert b.status_code == 200, f"an unrelated shopper was blocked: {b.text}"
    assert b.json()["discount_amount"] > 0


def test_second_code_replaces_rather_than_stacks(client: TestClient):
    """Scope guard: one code per cart. Applying a second replaces the first.

    Multi-code stacking is explicitly out of scope for launch; this asserts the
    existing single-code behaviour is intentional and server-validated, so a
    future 'stacking' feature cannot appear by accident.
    """
    db = TestingSessionLocal()
    now = datetime.now(timezone.utc)
    codes = {}
    for tag, pct in (("A", 10.0), ("B", 25.0)):
        code = f"REPLACE_{tag}"
        db.query(Promotion).filter(Promotion.code == code).delete()
        promo = Promotion(
            code=code,
            description=f"replace {tag}",
            discount_type="percent",
            discount_value=pct,
            currency="USD",
            is_active=True,
            max_per_user=5,
            starts_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=30),
        )
        db.add(promo)
        codes[tag] = code
    db.commit()
    db.close()

    try:
        h = {"X-Session-Token": "promo_replace_cart"}
        _fill(client, h)
        first = client.post(
            "/api/v1/commerce/cart/promo", headers=h, json={"promo_code": codes["A"]}
        )
        assert first.status_code == 200, first.text
        d1 = first.json()["discount_amount"]
        second = client.post(
            "/api/v1/commerce/cart/promo", headers=h, json={"promo_code": codes["B"]}
        )
        assert second.status_code == 200, second.text
        body = second.json()
        assert body["promo_code"] == codes["B"], "the second code must replace the first"
        assert body["discount_amount"] > d1, (
            "discounts stacked instead of replacing — multi-code stacking is out of scope"
        )
    finally:
        db = TestingSessionLocal()
        for code in codes.values():
            row = db.query(Promotion).filter(Promotion.code == code).first()
            if row:
                db.delete(row)
        db.commit()
        db.close()
