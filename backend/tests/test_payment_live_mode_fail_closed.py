"""PAYMENTS_LIVE=true must never fabricate a live authorisation.

Before this fix the orchestrator returned ``status="authorized"``,
``provider="stripe"`` for a live card payment without calling any PSP — an
order would be recorded as paid-by-Stripe with no charge behind it. Live mode
now fails closed until a real PSP adapter is registered in
``PaymentOrchestrator.LIVE_PSP_ADAPTERS``; demo mode is unchanged and labelled.
"""
import pytest

from backend.app.core.config import settings
from backend.app.providers.payment.orchestrator import PaymentOrchestrator


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENTS_LIVE", True)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_live_placeholder_for_test_only")
    monkeypatch.setattr(settings, "TABBY_API_KEY", "tabby_test_key")
    monkeypatch.setattr(settings, "TAMARA_API_KEY", "tamara_test_key")
    yield


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["card", "apple_pay", "google_pay", "bnpl_tabby", "bnpl_tamara",
                                    "vodafone_cash", "instapay_bridge"])
async def test_live_payment_without_psp_adapter_fails_closed(live, method):
    result = await PaymentOrchestrator().initiate_payment(
        method_id=method, amount_minor=12345, currency_code="USD",
        customer_email="x@example.com", order_number="CONF-TEST", country_code="EG",
    )
    assert result["status"] == "failed"
    assert result["reason"] == "live_psp_adapter_not_implemented"
    assert result["mode"] == "live"


@pytest.mark.asyncio
async def test_live_cod_needs_no_psp(live):
    result = await PaymentOrchestrator().initiate_payment(
        method_id="cod", amount_minor=12345, currency_code="USD",
        customer_email="x@example.com", order_number="CONF-TEST", country_code="EG",
    )
    assert result["status"] == "pending_delivery"


@pytest.mark.asyncio
async def test_live_refund_without_psp_adapter_fails_closed(live):
    result = await PaymentOrchestrator().refund(provider_tx_id="tx_x", amount=10, method="card", mode="live")
    assert result["status"] == "failed"
    assert result["reason"] == "live_psp_adapter_not_implemented"


@pytest.mark.asyncio
async def test_demo_mode_is_explicitly_labelled(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENTS_LIVE", False)
    result = await PaymentOrchestrator().initiate_payment(
        method_id="card", amount_minor=12345, currency_code="USD",
        customer_email="x@example.com", order_number="CONF-TEST", country_code="EG",
    )
    assert result["mode"] == "demo"
    assert result["provider"] == "demo_card_adapter"
    assert result["status"] == "authorized"


def test_no_live_adapter_is_silently_registered():
    """Registering a live adapter is a deliberate, reviewed change: it must come
    with provider-sandbox verification, not appear as a side effect."""
    assert PaymentOrchestrator.LIVE_PSP_ADAPTERS == {}
