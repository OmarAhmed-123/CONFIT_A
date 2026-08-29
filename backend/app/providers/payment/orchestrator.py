import os
import uuid
import hmac
import hashlib
from typing import Dict, Any
from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.providers.payment.capability_registry import MarketPaymentCapabilityRegistry
from backend.app.providers.payment.schemas import MarketPaymentCapabilitiesResponse


class PaymentOrchestrator:
    """Orchestrates payment gateway intents, webhook verification, and country capability lookups."""

    def __init__(self):
        self.registry = MarketPaymentCapabilityRegistry()

    def get_market_methods(self, country_code: str = "EG") -> MarketPaymentCapabilitiesResponse:
        return self.registry.get_capabilities_for_market(country_code)

    async def initiate_payment(
        self,
        method_id: str,
        amount_minor: int,
        currency_code: str,
        customer_email: str,
        order_number: str,
        country_code: str = "EG"
    ) -> Dict[str, Any]:
        logger.info(
            "Initiating payment transaction",
            method=method_id,
            amount_minor=amount_minor,
            currency=currency_code,
            order=order_number,
            market=country_code
        )

        tx_id = f"tx_{uuid.uuid4().hex[:12]}"

        # BNPL Split Payments
        if "bnpl" in method_id or method_id in ["bnpl_tabby", "bnpl_tamara"]:
            installments = 4
            installment_val = round((amount_minor / 100.0) / installments, 2)
            return {
                "transaction_id": tx_id,
                "provider": "Tabby" if "tabby" in method_id else "Tamara",
                "status": "authorized",
                "payment_method": method_id,
                "installments_count": installments,
                "installment_amount": installment_val,
                "redirect_url": None,
                "requires_redirect": False
            }

        # Egypt Smart Wallets (Vodafone Cash / Fawry)
        elif method_id == "vodafone_cash":
            return {
                "transaction_id": tx_id,
                "provider": "Paymob_Wallets_EG",
                "status": "authorized",
                "payment_method": "vodafone_cash",
                "wallet_reference": f"VFC-{uuid.uuid4().hex[:6].upper()}",
                "requires_redirect": False
            }

        # Egypt InstaPay Bridge
        elif method_id == "instapay_bridge":
            return {
                "transaction_id": tx_id,
                "provider": "InstaPay_PSP_Bridge_EG",
                "status": "authorized",
                "payment_method": "instapay_bridge",
                "ipn_reference": f"IPN-{uuid.uuid4().hex[:8].upper()}",
                "requires_redirect": False
            }

        # Credit / Debit Card
        elif method_id == "card":
            return {
                "transaction_id": tx_id,
                "provider": "Stripe_or_Paymob",
                "status": "captured",
                "payment_method": "card",
                "card_brand": "Visa",
                "last4": "4242",
                "requires_redirect": False
            }

        # Cash on Delivery
        elif method_id == "cod":
            return {
                "transaction_id": tx_id,
                "provider": "CONFIT_Logistics_COD",
                "status": "pending_delivery",
                "payment_method": "cod",
                "requires_redirect": False
            }

        # Fallback
        return {
            "transaction_id": tx_id,
            "provider": "CONFIT_Payment_Gateway",
            "status": "captured",
            "payment_method": method_id,
            "requires_redirect": False
        }

    # Per-provider webhook secrets (configured via environment). A provider
    # with no configured secret can never verify — webhooks are then rejected,
    # never silently accepted.
    PROVIDER_SECRET_ATTRS = {
        "tabby": "TABBY_API_KEY",
        "tamara": "TAMARA_API_KEY",
        "stripe": "STRIPE_WEBHOOK_SECRET",
        "paymob": "PAYMOB_API_KEY",
    }

    def verify_webhook(self, provider_name: str, payload_bytes: bytes, signature_header: str) -> bool:
        """Cryptographically verifies the webhook HMAC-SHA256 signature over
        the RAW request body. No dev bypass: the previous implementation ended
        with `or True`, making every webhook 'verified' regardless of the
        signature — that hole is closed."""
        if not signature_header:
            return False
        attr = self.PROVIDER_SECRET_ATTRS.get(provider_name.lower())
        secret = (getattr(settings, attr, None) or os.environ.get(attr)) if attr else None
        if not secret:
            logger.error("Webhook rejected: no secret configured for provider", provider=provider_name)
            return False
        expected = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature_header)
