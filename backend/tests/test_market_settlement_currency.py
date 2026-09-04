"""Market settlement currency - resolution, wiring and tamper resistance.

The defect: checkout hardcoded ``currency="USD"`` in every settled
transactional path (order, payment initiation, payment transaction, BNPL quote,
cart, checkout session) while ``MarketPaymentCapabilityRegistry`` next door
already knew that EG settles in EGP and AE in AED. The market configuration
existed and was simply never wired to the money.

These tests pin the replacement contract:

    Country -> Market capability registry -> Currency -> Order -> Payment
      -> Payment transaction

with the amount and the label always agreeing (currency without a rate would
mislabel money by ~48x, which is worse than the honest literal it replaces),
and with the client never able to choose the currency its own order settles in.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.core.config import settings
from backend.app.providers.payment.capability_registry import (
    MarketPaymentCapabilityRegistry as Registry,
)
from backend.tests.conftest import TestingSessionLocal


# --------------------------------------------------------------------------
# Shared-state isolation: these tests really check out, which really
# decrements product_skus.stock_level in the shared test database.
# --------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _restore_catalog_stock():
    db = TestingSessionLocal()
    try:
        before = db.execute(
            text("select id, stock_level, is_in_stock from product_skus")).all()
    finally:
        db.close()
    yield
    db = TestingSessionLocal()
    try:
        for sku_id, stock_level, is_in_stock in before:
            db.execute(
                text("update product_skus set stock_level = :s, is_in_stock = :i where id = :id"),
                {"s": stock_level, "i": is_in_stock, "id": sku_id})
        db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------
# Unit: the resolver
# --------------------------------------------------------------------------
class TestResolver:
    def test_pricing_currency_is_configuration_not_a_literal(self):
        assert Registry.pricing_currency() == settings.PRICING_CURRENCY.strip().upper()

    def test_market_currency_comes_from_the_registry(self):
        assert Registry.currency_for_market("EG") == "EGP"
        assert Registry.currency_for_market("AE") == "AED"
        assert Registry.currency_for_market("US") == "USD"

    def test_country_names_and_aliases_normalise_to_market_codes(self):
        # CheckoutRequest.country still defaults to the NAME "UAE", and
        # shipping addresses are free text - the resolver must understand both.
        assert Registry.market_code("UAE") == "AE"
        assert Registry.market_code("Egypt") == "EG"
        assert Registry.market_code("usa") == "US"
        assert Registry.market_code(None) == "EG"
        assert Registry.resolve_settlement("UAE").market_code == "AE"

    def test_no_fx_rate_configured_fails_safe_to_the_pricing_currency(self):
        """The fail-safe that makes this shippable: without a treasury rate the
        resolver settles in the pricing currency (today's behaviour) rather than
        stamping a market currency onto amounts never priced in it."""
        res = Registry.resolve_settlement("EG")
        assert res.market_currency == "EGP"
        assert res.currency == Registry.pricing_currency()
        assert res.converted is False
        assert res.rate == Decimal("1")
        assert res.reason == "fx_rate_not_configured"

    def test_configured_rate_settles_in_the_market_currency(self, monkeypatch):
        monkeypatch.setattr(settings, "MARKET_FX_RATES", '{"EGP": "48.5", "AED": "3.6725"}')
        eg = Registry.resolve_settlement("EG")
        assert (eg.currency, eg.rate, eg.converted, eg.reason) == (
            "EGP", Decimal("48.5"), True, "fx_rate_configured")
        ae = Registry.resolve_settlement("AE")
        assert (ae.currency, ae.rate) == ("AED", Decimal("3.6725"))
        # A market already in the pricing currency needs no rate at all.
        us = Registry.resolve_settlement("US")
        assert (us.currency, us.converted, us.reason) == (
            "USD", False, "market_currency_is_pricing_currency")

    def test_conversion_is_exact_decimal_and_a_noop_when_not_converted(self, monkeypatch):
        monkeypatch.setattr(settings, "MARKET_FX_RATES", '{"EGP": "48.5"}')
        conv = Registry.resolve_settlement("EG")
        assert conv.convert(Decimal("10.00")) == Decimal("485.00")
        assert conv.convert(Decimal("0.01")) == Decimal("0.49")  # ROUND_HALF_UP to 2dp
        plain = Registry.resolve_settlement("US")
        assert plain.convert(Decimal("10.00")) == Decimal("10.00")

    @pytest.mark.parametrize("bad", [
        "not json", "[1,2]", '{"EGP": "abc"}', '{"EGP": "0"}', '{"EGP": "-3"}',
        '{"EGP": "NaN"}', '{"EGP": "Infinity"}', "42",
    ])
    def test_malformed_fx_table_never_produces_a_rate(self, monkeypatch, bad):
        """A malformed table must not take checkout down, and a malformed ENTRY
        must never be silently treated as 1.0 - that would mislabel money."""
        monkeypatch.setattr(settings, "MARKET_FX_RATES", bad)
        assert Registry.fx_rates() == {}
        res = Registry.resolve_settlement("EG")
        assert res.converted is False
        assert res.currency == Registry.pricing_currency()

    def test_one_bad_entry_does_not_poison_a_good_one(self, monkeypatch):
        monkeypatch.setattr(settings, "MARKET_FX_RATES", '{"EGP": "junk", "AED": "3.6725"}')
        rates = Registry.fx_rates()
        assert "EGP" not in rates
        assert rates["AED"] == Decimal("3.6725")


# --------------------------------------------------------------------------
# Source guard: no USD literal may come back into the settled money path
# --------------------------------------------------------------------------
def test_no_hardcoded_usd_in_the_settled_money_path():
    import os
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    offenders = []
    for rel in ("backend/app/services/commerce_service.py",
                "backend/app/controllers/commerce_controller.py",
                "backend/app/providers/bnpl_provider.py",
                "backend/app/providers/payment/orchestrator.py"):
        path = os.path.join(repo, rel)
        for n, line in enumerate(open(path, encoding="utf-8"), 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("*"):
                continue
            for pat in ('currency="USD"', "currency='USD'",
                        'currency_code="USD"', "currency_code='USD'"):
                if pat in line:
                    offenders.append(f"{rel}:{n}: {stripped[:120]}")
    assert offenders == [], "hardcoded settlement currency reappeared:\n" + "\n".join(offenders)


# --------------------------------------------------------------------------
# End-to-end helpers
# --------------------------------------------------------------------------
def _register(client: TestClient) -> str:
    r = client.post("/api/v1/auth/register", json={
        "email": f"fx_{uuid.uuid4().hex[:8]}@confit.io",
        "password": "Password123!", "full_name": "FX Buyer"})
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


def _checkout(client: TestClient, token: str, country: str, extra: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {token}",
               "X-Session-Token": f"fx_{uuid.uuid4().hex[:10]}"}
    cart = client.get("/api/v1/commerce/cart", headers=headers).json()
    for it in list(cart.get("items") or []):
        client.delete(f"/api/v1/commerce/cart/items/{it['id']}", headers=headers)
    products = client.get("/api/v1/catalog/products").json()
    detail = client.get(f"/api/v1/catalog/products/{products[0]['id']}").json()
    sku = next(s for s in detail["skus"] if s["is_in_stock"])
    added = client.post("/api/v1/commerce/cart/items",
                        json={"product_sku_id": sku["id"], "quantity": 2}, headers=headers)
    assert added.status_code in (200, 201), added.text
    payload = {
        "payment_method": "cod", "fulfillment_type": "delivery",
        "recipient_name": "FX Buyer", "phone": "+201000000000",
        "address_line": "1 Tahrir", "city": "Cairo", "country": country,
    }
    payload.update(extra or {})
    r = client.post("/api/v1/commerce/checkout", headers=headers, json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _money_rows(order_number: str) -> dict:
    db = TestingSessionLocal()
    try:
        order = db.execute(text(
            "select id, currency, total_amount, subtotal_amount, discount_amount, "
            "tax_amount, shipping_amount from orders where order_number = :on"),
            {"on": order_number}).mappings().first()
        assert order, "order must be persisted"
        tx = db.execute(text(
            "select currency, amount from payment_transactions where order_id = :oid"),
            {"oid": order["id"]}).mappings().all()
        items = db.execute(text(
            "select unit_price, subtotal, quantity from order_items where order_id = :oid"),
            {"oid": order["id"]}).mappings().all()
        return {"order": order, "transactions": tx, "items": items}
    finally:
        db.close()


# --------------------------------------------------------------------------
# End-to-end: default configuration (no FX) must not change any behaviour
# --------------------------------------------------------------------------
def test_default_configuration_settles_in_the_pricing_currency(client: TestClient):
    token = _register(client)
    order = _checkout(client, token, "EG")
    rows = _money_rows(order["order_number"])

    assert order["currency"] == Registry.pricing_currency()
    assert rows["order"]["currency"] == Registry.pricing_currency()
    assert rows["transactions"], "a payment transaction must exist"
    assert all(t["currency"] == Registry.pricing_currency() for t in rows["transactions"])

    # Cart agrees with the order about which currency it is in.
    headers = {"Authorization": f"Bearer {token}", "X-Session-Token": f"fx_{uuid.uuid4().hex[:10]}"}
    cart = client.get("/api/v1/commerce/cart", headers=headers).json()
    assert cart["currency"] == Registry.pricing_currency()


def test_order_money_is_internally_consistent_in_the_settled_currency(client: TestClient):
    token = _register(client)
    order = _checkout(client, token, "AE")
    rows = _money_rows(order["order_number"])
    o = rows["order"]
    d = lambda v: Decimal(str(v))  # noqa: E731
    assert d(o["total_amount"]) == (
        d(o["subtotal_amount"]) - d(o["discount_amount"])
        + d(o["tax_amount"]) + d(o["shipping_amount"]))
    # Revenue conservation at item grain: the order subtotal is exactly the sum
    # of the persisted line subtotals.
    assert d(o["subtotal_amount"]) == sum((d(i["subtotal"]) for i in rows["items"]), Decimal("0.00"))
    for i in rows["items"]:
        assert d(i["subtotal"]) == d(i["unit_price"]) * i["quantity"]
    for t in rows["transactions"]:
        assert d(t["amount"]) == d(o["total_amount"])


# --------------------------------------------------------------------------
# End-to-end: with a configured rate the whole chain converts
# --------------------------------------------------------------------------
def test_configured_rate_settles_the_whole_chain_in_the_market_currency(
        client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "MARKET_FX_RATES", '{"EGP": "48.5"}')
    token = _register(client)
    order = _checkout(client, token, "EG")
    rows = _money_rows(order["order_number"])
    o = rows["order"]
    d = lambda v: Decimal(str(v))  # noqa: E731

    assert order["currency"] == "EGP"
    assert o["currency"] == "EGP"
    assert rows["transactions"] and all(t["currency"] == "EGP" for t in rows["transactions"])

    # Amounts were really converted, not just relabelled.
    assert d(o["subtotal_amount"]) > Decimal("1000"), (
        f"EGP subtotal looks unconverted: {o['subtotal_amount']}")
    # Still internally consistent after conversion + rounding.
    assert d(o["total_amount"]) == (
        d(o["subtotal_amount"]) - d(o["discount_amount"])
        + d(o["tax_amount"]) + d(o["shipping_amount"]))
    assert d(o["subtotal_amount"]) == sum((d(i["subtotal"]) for i in rows["items"]), Decimal("0.00"))
    for t in rows["transactions"]:
        assert d(t["amount"]) == d(o["total_amount"])
    # NUMERIC(12,2) range must still hold in the bigger currency.
    for field in ("total_amount", "subtotal_amount", "tax_amount",
                  "shipping_amount", "discount_amount"):
        assert d(o[field]) < Decimal("9999999999.99"), field


def test_checkout_session_is_stamped_with_the_resolved_currency(
        client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "MARKET_FX_RATES", '{"EGP": "48.5"}')
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}",
               "X-Session-Token": f"fx_cs_{uuid.uuid4().hex[:8]}"}
    products = client.get("/api/v1/catalog/products").json()
    detail = client.get(f"/api/v1/catalog/products/{products[0]['id']}").json()
    sku = next(s for s in detail["skus"] if s["is_in_stock"])
    r = client.post("/api/v1/commerce/cart/items",
                    json={"product_sku_id": sku["id"], "quantity": 1}, headers=headers)
    assert r.status_code in (200, 201), r.text
    created = client.post("/api/v1/checkout/sessions", headers=headers, json={
        "payment_method": "cod", "fulfillment_type": "delivery",
        "recipient_name": "FX Buyer", "phone": "+201000000000",
        "address_line": "1 Tahrir", "city": "Cairo", "country": "EG",
        "currency": "JPY",  # tamper: a client-declared currency
    })
    assert created.status_code == 200, created.text
    assert created.json()["currency"] == "EGP"


# --------------------------------------------------------------------------
# Tamper resistance
# --------------------------------------------------------------------------
def test_client_cannot_impose_the_settlement_currency(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "MARKET_FX_RATES", '{"EGP": "48.5"}')
    token = _register(client)
    order = _checkout(client, token, "EG", extra={
        "currency": "JPY", "currency_code": "JPY", "total": 1,
        "total_amount": 1, "subtotal_amount": 1, "tax_amount": 0,
    })
    rows = _money_rows(order["order_number"])
    assert order["currency"] == "EGP"
    assert rows["order"]["currency"] == "EGP"
    assert all(t["currency"] == "EGP" for t in rows["transactions"])
    assert Decimal(str(rows["order"]["total_amount"])) > Decimal("1")


def test_bnpl_quote_uses_the_server_resolved_currency(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "MARKET_FX_RATES", '{"EGP": "48.5"}')
    monkeypatch.setattr(settings, "MARKET", "EG")
    r = client.post("/api/v1/commerce/bnpl-quote",
                    json={"amount": 1000, "currency": "JPY", "provider": "tabby"})
    assert r.status_code == 200, r.text
    body = r.json()
    # The quote is produced in the market's settlement currency and the
    # disclaimer names that currency instead of a hardcoded "$".
    assert "JPY" not in (body.get("disclaimer") or "")
    assert "$" not in (body.get("disclaimer") or "")
    assert "EGP" in (body.get("disclaimer") or "")
