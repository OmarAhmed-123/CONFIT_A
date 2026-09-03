from decimal import Decimal
from typing import Any, Dict

from backend.app.core.money import (
    MoneyInput, money_mul, money_sub, quantize_money, to_decimal, to_float,
)
from backend.app.providers.base import BaseProvider


class BNPLProvider(BaseProvider):
    """Deterministic 4-split BNPL quote.

    Money is handled as Decimal end-to-end (quantized to cents, ROUND_HALF_UP);
    only the JSON boundary converts to float via ``to_float`` (2dp) so no
    float arithmetic touches an installment amount. The last installment
    absorbs the rounding remainder so the schedule sums exactly to ``amount``.
    """

    INSTALLMENTS = 4
    MIN_AMOUNT = Decimal("20.00")

    def __init__(self, provider_name: str = "tabby"):
        super().__init__(name=f"BNPL_{provider_name.upper()}_Provider", timeout_seconds=3.0, max_retries=2)
        self.provider_name = provider_name.lower()

    @property
    def provider_title(self) -> str:
        return (
            "Tabby" if self.provider_name == "tabby"
            else ("Tamara" if self.provider_name == "tamara" else self.provider_name.title())
        )

    async def get_installment_quote(self, amount: MoneyInput, currency: str = "USD") -> Dict[str, Any]:
        return await self.execute_with_resilience(
            self._fetch_remote_quote,
            amount=amount,
            currency=currency
        )

    async def _fetch_remote_quote(self, amount: MoneyInput, currency: str) -> Dict[str, Any]:
        return await self.fallback(amount=amount, currency=currency)

    def _split(self, amount: MoneyInput):
        """Return (eligible, installment, last_installment) as Decimals."""
        total = to_decimal(amount, "amount")  # NaN/Inf/garbage -> MoneyValueError
        eligible = total >= self.MIN_AMOUNT
        if not eligible:
            return False, Decimal("0.00"), Decimal("0.00")
        installment = quantize_money(total / Decimal(self.INSTALLMENTS))
        last = money_sub(total, money_mul(installment, self.INSTALLMENTS - 1))
        return True, installment, last

    async def fallback(self, amount: MoneyInput, currency: str) -> Dict[str, Any]:
        eligible, installment, last = self._split(amount)
        inst = to_float(installment)
        schedule = []
        if eligible:
            schedule = [
                {"due_in_days": 0, "amount": inst, "status": "Due Today"},
                {"due_in_days": 30, "amount": inst, "status": "In 1 month"},
                {"due_in_days": 60, "amount": inst, "status": "In 2 months"},
                {"due_in_days": 90, "amount": to_float(last), "status": "In 3 months"},
            ]
        return {
            "provider": self.provider_title,
            "eligible": eligible,
            "installments_count": self.INSTALLMENTS if eligible else 0,
            "installment_amount": inst if eligible else None,
            "payment_schedule": schedule,
            "disclaimer": (
                f"Split in {self.INSTALLMENTS} interest-free payments of ${installment} with {self.provider_title}."
                if eligible
                else f"{self.provider_title} is not available for this amount."
            ),
        }

    def quote_sync(self, amount: MoneyInput, currency: str = "USD") -> Dict[str, Any]:
        """Deterministic 4-split quote (no network). Same eligibility rules as fallback."""
        eligible, installment, _last = self._split(amount)
        inst = to_float(installment)
        return {
            "provider": self.provider_title,
            "eligible": eligible,
            "installments_count": self.INSTALLMENTS if eligible else 0,
            "installment_amount": inst if eligible else None,
            "payment_schedule": [],
            "disclaimer": (
                f"{self.INSTALLMENTS} payments of ${installment} with {self.provider_title}"
                if eligible
                else f"{self.provider_title} is not available for this amount."
            ),
        }
