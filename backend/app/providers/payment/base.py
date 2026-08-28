from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BasePaymentAdapter(ABC):
    """Abstract base class for all localized payment gateway adapters."""

    def __init__(self, name: str, is_live: bool = False):
        self.name = name
        self.is_live = is_live

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
