from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BasePaymentAdapter(ABC):
    """Abstract base class for all localized payment gateway adapters.

    Deliberately carries NO liveness field (removed 2026-09-23).

    Until this cycle `__init__` accepted `is_live: bool = False` and stored it.
    Nothing read it — the class has no subclasses and is never constructed — and
    that is exactly why it had to go: it is the class a real PSP adapter is
    written by subclassing, and a boolean named `is_live` sitting on it, with a
    default, is a second source of truth for the one fact this platform must not
    get wrong. A future `if adapter.is_live:` would publish a liveness claim
    that no measurement made — the same shape as the `is_live: bool = True`
    catalogue literal that served "Tabby … Sharia compliant, live" on a
    deployment holding no Tabby key (PR #176).

    Liveness is asked of `capability_service.payment_method_is_live(method_id)`,
    which consults `PAYMENTS_LIVE`, whether an adapter is actually implemented in
    `LIVE_PSP_ADAPTERS`, and whether that provider's credential is configured.
    `backend/tests/test_payment_adapter_liveness_owner.py` fails if a liveness
    field is reintroduced here or anywhere else in this package.
    """

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def create_payment_intent(
        self,
        amount_minor: int,
        currency_code: str,
        customer_email: str,
        customer_phone: Optional[str] = None,
        order_number: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Creates a payment intent, checkout session, or tokenized payload with the PSP."""

    @abstractmethod
    async def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        signature_header: str,
        secret: str
    ) -> bool:
        """Verifies cryptographic HMAC signature on incoming PSP webhook callbacks."""

    @abstractmethod
    async def get_transaction_status(self, provider_tx_id: str) -> Dict[str, Any]:
        """Queries PSP for current settled status."""
