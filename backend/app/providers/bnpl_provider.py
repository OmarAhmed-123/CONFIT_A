from typing import Any, Dict
from backend.app.providers.base import BaseProvider


class BNPLProvider(BaseProvider):
    def __init__(self, provider_name: str = "tabby"):
        super().__init__(name=f"BNPL_{provider_name.upper()}_Provider", timeout_seconds=3.0, max_retries=2)
        self.provider_name = provider_name.lower()

    async def get_installment_quote(self, amount: float, currency: str = "USD") -> Dict[str, Any]:
        return await self.execute_with_resilience(
            self._fetch_remote_quote,
            amount=amount,
            currency=currency
        )

    async def _fetch_remote_quote(self, amount: float, currency: str) -> Dict[str, Any]:
        return await self.fallback(amount=amount, currency=currency)

    async def fallback(self, amount: float, currency: str) -> Dict[str, Any]:
        installments = 4
        installment_val = round(amount / installments, 2) if amount else 0.0
        provider_title = "Tabby" if self.provider_name == "tabby" else ("Tamara" if self.provider_name == "tamara" else "Klarna")
        min_amount = 20.0
        eligible = amount >= min_amount

        schedule = []
        if eligible:
            schedule = [
                {"due_in_days": 0, "amount": installment_val, "status": "Due Today"},
                {"due_in_days": 30, "amount": installment_val, "status": "In 1 month"},
                {"due_in_days": 60, "amount": installment_val, "status": "In 2 months"},
                {"due_in_days": 90, "amount": round(amount - (installment_val * 3), 2), "status": "In 3 months"},
            ]

        return {
            "provider": provider_title,
            "eligible": eligible,
            "installments_count": installments if eligible else 0,
            "installment_amount": installment_val if eligible else None,
            "payment_schedule": schedule,
            "disclaimer": (
                f"Split in {installments} interest-free payments of ${installment_val} with {provider_title}."
                if eligible
                else f"{provider_title} is not available for this amount."
            ),
        }

    def quote_sync(self, amount: float, currency: str = "USD") -> Dict[str, Any]:
        """Deterministic 4-split quote (no network). Same eligibility rules as fallback."""
        installments = 4
        installment_val = round(amount / installments, 2) if amount else 0.0
        provider_title = (
            "Tabby" if self.provider_name == "tabby"
            else ("Tamara" if self.provider_name == "tamara" else self.provider_name.title())
        )
        eligible = amount >= 20.0
        return {
            "provider": provider_title,
            "eligible": eligible,
            "installments_count": installments if eligible else 0,
            "installment_amount": installment_val if eligible else None,
            "payment_schedule": [],
            "disclaimer": (
                f"4 payments of ${installment_val} with {provider_title}"
                if eligible
                else f"{provider_title} is not available for this amount."
            ),
        }
