"""Payment-method models — two concepts that used to be one.

Until 2026-09-23 a single model served both jobs, and the field that belongs to
only one of them defaulted to the flattering answer::

    class PaymentMethodOption(BaseModel):
        ...
        is_live: bool = True          # a LITERAL shipped to shoppers

``PAYMENT_CATALOG`` therefore asserted, in seven places, that every rail was
live — "Tabby — Split in 4 … Sharia compliant, is_live: true" was served by a
deployment holding no Tabby key, no PSP adapter and ``payments_mode=demo``.
PR #176 replaced the published value with a measurement, but the catalogue kept
the literal and the model kept the optimistic default: an internal source of
truth still capable of reproducing the false claim, one forgotten stamp away.

The split below removes the possibility rather than the symptom:

* :class:`PaymentMethodOption` — what the platform supports **in principle**.
  It has no liveness field at all, so no catalogue entry can carry a claim
  about any deployment.
* :class:`MarketPaymentCatalogResponse` — the catalogue's answer for a market.
  Safe to read directly (``product_context_service`` does).
* :class:`PaymentMethodAvailability` — a catalogue option stamped with **this**
  deployment's measured state. ``is_live`` has no default, so the measurement
  layer cannot forget it: omitting it is a ``ValidationError``, never a silent
  ``True``.
* :class:`MarketPaymentCapabilitiesResponse` — the wire contract. Unchanged for
  clients; ``available_methods[].is_live`` is still present, now guaranteed to
  have been measured.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class PaymentMethodOption(BaseModel):
    """A payment method the platform supports in principle.

    Deliberately carries no liveness field: liveness is a property of a
    deployment, not of a catalogue entry, and the two were conflated here.
    """

    id: str = Field(description="Unique method key e.g. 'card', 'bnpl_tabby', 'vodafone_cash', 'apple_pay', 'cod'")
    title_en: str
    title_ar: str
    description_en: str
    description_ar: str
    icon_name: str
    provider_name: str
    requires_redirect: bool = False
    supported_countries: List[str] = Field(default_factory=lambda: ["EG", "AE", "SA"])
    installment_available: bool = False
    installments_count: Optional[int] = None
    fee_percentage: float = 0.0


class MarketPaymentCatalogResponse(BaseModel):
    """What the catalogue supports for a market — no deployment claim.

    Returned by :meth:`MarketPaymentCapabilityRegistry.get_capabilities_for_market`.
    Callers that need "can this deployment settle with it?" must go through
    ``PaymentOrchestrator.get_market_methods`` (or ``capability_service``).
    """

    market_code: str
    currency_code: str
    available_methods: List[PaymentMethodOption]
    cod_eligible: bool = True
    bopis_eligible: bool = True
    disclaimer_en: str
    disclaimer_ar: str


class PaymentMethodAvailability(PaymentMethodOption):
    """A catalogue option carrying THIS deployment's measured state.

    ``is_live`` is **required and has no default** on purpose. The defect this
    file documents began as ``is_live: bool = True`` on the shared model: a
    forgotten value became a false claim. Now a forgotten value is a
    ``ValidationError`` at construction time — loud, immediate, and impossible
    to publish. Only the measurement layer may build these.
    """

    is_live: bool


class MarketPaymentCapabilitiesResponse(BaseModel):
    """The public wire contract for ``/commerce/payment-methods``.

    Same JSON shape as before the split (clients need no change); the type now
    guarantees every entry was stamped by the measurement layer.
    """

    market_code: str
    currency_code: str
    available_methods: List[PaymentMethodAvailability]
    cod_eligible: bool = True
    bopis_eligible: bool = True
    disclaimer_en: str
    disclaimer_ar: str
