import os
import uuid
import hmac
import hashlib
from decimal import Decimal
from typing import Dict, Any
from backend.app.core.money import quantize_money, to_float
from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.providers.payment.capability_registry import MarketPaymentCapabilityRegistry
from backend.app.providers.payment.schemas import MarketPaymentCapabilitiesResponse


class PaymentOrchestrator:
    """Orchestrates payment gateway intents, webhook verification, and country capability lookups.

    Payment modes (explicit product contract, surfaced on every order as
    ``payment_mode`` and in the checkout UI):

    * ``demo`` (``PAYMENTS_LIVE=false``, the default): orders are authorised by
      the local demo adapter and labelled as such. No money moves.
    * ``live`` (``PAYMENTS_LIVE=true``): a real PSP charge is REQUIRED. No live
      PSP adapter is implemented in this codebase yet (``LIVE_PSP_ADAPTERS`` is
      empty), so live card/wallet/BNPL/instapay payments FAIL CLOSED with
      ``reason="live_psp_adapter_not_implemented"`` — the previous behaviour
      returned ``status="authorized"``/``provider="stripe"`` without calling
      any gateway, i.e. a fabricated live authorisation. Cash on delivery does
      not involve a PSP and stays valid in both modes.
    """

    # provider key -> live adapter callable. Empty until a real PSP
    # integration (Stripe / Paymob / Tabby / Tamara) is implemented and
    # verified against the provider's sandbox; see PRODUCTION_DEPENDENCIES.md.
    LIVE_PSP_ADAPTERS: Dict[str, Any] = {}

    def __init__(self):
        self.registry = MarketPaymentCapabilityRegistry()

    @classmethod
    def live_adapter_for(cls, method_id: str):
        key = (
            "stripe" if method_id in ("card", "apple_pay", "google_pay")
            else "tabby" if "tabby" in method_id
            else "tamara" if "tamara" in method_id
            else "paymob" if method_id in ("vodafone_cash", "instapay_bridge")
            else None
        )
        return key, cls.LIVE_PSP_ADAPTERS.get(key) if key else None

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
        # Demo adapter: authorised locally and labelled as demo. Live charges
        # require PAYMENTS_LIVE=1 plus the matching provider secret.
        live = bool(settings.PAYMENTS_LIVE)
        mode = "live" if live else "demo"
        status = "authorized" if method_id != "cod" else "pending_delivery"

        def _missing_live_secret(provider: str, attr: str) -> Dict[str, Any]:
            logger.error("Live payment requested but provider secret is not configured", provider=provider)
            return {
                "transaction_id": tx_id,
                "provider": provider,
                "status": "failed",
                "payment_method": method_id,
                "mode": mode,
                "reason": "live_credentials_missing",
            }

        if live and method_id in ("card", "apple_pay", "google_pay") and not (
            settings.STRIPE_SECRET_KEY or os.environ.get("STRIPE_SECRET_KEY")
        ):
            return _missing_live_secret("stripe", "STRIPE_SECRET_KEY")
        if live and "tabby" in method_id and not (settings.TABBY_API_KEY or os.environ.get("TABBY_API_KEY")):
            return _missing_live_secret("tabby", "TABBY_API_KEY")
        if live and "tamara" in method_id and not (settings.TAMARA_API_KEY or os.environ.get("TAMARA_API_KEY")):
            return _missing_live_secret("tamara", "TAMARA_API_KEY")

        if live and method_id != "cod":
            provider_key, adapter = self.live_adapter_for(method_id)
            if adapter is None:
                # FAIL CLOSED: never report a live authorisation that no PSP performed.
                logger.error(
                    "Live payment requested but no live PSP adapter is implemented",
                    provider=provider_key, method=method_id, order=order_number,
                )
                return {
                    "transaction_id": tx_id,
                    "provider": provider_key or method_id,
                    "status": "failed",
                    "payment_method": method_id,
                    "mode": mode,
                    "reason": "live_psp_adapter_not_implemented",
                }
            return await adapter(
                method_id=method_id, amount_minor=amount_minor, currency_code=currency_code,
                customer_email=customer_email, order_number=order_number, country_code=country_code,
                tx_id=tx_id,
            )

        # BNPL Split Payments
        if "bnpl" in method_id or method_id in ["bnpl_tabby", "bnpl_tamara"]:
            installments = 4
            # amount_minor is an exact integer of cents -> Decimal split, 2dp, no float math
            installment_val = to_float(quantize_money(Decimal(int(amount_minor)) / Decimal(100) / Decimal(installments)))
            provider = "Tabby" if "tabby" in method_id else "Tamara"
            return {
                "transaction_id": tx_id,
                "provider": provider,
                "status": status,
                "payment_method": method_id,
                "installments_count": installments,
                "installment_amount": installment_val,
                "redirect_url": None,
                "requires_redirect": False,
                "mode": mode,
            }

        elif method_id == "vodafone_cash":
            return {
                "transaction_id": tx_id,
                "provider": "Paymob_Wallets_EG",
                "status": status,
                "payment_method": "vodafone_cash",
                "requires_redirect": False,
                "mode": mode,
            }

        elif method_id == "instapay_bridge":
            return {
                "transaction_id": tx_id,
                "provider": "InstaPay_PSP_Bridge_EG",
                "status": status,
                "payment_method": "instapay_bridge",
                "requires_redirect": True,
                "mode": mode,
            }

        elif method_id in ("card", "apple_pay", "google_pay"):
            return {
                "transaction_id": tx_id,
                "provider": "stripe" if live else "demo_card_adapter",
                "status": status,
                "payment_method": method_id,
                "requires_redirect": False,
                "mode": mode,
            }

        elif method_id == "cod":
            return {
                "transaction_id": tx_id,
                "provider": "CONFIT_Logistics_COD",
                "status": "pending_delivery",
                "payment_method": "cod",
                "requires_redirect": False,
                "mode": mode,
            }

        return {
            "transaction_id": tx_id,
            "provider": "demo_adapter" if not live else "CONFIT_Payment_Gateway",
            "status": status,
            "payment_method": method_id,
            "requires_redirect": False,
            "mode": mode,
        }

    async def refund(
        self,
        provider_tx_id: str,
        amount: float,
        method: str,
        mode: str = "demo",
    ) -> Dict[str, Any]:
        """Refunds through the configured adapter.

        Demo mode records a refund against the original transaction id without
        calling a live PSP. Live mode requires the matching secret; otherwise
        the refund is reported as failed — never as a fabricated success.
        """
        live = bool(settings.PAYMENTS_LIVE) and mode == "live"
        if live and method == "card" and not settings.STRIPE_SECRET_KEY:
            return {"status": "failed", "reason": "live_credentials_missing", "provider_tx_id": provider_tx_id}
        if live and method != "cod":
            provider_key, adapter = self.live_adapter_for(method)
            if adapter is None:
                logger.error("Live refund requested but no live PSP adapter is implemented",
                             provider=provider_key, method=method, provider_tx_id=provider_tx_id)
                return {"status": "failed", "reason": "live_psp_adapter_not_implemented",
                        "provider_tx_id": provider_tx_id}
            return await adapter.refund(provider_tx_id=provider_tx_id, amount=amount, method=method)
        logger.info(
            "Refund initiated",
            provider_tx_id=provider_tx_id,
            amount=amount,
            mode="live" if live else "demo",
        )
        return {
            "status": "refunded",
            "provider_tx_id": provider_tx_id,
            "amount": amount,
            "mode": "live" if live else "demo",
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
