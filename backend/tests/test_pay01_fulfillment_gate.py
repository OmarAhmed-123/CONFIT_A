"""PAY-01 code-path gates: order state machine, fulfilment payment gate,
demo capture, COD settlement at handover, webhook idempotency, RBAC.

Why these exist: `transition_order` used to be dead, unguarded service code —
any future caller could walk an UNPAID order to 'shipped' with no payment
check. These tests pin the contract at the API level:

  - fulfilment states require payment_status == 'paid' (or COD, which settles
    at handover) -> FULFILLMENT_PAYMENT_REQUIRED 409 otherwise;
  - ORDER_TRANSITIONS is enforced for admin transitions (invalid jump -> 409);
  - demo capture is explicit + auditable + idempotent, and refuses in live mode;
  - provider webhooks stay idempotent (duplicate event -> duplicate response).

Research anchors: fulfilment only after capture is the standard commerce
checkout contract (Elastic Path checkout/order-processing: fulfilment actions
run after capturePaymentCheckoutAction; SHOPLINE order-status guide: order
enters the fulfilment queue only after payment clears). Webhook duplicate
handling per Stripe webhooks guidance (track event IDs, ack duplicates).
"""
import hashlib
import hmac
import itertools
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


def _login(client: TestClient, email: str, password: str = "Password123!") -> str:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _consumer(client: TestClient, session: str = "pay01") -> dict:
    return {
        "Authorization": f"Bearer {_login(client, 'shopper@confit.io')}",
        "X-Session-Token": session,
    }


def _admin(client: TestClient) -> dict:
    return {"Authorization": f"Bearer {_login(client, 'admin@confit.io')}"}


_CARD_SEQ = itertools.count(1)


def _first_in_stock_sku(client: TestClient) -> dict:
    """First in-stock SKU across the catalogue.

    The full backend suite performs hundreds of real checkouts; a fixed SKU
    can legitimately sell out mid-run, so the probe must pick whatever the
    store actually has (and fail loudly if it truly has nothing).
    """
    products = client.get("/api/v1/catalog/products").json()
    for prod in products:
        detail = client.get(f"/api/v1/catalog/products/{prod['id']}").json()
        for sku in detail.get("skus", []):
            if sku.get("is_in_stock") and (sku.get("stock_level") or 0) > 0:
                return sku
    raise AssertionError("no in-stock SKU available for the payment-gate probe")


def _card_order(client: TestClient) -> dict:
    seq = next(_CARD_SEQ)
    headers = _consumer(client, session=f"pay01-card-{seq}")
    _empty_cart(client, headers)
    sku = _first_in_stock_sku(client)
    added = client.post("/api/v1/commerce/cart/items", json={"product_sku_id": sku["id"], "quantity": 1}, headers=headers)
    assert added.status_code in (200, 201), added.text
    r = client.post("/api/v1/commerce/checkout", json={
        "payment_method": "card",
        "fulfillment_type": "delivery",
        "idempotency_key": f"pay01-card-{seq}",
        "recipient_name": "Pay Gate Probe",
        "phone": "+971501234567",
        "address_line": "1 Gate Street",
        "city": "Dubai",
        "country": "AE",
    }, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _cod_order(client: TestClient, key: str) -> dict:
    headers = _consumer(client, session=f"pay01-cod-{key}")
    _empty_cart(client, headers)
    sku = _first_in_stock_sku(client)
    added = client.post("/api/v1/commerce/cart/items", json={"product_sku_id": sku["id"], "quantity": 1}, headers=headers)
    assert added.status_code in (200, 201), added.text
    r = client.post("/api/v1/commerce/checkout", json={
        "payment_method": "cod",
        "fulfillment_type": "delivery",
        "idempotency_key": key,
        "recipient_name": "COD Probe",
        "phone": "+971501234567",
        "address_line": "2 Handover Street",
        "city": "Dubai",
        "country": "AE",
    }, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _empty_cart(client: TestClient, headers: dict) -> None:
    cart = client.get("/api/v1/commerce/cart", headers=headers).json()
    for item in list(cart.get("items") or []):
        client.delete(f"/api/v1/commerce/cart/items/{item['id']}", headers=headers)


def _transition(client: TestClient, num: str, status: str, headers: dict):
    return client.post(f"/api/v1/admin/orders/{num}/transition", json={"new_status": status}, headers=headers)


def test_unpaid_card_order_cannot_be_fulfilled(client: TestClient) -> None:
    """The core PAY-01 gate: authorized-but-not-captured must NOT ship."""
    order = _card_order(client)
    assert order["payment_status"] == "authorized"
    r = _transition(client, order["order_number"], "shipped", _admin(client))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "FULFILLMENT_PAYMENT_REQUIRED"
    # order unchanged
    body = client.get(f"/api/v1/commerce/orders/{order['order_number']}", headers=_consumer(client)).json()
    assert body["status"] == "processing"


def test_capture_then_fulfillment_succeeds(client: TestClient) -> None:
    order = _card_order(client)
    num = order["order_number"]
    cap = client.post(f"/api/v1/admin/orders/{num}/capture-payment", headers=_admin(client))
    assert cap.status_code == 200, cap.text
    assert cap.json()["payment_status"] == "paid"
    for nxt in ("preparing", "dispatched", "out_for_delivery", "delivered"):
        r = _transition(client, num, nxt, _admin(client))
        assert r.status_code == 200, f"{nxt}: {r.text}"
        assert r.json()["status"] == nxt
    # capture is idempotent after paid
    cap2 = client.post(f"/api/v1/admin/orders/{num}/capture-payment", headers=_admin(client))
    assert cap2.status_code == 200 and cap2.json()["payment_status"] == "paid"


def test_state_machine_rejects_illegal_jump(client: TestClient) -> None:
    order = _card_order(client)
    client.post(f"/api/v1/admin/orders/{order['order_number']}/capture-payment", headers=_admin(client))
    r = _transition(client, order["order_number"], "delivered", _admin(client))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_cod_fulfills_and_settles_cash_at_handover(client: TestClient) -> None:
    order = _cod_order(client, "pay01-cod-1")
    num = order["order_number"]
    assert order["payment_status"] != "paid"
    assert order["status"] == "processing"  # COD fulfilment starts; cash settles at handover
    # COD may move goods before payment (payable at handover)
    for nxt in ("shipped", "out_for_delivery"):
        r = _transition(client, num, nxt, _admin(client))
        assert r.status_code == 200, f"{nxt}: {r.text}"
        assert r.json()["payment_status"] != "paid"  # not yet collected
    r = _transition(client, num, "delivered", _admin(client))
    assert r.status_code == 200, r.text
    assert r.json()["payment_status"] == "paid"  # settled exactly at handover
    # cash settlement is recorded as a real PaymentTransaction (auditable).
    # Session comes from the app's own get_db override — the exact session
    # factory the API writes through (avoids importing conftest, which the
    # deployment dependency gate rightly flags as an undeclared import).
    from backend.app.core.database import get_db
    from backend.app.models.commerce import PaymentTransaction
    from backend.app.models.commerce import Order as OrderModel
    db = next(app.dependency_overrides[get_db]())
    try:
        oid = db.query(OrderModel).filter(OrderModel.order_number == num).first().id
        tx = (
            db.query(PaymentTransaction)
            .filter(PaymentTransaction.order_id == oid, PaymentTransaction.provider == "cash")
            .order_by(PaymentTransaction.created_at.desc())
            .first()
        )
        assert tx is not None, "COD handover must record a cash payment transaction"
        assert tx.status == "paid" and float(tx.amount) == float(order["total_amount"])
    finally:
        db.close()


def test_non_admin_cannot_transition(client: TestClient) -> None:
    order = _card_order(client)
    r = _transition(client, order["order_number"], "shipped", _consumer(client))
    assert r.status_code == 403, r.text


def test_webhook_duplicate_event_is_idempotent(client: TestClient, monkeypatch) -> None:
    from backend.app.core.config import settings
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_pay01_test")
    order = _card_order(client)
    num = order["order_number"]
    payload = b'{"id":"evt_pay01_dup_1","type":"payment_intent.succeeded","order_number":"' + num.encode() + b'"}'
    sig = hmac.new(b"whsec_pay01_test", payload, hashlib.sha256).hexdigest()
    fresh = TestClient(app)  # no cookie jar -> immune to the CSRF cookie guard
    r1 = fresh.post("/api/v1/payments/webhooks/stripe", content=payload,
                     headers={"Content-Type": "application/json", "X-Signature": sig})
    assert r1.status_code == 200 and r1.json()["status"] == "received", r1.text
    r2 = fresh.post("/api/v1/payments/webhooks/stripe", content=payload,
                     headers={"Content-Type": "application/json", "X-Signature": sig})
    assert r2.status_code == 200 and r2.json()["status"] == "duplicate", r2.text
    body = client.get(f"/api/v1/commerce/orders/{num}", headers=_consumer(client)).json()
    assert body["payment_status"] == "paid"


def test_webhook_capture_unlocks_fulfillment(client: TestClient, monkeypatch) -> None:
    from backend.app.core.config import settings
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_pay01_test")
    order = _card_order(client)
    num = order["order_number"]
    payload = b'{"id":"evt_pay01_cap_1","type":"payment_intent.succeeded","order_number":"' + num.encode() + b'"}'
    sig = hmac.new(b"whsec_pay01_test", payload, hashlib.sha256).hexdigest()
    fresh = TestClient(app)
    r = fresh.post("/api/v1/payments/webhooks/stripe", content=payload,
                    headers={"Content-Type": "application/json", "X-Signature": sig})
    assert r.status_code == 200, r.text
    body = client.get(f"/api/v1/commerce/orders/{num}", headers=_consumer(client)).json()
    assert body["payment_status"] == "paid" and body["status"] == "processing"
    ship = _transition(client, num, "shipped", _admin(client))
    assert ship.status_code == 200, ship.text


def test_demo_capture_refuses_in_live_mode(client: TestClient, monkeypatch) -> None:
    from backend.app.services import commerce_service as cs
    order = _card_order(client)
    monkeypatch.setattr(cs.settings, "PAYMENTS_LIVE", 1)
    r = client.post(f"/api/v1/admin/orders/{order['order_number']}/capture-payment", headers=_admin(client))
    assert r.status_code == 422, r.text
    assert "PAYMENTS_LIVE" in r.json()["error"]["message"] or "webhook" in r.json()["error"]["message"]
