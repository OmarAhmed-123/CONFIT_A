from typing import List, Optional
from pydantic import BaseModel, Field


class PaymentMethodOption(BaseModel):
    id: str = Field(description="Unique method key e.g. 'card', 'bnpl_tabby', 'vodafone_cash', 'apple_pay', 'cod'")
    title_en: str
    title_ar: str
    description_en: str
    description_ar: str
    icon_name: str
    provider_name: str
    is_live: bool = True
    requires_redirect: bool = False
    supported_countries: List[str] = Field(default_factory=lambda: ["EG", "AE", "SA"])
    installment_available: bool = False
    installments_count: Optional[int] = None
    fee_percentage: float = 0.0


class MarketPaymentCapabilitiesResponse(BaseModel):
    market_code: str
    currency_code: str
    available_methods: List[PaymentMethodOption]
    cod_eligible: bool = True
    bopis_eligible: bool = True
    disclaimer_en: str
    disclaimer_ar: str
