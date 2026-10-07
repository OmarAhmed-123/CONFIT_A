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

from backend.app.core.config import settings
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
    # Product-detail instalment figures. The cart's `bnpl_monthly_quote` was
    # declared here from day one, but the PDP publishes the SAME money under
    # two other names — `bnpl_monthly_installment` (top level) and
    # `bnpl.installment_amount` (nested teaser). Neither was in this allowlist,
    # so an EGP storefront converted the price to EGP 3,932.37 while the badge
    # right under it kept quoting the price book's $18.75 — wrong currency AND
    # wrong arithmetic in the same sentence (observed in production,
    # 2026-10-07 screenshot audit).
    "bnpl_monthly_installment",
    "installment_amount",
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

    def factor_from(self, source_currency: Optional[str]) -> Decimal:
        """Conversion factor FROM ``source_currency`` INTO this currency.

        DEFECT THIS FIXES — found in production, 2026-09-30, caused by the
        first cut of this very module. ``commerce_service`` ALREADY converts
        cart money through ``MarketSettlement`` before returning it. That
        conversion had been a silent no-op for as long as ``MARKET_FX_RATES``
        was empty; the moment real rates were configured it woke up, and a
        presentation layer that blindly converted "from the price book"
        converted a SECOND time. Measured on production: a 180.00 USD line
        rendered as 488,444.65 EGP (180 x 52.09 x 52.09).

        The fix is to stop assuming the input denomination. A payload states
        its own currency, and converting from THAT is idempotent: it does not
        matter whether an upstream layer already converted, and any number of
        presentation passes produce the same answer. Composability here is a
        correctness property, not a nicety.
        """
        source = (source_currency or "").strip().upper() or self.pricing_currency
        if source == self.code:
            return Decimal("1")
        rates = dict(_Registry.fx_rates())
        rates[self.pricing_currency] = Decimal("1")
        src_rate = rates.get(source)
        dst_rate = rates.get(self.code)
        if src_rate is None or dst_rate is None or src_rate <= 0:
            # An unknown denomination is not a licence to guess. Leaving the
            # amount untouched keeps it consistent with the label already on
            # it, which is the only honest option.
            return Decimal("1")
        return dst_rate / src_rate

    def convert(self, amount: Any, source_currency: Optional[str] = None) -> Optional[float]:
        """Convert one money value, preserving ``None`` as ``None``.

        ``None`` means "no such price" (e.g. no prior price to advertise);
        turning it into 0.0 would invent a free product.

        ``source_currency`` defaults to the price book. Callers that know the
        payload's real denomination MUST pass it — see ``factor_from``.
        """
        if amount is None:
            return None
        dec = to_decimal(amount, field="presentation_amount")
        factor = self.factor_from(source_currency)
        if factor == 1:
            return float(quantize_money(dec))
        return float(quantize_money(dec * factor))


def default_display_currency() -> str:
    """Storefront default when the shopper has expressed no preference.

    Separate from ``PRICING_CURRENCY`` on purpose: the price book is stored in
    one denomination (USD today) while CONFIT's home market reads in EGP.
    Conflating the two would mean re-denominating every product row just to
    change a default.
    """
    raw = (getattr(settings, "DEFAULT_DISPLAY_CURRENCY", "") or "").strip().upper()
    return raw or _Registry.pricing_currency()


def rate_snapshot():
    """Provenance-carrying rate table (live / stale_live / configured)."""
    from backend.app.services.fx_rates import fx_rates as _live

    return _live.snapshot()


def supported_currencies() -> List[Dict[str, Any]]:
    """Every currency the platform can actually render, with proof.

    Changed 2026-09-30: this used to enumerate only the eight registry market
    currencies. It now enumerates every currency the live rate table carries
    (166 today), because a shopper outside those eight markets previously had
    no option at all. Registry markets are still flagged so the UI can list
    them first.

    ``available`` stays the honest bit: a currency with no rate is reported
    NOT available rather than offered and then silently served at 1:1.
    """
    pricing = _Registry.pricing_currency()
    snapshot = rate_snapshot()
    rates = snapshot.rates
    markets_by_currency: Dict[str, List[str]] = {}
    for market, currency in sorted(_Registry.MARKET_CURRENCIES.items()):
        markets_by_currency.setdefault(currency, []).append(market)

    codes = set(rates) | set(markets_by_currency) | {pricing, default_display_currency()}
    out: List[Dict[str, Any]] = []
    for code in sorted(codes):
        is_pricing = code == pricing
        rate = Decimal("1") if is_pricing else rates.get(code)
        out.append({
            "currency": code,
            "markets": markets_by_currency.get(code, []),
            "is_pricing_currency": is_pricing,
            "is_market_currency": code in markets_by_currency,
            "is_default": code == default_display_currency(),
            "rate_from_pricing_currency": str(rate) if rate is not None else None,
            "available": rate is not None,
        })
    return out


def resolve_presentation(
    requested_currency: Optional[str] = None,
    country_code: Optional[str] = None,
) -> PresentationCurrency:
    """Decide the display currency for one request. Never raises.

    Precedence, highest first:

    1. An explicit shopper choice that the platform can actually honour.
    2. The market's own currency, when a rate exists for it.
    3. ``DEFAULT_DISPLAY_CURRENCY`` (EGP — CONFIT's home market), when a rate
       exists for it. A visitor with no market signal should not be shown a
       USD price book.
    4. The price-book currency — the only honest answer when no rate exists at
       all, because rendering "EGP 289" from a 289 USD price book would be a
       ~52x lie.
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
    if settlement.converted:
        return PresentationCurrency(
            code=settlement.currency, pricing_currency=pricing, rate=settlement.rate,
            converted=True, reason=settlement.reason, requested=None,
        )

    # Settlement could not place the shopper in a converted market currency.
    # Two different situations hide behind that, and they need different
    # answers:
    #
    #   (a) The caller named a country the registry KNOWS (e.g. "US" -> USD).
    #       Settlement's answer is correct and final; overriding a real market
    #       signal with the home-market default would show a US shopper EGP.
    #   (b) There was no country signal, or an unknown one. Only here does the
    #       storefront default apply — CONFIT's home market reads in EGP, and
    #       a visitor with no signal should not be handed a USD price book.
    known_market = (
        country_code is not None
        and _Registry.market_code(country_code) in _Registry.MARKET_CURRENCIES
    )
    fallback = default_display_currency()
    if not known_market and fallback != pricing and fallback in rates:
        return PresentationCurrency(
            code=fallback, pricing_currency=pricing, rate=rates[fallback],
            converted=True, reason="default_display_currency", requested=None,
        )
    return PresentationCurrency(
        code=settlement.currency, pricing_currency=pricing, rate=settlement.rate,
        converted=settlement.converted, reason=settlement.reason, requested=None,
    )


def present(payload: Any, presentation: PresentationCurrency,
            source_currency: Optional[str] = None) -> Any:
    """Recursively convert declared money fields and restamp currency labels.

    Applied to the SERIALISED payload, so it works identically for a dict, a
    list of products, or a nested cart — one implementation, every read path.

    The currency label is restamped even on a no-op conversion: a payload that
    says ``USD`` while the shopper is browsing in USD is correct, and a payload
    that says ``USD`` while we failed to honour EGP is *also* correct. The lie
    we are removing is a label that disagrees with the numbers beside it.
    """
    if isinstance(payload, list):
        return [present(item, presentation, source_currency) for item in payload]
    if not isinstance(payload, (dict, Mapping)):
        return payload

    # A payload that declares its own currency is the authority on what its
    # numbers mean. Inheriting the enclosing declaration keeps nested items
    # (cart lines inside a cart) consistent with their parent.
    declared = None
    for key in _CURRENCY_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            declared = value.strip().upper()
            break
    source = declared or source_currency

    out: Dict[str, Any] = {}
    for key, value in payload.items():
        if key in MONEY_FIELDS and isinstance(value, (int, float, str, Decimal)) and not isinstance(value, bool):
            out[key] = presentation.convert(value, source)
        elif key in _CURRENCY_KEYS and isinstance(value, str):
            out[key] = presentation.code
        elif isinstance(value, (dict, list, Mapping)):
            out[key] = present(value, presentation, source)
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
        # Provenance: a rate nobody can date is a rate nobody can audit.
        "rate_source": rate_snapshot().source,
        "rate_as_of": rate_snapshot().as_of,
    }


def money_fields_of(*schemas: Iterable[Any]) -> Set[str]:  # pragma: no cover - test helper
    """Collect field names from pydantic models (used by the contract test)."""
    names: Set[str] = set()
    for schema in schemas:
        fields = getattr(schema, "model_fields", None) or {}
        names.update(fields.keys())
    return names
