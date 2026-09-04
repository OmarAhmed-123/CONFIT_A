"""BRD §globalization — checkout settles in the buyer's market currency.

Contract: the order, its payment transaction and the cart breakdown must all be
recorded/presented in ONE currency per market, derived from the *server-side*
market→currency map (MarketPaymentCapabilityRegistry.MARKET_CURRENCIES), never a
client-supplied amount/currency and never a hardcoded USD.

These pin:
- EG order + its payment transaction -> EGP
- AE order + its payment transaction -> AED
- an unmapped/generic market -> USD (safe fallback; never silently becomes a
  wrong local currency)
- server-authoritative: the cart/order currency is decided by the selected
  country, not by any client-provided currency field.
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


def _first_in_stock_product(client: TestClient) -> dict:
    products = client.get("/api/v1/catalog/products").json()
    assert products
    detail = client.get(f"/api/v1/catalog/products/{products[0]['id']}").json()
    sku = next(s for s in detail["skus"] if s["is_in_stock"])
    return detail, sku


def _checkout(client: TestClient, token: str, sku: dict, country: str) -> dict:
    headers = {
        "Authorization": f"Bearer {token}",
        # fresh session token per checkout (cart.session_token is UNIQUE)
        "X-Session-Token": str(uuid.uuid4()),
    }
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
            "recipient_name": "Currency Buyer",
            "phone": "+201000000000",
            "address_line": "1 Tahrir",
            "city": "Cairo",
            "country": country,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_eg_checkout_settles_in_egp(client: TestClient) -> None:
    token = _register(client, f"cur_eg_{uuid.uuid4().hex[:6]}@confit.io", "EG Buyer")
    product, sku = _first_in_stock_product(client)
    order = _checkout(client, token, sku, "EG")
    assert order["currency"] == "EGP"
    assert order["shipping_recipient_name"] == "Currency Buyer"


def test_ae_checkout_settles_in_aed(client: TestClient) -> None:
    token = _register(client, f"cur_ae_{uuid.uuid4().hex[:6]}@confit.io", "AE Buyer")
    product, sku = _first_in_stock_product(client)
    order = _checkout(client, token, sku, "AE")
    assert order["currency"] == "AED"


def test_unmapped_market_falls_back_to_usd(client: TestClient) -> None:
    token = _register(client, f"cur_zz_{uuid.uuid4().hex[:6]}@confit.io", "ZZ Buyer")
    product, sku = _first_in_stock_product(client)
    order = _checkout(client, token, sku, "ZZ")
    # An unknown market must never become a silently-typed wrong local currency;
    # the safe default is the generic global currency.
    assert order["currency"] == "USD"


def test_payment_transaction_uses_order_currency(client: TestClient) -> None:
    from backend.app.models.commerce import PaymentTransaction
    from backend.tests.conftest import TestingSessionLocal

    token = _register(client, f"cur_tx_{uuid.uuid4().hex[:6]}@confit.io", "Tx Buyer")
    product, sku = _first_in_stock_product(client)
    order = _checkout(client, token, sku, "EG")

    db = TestingSessionLocal()
    try:
        tx = (
            db.query(PaymentTransaction)
            .filter(PaymentTransaction.order_id == order["id"])
            .first()
        )
        assert tx is not None, "checkout did not create a payment transaction"
        # Order and its payment transaction share the market currency.
        assert tx.currency == "EGP"
        assert tx.currency == order["currency"]
    finally:
        db.close()
