"""Presentation currency — one authority for "what currency does the shopper see?".

WHY THIS MODULE EXISTS
----------------------
Measured on production 2026-09-30: ``GET /commerce/payment-methods`` advertised
``currency_code: "EGP"`` for market EG while ``GET /commerce/cart`` returned
``"currency": "USD"`` for the same shopper, and ``GET /catalog/products``
returned raw price-book numbers stamped ``USD``. So the storefront was showing
Egyptian shoppers dollar-denominated numbers next to an Egyptian-pound
checkout. That is not a cosmetic bug: a 289.00 shown as "$289" and charged as
"EGP 289" differ by a factor of ~48.

The FX machinery to fix it already existed — ``MarketSettlement`` in
``providers/payment/capability_registry.py`` resolves a market to a currency
and a rate. What was missing was (a) any configured rate, and (b) any use of
that resolution on the READ path. Settlement answered "what will we charge?";
nothing answered "what do we display?".

DESIGN
------
``MarketSettlement`` stays the single market authority — this module does not
re-implement FX, it *consumes* the same rate table so display and settlement
can never drift. It adds exactly two things:

1. ``resolve_presentation()`` — which currency this request should render in,
   honouring an explicit shopper choice, falling back to the market default,
   and refusing to invent a currency it has no rate for.
2. ``present()`` — converts the declared money fields of an already-serialised
   payload and restamps ``currency``. The field list is an explicit allowlist,
   not a heuristic: a key called ``rating`` or ``ai_fit_score`` is a score, not
   money, and guessing by name is how you end up converting someone's shoe
   size into riyals.

The price book itself is NEVER mutated. Conversion is a presentation concern
applied on the way out; the database keeps one canonical denomination
(``PRICING_CURRENCY``), which is what makes reporting, ledgers and the audit
chain stay comparable.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set

from backend.app.core.money import quantize_money, to_decimal
from backend.app.providers.payment.capability_registry import (
    MarketPaymentCapabilityRegistry as _Registry,
)

#: Money fields that may appear in an outbound payload. Explicit by design —
#: see the module docstring. Adding a money field to a schema WITHOUT adding it
#: here means it renders unconverted, which the contract test catches.
MONEY_FIELDS: Set[str] = {
    # catalog
    "base_price",
    "compare_at_price",
    "price",
    "price_override",
    "min_price",
    "max_price",
    "avg_price",
    "unit_price",
    "original_price",
    # cart / order money
    "subtotal",
    "discount_amount",
    "tax_amount",
    "shipping_amount",
    "total",
    "total_price",
    "total_amount",
    "budget_limit",
    "bnpl_monthly_quote",
    "line_total",
    "line_discount",
}

#: Keys whose values are containers we must walk into. Everything else is left
#: untouched, so an unexpected blob can never be silently rewritten.
_CURRENCY_KEYS = ("currency", "currency_code")


@dataclass(frozen=True)
class PresentationCurrency:
    """The resolved answer for one request.

    ``rate`` converts FROM the price book INTO ``code``. ``Decimal("1")`` when
    they are the same currency, which makes the default configuration a
    provable no-op rather than "probably fine".
    """

    code: str
    pricing_currency: str
    rate: Decimal
    converted: bool
    reason: str
    requested: Optional[str] = None

    @property
    def is_noop(self) -> bool:
        return not self.converted

    def to_pricing(self, amount: Any) -> Optional[float]:
        """Convert an INBOUND amount (a price filter the shopper typed in the
        displayed currency) back into the price book's denomination.

        Without this, a shopper browsing in EGP who drags the price slider to
        "up to 5,000" would have 5000 compared against a USD price book and
        match the entire catalogue. Filters must speak the same currency as
        the numbers the shopper is looking at.
        """
        if amount is None:
            return None
        dec = to_decimal(amount, field="presentation_filter")
        if not self.converted:
            return float(quantize_money(dec))
        return float(quantize_money(dec / self.rate))

    def convert(self, amount: Any) -> Optional[float]:
        """Convert one money value, preserving ``None`` as ``None``.

        ``None`` means "no such price" (e.g. no prior price to advertise);
        turning it into 0.0 would invent a free product.
        """
        if amount is None:
            return None
        dec = to_decimal(amount, field="presentation_amount")
        if not self.converted:
            return float(quantize_money(dec))
        return float(quantize_money(dec * self.rate))


def supported_currencies() -> List[Dict[str, Any]]:
    """Every currency the platform can actually render, with proof.

    ``available`` is the honest bit: a currency the registry knows about but
    has no configured rate for is listed as NOT available rather than offered
    and then silently served at 1:1.
    """
    pricing = _Registry.pricing_currency()
    rates = _Registry.fx_rates()
    seen: Dict[str, Dict[str, Any]] = {}
    for market, currency in sorted(_Registry.MARKET_CURRENCIES.items()):
        entry = seen.setdefault(
            currency,
            {
                "currency": currency,
                "markets": [],
                "is_pricing_currency": currency == pricing,
                "rate_from_pricing_currency": (
                    "1" if currency == pricing else (str(rates[currency]) if currency in rates else None)
                ),
                "available": currency == pricing or currency in rates,
            },
        )
        entry["markets"].append(market)
    return [seen[c] for c in sorted(seen)]


def resolve_presentation(
    requested_currency: Optional[str] = None,
    country_code: Optional[str] = None,
) -> PresentationCurrency:
    """Decide the display currency for one request. Never raises.

    Precedence, highest first:

    1. An explicit shopper choice that the platform can actually honour.
    2. The market's own currency, when a rate exists for it.
    3. The price-book currency — the only honest answer when no rate is
       configured, because rendering "EGP 289" from a 289 USD price book would
       be a 48x lie.
    """
    pricing = _Registry.pricing_currency()
    rates = _Registry.fx_rates()
    requested = (requested_currency or "").strip().upper() or None

    if requested:
        if requested == pricing:
            return PresentationCurrency(
                code=pricing, pricing_currency=pricing, rate=Decimal("1"),
                converted=False, reason="requested_is_pricing_currency", requested=requested,
            )
        if requested in rates:
            return PresentationCurrency(
                code=requested, pricing_currency=pricing, rate=rates[requested],
                converted=True, reason="requested_currency_honoured", requested=requested,
            )
        # Unknown or unrated currency: fall through to the market default
        # rather than 502-ing a storefront read, but record WHY so the
        # response can tell the client its choice was not honoured.
        settlement = _Registry.resolve_settlement(country_code)
        return PresentationCurrency(
            code=settlement.currency, pricing_currency=pricing, rate=settlement.rate,
            converted=settlement.converted,
            reason="requested_currency_unavailable", requested=requested,
        )

    settlement = _Registry.resolve_settlement(country_code)
    return PresentationCurrency(
        code=settlement.currency, pricing_currency=pricing, rate=settlement.rate,
        converted=settlement.converted, reason=settlement.reason, requested=None,
    )


def present(payload: Any, presentation: PresentationCurrency) -> Any:
    """Recursively convert declared money fields and restamp currency labels.

    Applied to the SERIALISED payload, so it works identically for a dict, a
    list of products, or a nested cart — one implementation, every read path.

    The currency label is restamped even on a no-op conversion: a payload that
    says ``USD`` while the shopper is browsing in USD is correct, and a payload
    that says ``USD`` while we failed to honour EGP is *also* correct. The lie
    we are removing is a label that disagrees with the numbers beside it.
    """
    if isinstance(payload, list):
        return [present(item, presentation) for item in payload]
    if not isinstance(payload, (dict, Mapping)):
        return payload

    out: Dict[str, Any] = {}
    for key, value in payload.items():
        if key in MONEY_FIELDS and isinstance(value, (int, float, str, Decimal)) and not isinstance(value, bool):
            out[key] = presentation.convert(value)
        elif key in _CURRENCY_KEYS and isinstance(value, str):
            out[key] = presentation.code
        elif isinstance(value, (dict, list, Mapping)):
            out[key] = present(value, presentation)
        else:
            out[key] = value
    return out


def presentation_meta(presentation: PresentationCurrency) -> Dict[str, Any]:
    """Machine-readable explanation the client can act on.

    A storefront that silently ignores a currency switch is indistinguishable
    from a broken one. This lets the UI say "EGP unavailable, showing USD"
    instead of quietly doing the wrong thing.
    """
    return {
        "currency": presentation.code,
        "pricing_currency": presentation.pricing_currency,
        "rate_from_pricing_currency": str(presentation.rate),
        "converted": presentation.converted,
        "reason": presentation.reason,
        "requested_currency": presentation.requested,
        "honoured": presentation.requested is None or presentation.requested == presentation.code,
    }


def money_fields_of(*schemas: Iterable[Any]) -> Set[str]:  # pragma: no cover - test helper
    """Collect field names from pydantic models (used by the contract test)."""
    names: Set[str] = set()
    for schema in schemas:
        fields = getattr(schema, "model_fields", None) or {}
        names.update(fields.keys())
    return names
