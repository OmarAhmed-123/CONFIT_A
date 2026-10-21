"""Catalog price normalisation: a brand's currency → the price book's currency.

WHY THIS EXISTS AND WHY IT IS THIS SMALL
----------------------------------------
The importer refuses a row priced in anything other than ``PRICING_CURRENCY``
(USD), and it refuses it for a measured reason: a row priced in EGP was stored
as ``1450.00`` with ``currency='EGP'``; the product page then rendered
"1,450 EGP" from that label while the cart converted the SAME NUMBER out of the
USD price book and rendered 78,166.03 EGP. One product, two prices, ~53x apart,
and the shopper is charged the second one.

Refusing was the correct stopgap. This module is the resolution: convert the
row ONCE, at import, into the price book's denomination, and keep enough
provenance that the conversion can be audited and reproduced.

THE RATE SOURCE IS NOT NEW
--------------------------
It is the project's existing, single FX authority — ``services/fx_rates.py`` —
which is also what stamps ``orders.fx_rate_used`` at checkout. That is the whole
point: catalogue normalisation and order settlement read the same provider, so
they agree by construction and there is no second table to drift.

``orders.fx_rate_used`` itself is a *snapshot*, not a rate-acquisition
mechanism: it records the rate a particular order was priced at, forever. Using
the last order's stored rate for a new catalogue import would price today's
stock at an arbitrary past moment with no freshness control — so this module
reads the provider directly and never reads an order row.

DIRECTION (verified in code, not assumed)
-----------------------------------------
``MarketSettlement.fx_rates()`` documents its table as "Rates FROM the pricing
currency, e.g. {"EGP": "52.09"}", i.e. **1 USD = 52.09 EGP**. So converting an
EGP amount into the price book is a DIVISION by that number:

    amount_usd = amount_egp / 52.09

``CatalogRate.provider_rate`` keeps the published number (52.09) and
``CatalogRate.multiplier`` keeps ``1/52.09``; both are stored so the arithmetic
can be re-derived from the database without guessing which way round it went.

FAIL CLOSED
-----------
No rate, a non-positive or non-finite rate, an unparseable table, or a source
this module does not trust ⇒ :class:`RateUnavailable`. The importer turns that
into a per-row error telling the brand what is missing. Nothing here ever
invents a rate, falls back to 1.0, or converts "approximately".

FRESHNESS POLICY (explicit, because silence here misprices a catalogue)
-----------------------------------------------------------------------
Accepted: ``live`` (fetched from the provider within its TTL) and
``configured`` (the treasury's ``MARKET_FX_RATES`` table — an operator statement
of policy, which is why it is trusted).

Rejected: ``stale_live`` (a cached snapshot past its TTL, served because the
provider is unreachable) and ``unavailable``.

This is deliberately STRICTER than checkout, which degrades to a stale rate so a
shopper is never blocked. The asymmetry is intentional: checkout converts one
order and records exactly what it used, while a catalogue import writes
permanent prices onto a whole product range in one action. A stale rate there is
not a degraded experience, it is a wrong price list that nobody revisits. An
operator who needs to import during a provider outage sets ``MARKET_FX_RATES``
— an explicit, auditable act — rather than the system quietly using yesterday's
number.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from email.utils import parsedate_to_datetime
from typing import Optional

from backend.app.core.config import settings
from backend.app.core.logging import logger

#: Money is quantized to 2 decimals, ROUND_HALF_UP — the convention `core/money.py`
#: already applies everywhere else. Reusing it is what keeps a converted price
#: and a cart line computed from that price in the same currency to the cent.
TWOPLACES = Decimal("0.01")

#: Sources this module will convert with. See the module docstring for why
#: ``stale_live`` is excluded here and included at checkout.
TRUSTED_SOURCES = ("live", "configured")

#: Default maximum age (seconds) of a rate publication timestamp (`as_of`) accepted
#: during catalogue price conversion (48h covers weekend publication windows).
DEFAULT_MAX_RATE_AGE_SECONDS = 172800


def _parse_as_of(raw: Optional[str]) -> datetime:
    """Parse RFC-2822 or ISO-8601 publication timestamp into timezone-aware UTC."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty timestamp")
    dt: Optional[datetime] = None
    try:
        iso = text[:-1] + "+00:00" if text.endswith("Z") else text
        dt = datetime.fromisoformat(iso)
    except ValueError:
        try:
            dt = parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError) as exc:
            raise ValueError(f"unparseable timestamp {text!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class RateUnavailable(Exception):
    """No trustworthy rate exists for this currency. Never converted around."""

    def __init__(self, message: str, *, reason: str, currency: str = ""):
        super().__init__(message)
        self.reason = reason
        self.currency = currency

    def to_dict(self):
        return {"reason": self.reason, "currency": self.currency, "message": str(self)}


@dataclass(frozen=True)
class CatalogRate:
    """One verified conversion, with everything needed to reproduce it."""

    source_currency: str
    pricing_currency: str
    #: The number the provider published: PRICING → SOURCE (1 USD = 52.09 EGP).
    provider_rate: Decimal
    #: Applied multiplier: SOURCE → PRICING (1 EGP = 0.0192… USD).
    multiplier: Decimal
    #: ``live`` | ``configured``
    source: str
    #: Provider publication time, when it stated one.
    as_of: Optional[str] = None
    #: Measured age in seconds at conversion time when ``as_of`` is present.
    age_seconds: Optional[float] = None

    def convert(self, amount: Decimal, field: str = "amount") -> Decimal:
        """Convert one positive ``Decimal`` amount into the price book currency.

        The division is done in Decimal at the context precision and only the
        MONEY result is quantized — quantizing the multiplier first would
        compound a rounding error across every row in the file.
        """
        if not isinstance(amount, Decimal):
            try:
                amount = Decimal(str(amount))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise RateUnavailable(
                    f"{field} is not a decimal amount: {amount!r}",
                    reason="amount_not_decimal", currency=self.source_currency,
                ) from exc
        converted = amount * self.multiplier
        return converted.quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    def provenance(self) -> dict:
        """The audit record persisted alongside a converted product."""
        return {
            "price_source_currency": self.source_currency,
            "price_fx_rate": str(self.provider_rate),
            "price_fx_source": self.source,
            "price_fx_as_of": self.as_of,
        }

    def describe(self) -> str:
        """One human sentence for a preview screen or an error message."""
        where = self.source if not self.as_of else f"{self.source} @ {self.as_of}"
        return (f"1 {self.pricing_currency} = {self.provider_rate} "
                f"{self.source_currency} ({where})")


def _provider_snapshot():
    """The shared provider instance. Imported lazily so tests can monkeypatch it."""
    from backend.app.services.fx_rates import fx_rates

    return fx_rates.snapshot()


def resolve_rate(source_currency: str, pricing_currency: Optional[str] = None,
                 *, snapshot=None, max_age_seconds: Optional[int] = None,
                 now: Optional[datetime] = None) -> CatalogRate:
    """Resolve a verified SOURCE → PRICING conversion, or raise.

    ``snapshot`` is injectable so a test can state a rate instead of reaching
    the network. It is NOT a production path: nothing in the application passes
    it, and the value it accepts is a real :class:`RateSnapshot`.
    """
    from backend.app.providers.payment.capability_registry import MarketSettlement

    pricing = (pricing_currency or MarketSettlement.pricing_currency() or "").strip().upper()
    source = (source_currency or "").strip().upper()

    if not source or len(source) != 3 or not source.isalpha():
        raise RateUnavailable(
            f'"{source_currency}" is not a three-letter currency code',
            reason="currency_malformed", currency=source,
        )
    if source == pricing:
        # Same denomination: nothing to convert, and saying so is not a
        # conversion. The caller still gets a rate object so one code path
        # handles both cases.
        return CatalogRate(
            source_currency=source, pricing_currency=pricing,
            provider_rate=Decimal("1"), multiplier=Decimal("1"), source="identity",
        )

    snap = snapshot if snapshot is not None else _provider_snapshot()

    if snap is None or getattr(snap, "is_empty", True):
        raise RateUnavailable(
            f"No exchange rate is available to convert {source} into {pricing}. "
            f"Nothing was imported at a guessed rate. An operator must configure "
            f"market FX (MARKET_FX_RATES) or restore the rate provider.",
            reason="rate_table_unavailable", currency=source,
        )
    if getattr(snap, "source", "unavailable") not in TRUSTED_SOURCES:
        raise RateUnavailable(
            f"The {source}→{pricing} rate is {getattr(snap, 'source', 'unknown')!r}, which this "
            f"import does not convert with: a catalogue import writes permanent prices, so it "
            f"will only use a live rate or an operator-configured one. Publish prices in "
            f"{pricing}, or have an operator set MARKET_FX_RATES for {source}.",
            reason=f"rate_source_not_trusted:{getattr(snap, 'source', 'unknown')}",
            currency=source,
        )
    if getattr(snap, "base", "").upper() != pricing:
        # A table denominated in something else would silently skew every
        # conversion — e.g. reading EUR-based rates as USD-based.
        raise RateUnavailable(
            f"The rate table is denominated in {getattr(snap, 'base', '?')}, but the price book "
            f"is {pricing}; converting would skew every price.",
            reason="rate_base_mismatch", currency=source,
        )

    published = (snap.rates or {}).get(source)
    if published is None:
        raise RateUnavailable(
            f"No {source} rate is published by the current rate source. Publish prices in "
            f"{pricing}, or have an operator add a {source} rate.",
            reason="rate_not_published", currency=source,
        )
    if not isinstance(published, Decimal):
        try:
            published = Decimal(str(published))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise RateUnavailable(
                f"The published {source} rate is not a number.",
                reason="rate_malformed", currency=source,
            ) from exc
    if not published.is_finite() or published <= 0:
        raise RateUnavailable(
            f"The published {source} rate ({published}) is not a positive finite number.",
            reason="rate_non_positive", currency=source,
        )

    raw_as_of = getattr(snap, "as_of", None)
    measured_age: Optional[float] = None
    max_age = (
        int(max_age_seconds)
        if max_age_seconds is not None
        else int(getattr(settings, "FX_MAX_AGE_SECONDS", DEFAULT_MAX_RATE_AGE_SECONDS))
    )
    if max_age <= 0:
        raise RateUnavailable(
            f"Configured FX_MAX_AGE_SECONDS ({max_age}) must be positive.",
            reason="rate_policy_invalid", currency=source,
        )
    if raw_as_of is not None:
        try:
            published_dt = _parse_as_of(str(raw_as_of))
        except ValueError as exc:
            raise RateUnavailable(
                f"The {source} rate carries an unparseable timestamp ({raw_as_of!r}).",
                reason="rate_timestamp_malformed", currency=source,
            ) from exc
        ref_now = now.astimezone(timezone.utc) if now is not None else datetime.now(timezone.utc)
        measured_age = (ref_now - published_dt).total_seconds()
        if measured_age > max_age:
            raise RateUnavailable(
                f"The {source}→{pricing} rate published at {raw_as_of} is stale "
                f"({int(measured_age)}s old > max {max_age}s). Refresh the live feed "
                f"or update MARKET_FX_RATES before importing.",
                reason="rate_stale", currency=source,
            )

    multiplier = Decimal("1") / published
    rate = CatalogRate(
        source_currency=source, pricing_currency=pricing,
        provider_rate=published, multiplier=multiplier,
        source=getattr(snap, "source", "unknown"),
        as_of=raw_as_of,
        age_seconds=measured_age,
    )
    logger.info(
        "catalog_fx_rate_resolved",
        source_currency=source, pricing_currency=pricing,
        provider_rate=str(published), rate_source=rate.source, as_of=rate.as_of,
    )
    return rate
