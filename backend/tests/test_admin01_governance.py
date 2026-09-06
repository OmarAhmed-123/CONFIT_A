"""ADMIN-01 governance gates: full audit rows (actor/action/resource/before/
after/request_id), negative RBAC on admin mutations, step-up re-auth policy.

Why: `transition_order` spent its life as dead unguarded code — the exact
class of invisible admin power this item closes. These tests pin, at the API
level, that state-changing admin actions are (a) unreachable without the
admin role, (b) unreachable with a stale admin token (re-auth policy), and
(c) always accompanied by a complete audit row correlated to the request id
returned in the X-Request-Id response header.
"""
import itertools
import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.main import app


def _login(client: TestClient, email: str, password: str = "Password123!") -> str:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


_SEQ = itertools.count(1)


def _card_order(client: TestClient) -> dict:
    headers = {"Authorization": f"Bearer {_login(client, 'shopper@confit.io')}",
               "X-Session-Token": f"adm01-cart-{next(_SEQ)}"}
    cart = client.get("/api/v1/commerce/cart", headers=headers).json()
    for item in list(cart.get("items") or []):
        client.delete(f"/api/v1/commerce/cart/items/{item['id']}", headers=headers)
    products = client.get("/api/v1/catalog/products").json()
    sku = client.get(f"/api/v1/catalog/products/{products[0]['id']}").json()["skus"][0]
    client.post("/api/v1/commerce/cart/items", json={"product_sku_id": sku["id"], "quantity": 1}, headers=headers)
    r = client.post("/api/v1/commerce/checkout", json={
        "payment_method": "card",
        "fulfillment_type": "delivery",
        "idempotency_key": "adm01-card-1",  # order ids differ per cart session anyway
        "recipient_name": "Gov Probe",
        "phone": "+971501234567",
        "address_line": "9 Audit Way",
        "city": "Dubai",
        "country": "AE",
    }, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_guest_and_consumer_cannot_reach_admin_mutations(client: TestClient) -> None:
    """Negative RBAC, independent requests: no token -> 401; consumer -> 403."""
    order = _card_order(client)
    num = order["order_number"]
    base = "/api/v1/admin/orders"
    # guest: a cookie-free client (the main client carries the consumer's
    # session cookie from login, which would legitimately trip the CSRF guard)
    fresh = TestClient(app)
    r = fresh.post(f"{base}/{num}/transition", json={"new_status": "shipped"})
    assert r.status_code == 401, r.text
    r = fresh.post(f"{base}/{num}/capture-payment")
    assert r.status_code == 401, r.text
    # consumer (valid identity, wrong role)
    consumer = {"Authorization": f"Bearer {_login(client, 'shopper@confit.io')}"}
    r = client.post(f"{base}/{num}/transition", json={"new_status": "shipped"}, headers=consumer)
    assert r.status_code == 403, r.text
    r = client.post(f"{base}/{num}/capture-payment", headers=consumer)
    assert r.status_code == 403, r.text


def test_stale_admin_token_requires_reauth(client: TestClient) -> None:
    """Step-up policy: an admin token issued > 60 min ago must NOT be able to
    mutate orders — 401 ADMIN_REAUTH_REQUIRED until a fresh sign-in."""
    import jwt as pyjwt
    from datetime import datetime, timezone, timedelta

    admin_id = None
    from backend.app.core.database import get_db
    db = next(app.dependency_overrides[get_db]())
    try:
        from backend.app.models.user import User, UserRole
        admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
        admin_id = str(admin.id)
    finally:
        db.close()

    now = datetime.now(timezone.utc)
    stale = pyjwt.encode(
        {
            "sub": admin_id,
            "iat": now - timedelta(hours=2),
            "exp": now + timedelta(minutes=10),
            "type": "access",
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    order = _card_order(client)
    r = client.post(f"/api/v1/admin/orders/{order['order_number']}/transition",
                    json={"new_status": "preparing"},
                    headers={"Authorization": f"Bearer {stale}"})
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "ADMIN_REAUTH_REQUIRED", r.text


def test_admin_transition_audited_with_before_after_and_request_id(client: TestClient) -> None:
    admin = {"Authorization": f"Bearer {_login(client, 'admin@confit.io')}"}
    order = _card_order(client)
    client.post(f"/api/v1/admin/orders/{order['order_number']}/capture-payment", headers=admin)
    r = client.post(f"/api/v1/admin/orders/{order['order_number']}/transition",
                    json={"new_status": "preparing"}, headers=admin)
    assert r.status_code == 200, r.text
    rid = r.headers.get("X-Request-Id")
    assert rid, "every response must carry X-Request-Id"

    from backend.app.core.database import get_db
    from backend.app.models.user import AuditLog
    db = next(app.dependency_overrides[get_db]())
    try:
        row = (
            db.query(AuditLog)
            .filter(AuditLog.action == "ADMIN_ORDER_TRANSITION",
                    AuditLog.resource_id == order["order_number"])
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None, "admin transition must write an audit row"
        assert row.user_id is not None, "actor required"
        assert row.resource_type == "Order"
        import json as _json
        before = _json.loads(row.before_json or "{}")
        after = _json.loads(row.after_json or "{}")
        assert before.get("payment_status") == "paid" and after.get("status") == "preparing"
        assert row.request_id == rid, "audit row must correlate with X-Request-Id"
    finally:
        db.close()


def test_admin_capture_audited(client: TestClient) -> None:
    admin = {"Authorization": f"Bearer {_login(client, 'admin@confit.io')}"}
    order = _card_order(client)
    r = client.post(f"/api/v1/admin/orders/{order['order_number']}/capture-payment", headers=admin)
    assert r.status_code == 200, r.text
    from backend.app.core.database import get_db
    from backend.app.models.user import AuditLog
    db = next(app.dependency_overrides[get_db]())
    try:
        row = (
            db.query(AuditLog)
            .filter(AuditLog.action == "ADMIN_DEMO_CAPTURE",
                    AuditLog.resource_id == order["order_number"])
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None and row.request_id
    finally:
        db.close()


def test_transition_rejects_malformed_body(client: TestClient) -> None:
    admin = {"Authorization": f"Bearer {_login(client, 'admin@confit.io')}"}
    r = client.post("/api/v1/admin/orders/CONF-NOPE/transition", json={}, headers=admin)
    assert r.status_code == 422, r.text
