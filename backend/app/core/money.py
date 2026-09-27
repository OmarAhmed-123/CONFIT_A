"""
Money domain utilities — exact Decimal arithmetic for financial integrity

All monetary values in CONFIT_A are stored as Numeric(12,2) → Python Decimal.
This module ensures:
- No accidental float + Decimal mixing
- Exact arithmetic with quantize to 2 decimals, ROUND_HALF_UP
- Safe conversion from various inputs (Decimal, int, float, str, None)
- Serialization helpers

Precision: 12,2 means max 10 digits before decimal, 2 after.
Max value: 9,999,999,999.99 (10 digits) — sufficient for luxury fashion orders.
Min value: 0.01 (for most), but some allow 0.0.

Non-money Floats remain float: rating, latitude, longitude, body_scaling, height, ai_confidence etc.

Usage:
    from backend.app.core.money import to_decimal, money_add, money_mul, money_sub, quantize_money

    price = to_decimal(product.base_price)  # Decimal
    line_sub = money_mul(price, quantity)  # Decimal quantized to 2 decimals
    subtotal = money_add(subtotal, line_sub)
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation, getcontext
from typing import List, Optional, Sequence, Union

# Set high precision for intermediate calculations, final quantized to 2 decimals
getcontext().prec = 28

MoneyInput = Union[Decimal, int, float, str, None]

TWOPLACES = Decimal("0.01")
MAX_MONEY = Decimal("9999999999.99")
MIN_MONEY = Decimal("-9999999999.99")


class MoneyRangeError(ValueError):
    """Raised when a monetary value exceeds NUMERIC(12,2) representable range."""


class MoneyValueError(ValueError):
    """Raised when a value cannot be interpreted as a finite monetary amount
    (NaN, ±Infinity, unparseable text, unsupported types).

    Domain-level rejection: this fires BEFORE any ORM assignment, so a corrupt
    amount can never reach PostgreSQL (which would raise) or SQLite (which
    would silently store garbage).
    """


def _finite_decimal(value, field: str = "amount") -> Decimal:
    """Parse to a FINITE Decimal or raise MoneyValueError. Never returns 0.00
    as a stand-in for garbage — silent coercion is a financial defect."""
    if isinstance(value, bool):
        raise MoneyValueError(f"{field}: boolean is not a monetary amount")
    if isinstance(value, Decimal):
        dec = value
    elif isinstance(value, int):
        dec = Decimal(value)
    elif isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise MoneyValueError(f"{field}: non-finite float {value!r} rejected")
        # str() round-trip avoids binary float error: Decimal(0.1) != Decimal("0.1")
        dec = Decimal(str(value))
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise MoneyValueError(f"{field}: empty string is not a monetary amount")
        try:
            dec = Decimal(text)
        except (InvalidOperation, ValueError) as exc:
            raise MoneyValueError(f"{field}: {value!r} is not a valid monetary amount") from exc
    else:
        try:
            dec = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise MoneyValueError(f"{field}: unsupported type {type(value).__name__}") from exc
    if not dec.is_finite():
        raise MoneyValueError(f"{field}: non-finite value {dec} rejected")
    return dec


def to_decimal(value: MoneyInput, field: str = "amount") -> Decimal:
    """Convert any money input to Decimal safely, without float binary errors.

    - None → Decimal("0.00")   (absent optional amount; callers that must not
      accept None use validate_money(..., required=True))
    - Decimal / int / float / numeric str → quantized to 2 decimals, ROUND_HALF_UP
    - NaN, ±Infinity, unparseable text, bool → MoneyValueError (never 0.00)
    """
    if value is None:
        return Decimal("0.00")
    dec = _finite_decimal(value, field)
    try:
        return dec.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        # Magnitude beyond the 28-digit context (e.g. "1e400"): cannot be money.
        raise MoneyRangeError(
            f"{field}={dec} exceeds NUMERIC(12,2) range [{MIN_MONEY}, {MAX_MONEY}]"
        ) from exc


def to_rate(value: MoneyInput, field: str = "rate") -> Decimal:
    """Convert a RATE/PERCENT to exact Decimal WITHOUT 2-decimal quantization.

    Rates (tax rate 0.075, discount percent 7.125) are NOT money and must never be
    quantized to 2 decimals — doing so turns a 7.5% tax rate into 8%.
    Only the monetary RESULT of applying a rate is quantized.
    Non-finite / unparseable rates raise MoneyValueError (never coerced to 0).
    """
    if value is None:
        return Decimal("0")
    return _finite_decimal(value, field)


def assert_money_range(value: MoneyInput, field: str = "amount") -> Decimal:
    """Explicitly reject values outside NUMERIC(12,2).

    SQLite silently stores out-of-range values; PostgreSQL raises. This makes the
    failure explicit and identical on both backends, so persistence can never
    truncate or corrupt a monetary value silently.
    """
    dec = to_decimal(value, field)
    if dec > MAX_MONEY or dec < MIN_MONEY:
        raise MoneyRangeError(
            f"{field}={dec} exceeds NUMERIC(12,2) range [{MIN_MONEY}, {MAX_MONEY}]"
        )
    return dec


def validate_money(
    value: MoneyInput,
    field: str = "amount",
    *,
    allow_negative: bool = False,
    allow_zero: bool = True,
    required: bool = False,
    exact_scale: bool = False,
) -> Optional[Decimal]:
    """Canonical DOMAIN validation for a monetary input before persistence.

    Field-specific sign rules are expressed by the caller:
      prices / budgets / bids  -> allow_negative=False, allow_zero=False
      refunds / subtotals      -> allow_negative=False, allow_zero=True
      exchange price_delta     -> allow_negative=True
    Rejects NaN/Infinity/garbage (MoneyValueError) and values outside
    NUMERIC(12,2) (MoneyRangeError). Returns None for an absent optional value.

    ``exact_scale=True`` is for USER-SUPPLIED amounts (API bodies, query
    params, CSV cells): a value with sub-cent precision (0.005, 12.345) is
    rejected instead of being silently rounded — a bid of 0.005 that is
    charged as 0.01 is a financial defect, not a convenience.
    """
    if value is None:
        if required:
            raise MoneyValueError(f"{field} is required")
        return None
    dec = assert_money_range(value, field)
    if exact_scale:
        raw = _finite_decimal(value, field)
        if raw != dec:
            raise MoneyValueError(
                f"{field} must have at most 2 decimal places (got {raw})"
            )
    if not allow_negative and dec < Decimal("0.00"):
        raise MoneyValueError(f"{field} must not be negative (got {dec})")
    if not allow_zero and dec == Decimal("0.00"):
        raise MoneyValueError(f"{field} must be greater than zero")
    return dec


def quantize_money(value: Decimal) -> Decimal:
    """Quantize to 2 decimals with ROUND_HALF_UP (standard financial rounding)."""
    if not isinstance(value, Decimal):
        value = to_decimal(value)
    return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def money_add(a: MoneyInput, b: MoneyInput) -> Decimal:
    """Add two money values with exact Decimal arithmetic."""
    return quantize_money(to_decimal(a) + to_decimal(b))


def money_sub(a: MoneyInput, b: MoneyInput) -> Decimal:
    """Subtract b from a with exact Decimal arithmetic."""
    return quantize_money(to_decimal(a) - to_decimal(b))


def money_mul(a: MoneyInput, b: Union[int, float, Decimal, str]) -> Decimal:
    """Multiply money by quantity (int) or rate (Decimal/float) with exact arithmetic.
    
    For quantity: price * qty
    For percent: eligible * (discount_percent / 100)
    """
    dec_a = to_decimal(a)
    if isinstance(b, int):
        return quantize_money(dec_a * Decimal(b))
    # b is a rate/multiplier: must NOT be quantized to 2 decimals (0.075 -> 0.08 bug)
    dec_b = to_rate(b)
    return quantize_money(dec_a * dec_b)


def money_percent(base: MoneyInput, percent: MoneyInput) -> Decimal:
    """Calculate percent of base: base * (percent / 100) with exact arithmetic."""
    dec_base = to_decimal(base)
    dec_percent = to_rate(percent)
    return quantize_money(dec_base * dec_percent / Decimal("100"))


def money_min(a: MoneyInput, b: MoneyInput) -> Decimal:
    """Min of two money values."""
    dec_a = to_decimal(a)
    dec_b = to_decimal(b)
    return dec_a if dec_a <= dec_b else dec_b


def money_max(a: MoneyInput, b: MoneyInput) -> Decimal:
    """Max of two money values, floored at 0."""
    dec_a = to_decimal(a)
    dec_b = to_decimal(b)
    result = dec_a if dec_a >= dec_b else dec_b
    return quantize_money(result if result >= Decimal("0") else Decimal("0.00"))


def money_sum(values) -> Decimal:
    """Sum iterable of money values with exact arithmetic."""
    total = Decimal("0.00")
    for v in values:
        total += to_decimal(v)
    return quantize_money(total)


def to_float(value: MoneyInput) -> float:
    """Convert Decimal to float for JSON serialization (2 decimals).
    
    Authoritative calculation remains Decimal, serialization as float for frontend.
    Frontend must never be source of truth — server is authoritative.
    """
    return float(quantize_money(to_decimal(value)))


def to_str(value: MoneyInput) -> str:
    """Convert to string with 2 decimals for exact serialization if needed."""
    return str(quantize_money(to_decimal(value)))


# Regression helpers for tests
def is_decimal(value) -> bool:
    """Check if value is Decimal (exact) not float."""
    return isinstance(value, Decimal)


# =========================================================================
# Proportional allocation
# =========================================================================

def allocate_proportionally(
    total: MoneyInput,
    weights: Sequence[MoneyInput],
) -> List[Decimal]:
    """Split ``total`` across ``weights`` so the parts sum to it EXACTLY.

    WHY THIS EXISTS
    ---------------
    An order-level discount is a single number, but every consumer of it needs
    it per line: a brand must know the discount borne by ITS items, a refund
    must return what was actually paid for the unit, and tax is owed on the
    discounted amount. Splitting naively is where money goes missing.

    THE FAILURE THIS PREVENTS
    -------------------------
    ``round(total * weight / sum_weights)`` per line does not re-sum to
    ``total``. Splitting 10.00 across three equal lines yields 3.33 * 3 = 9.99
    and one cent evaporates; with ROUND_HALF_UP it can instead yield 10.01 and
    a cent is conjured. Over many orders this is a real, compounding
    discrepancy between the customer's total and the sum of brand statements,
    and it is the kind of drift that surfaces as an unreconcilable ledger.

    THE ALGORITHM — LARGEST REMAINDER METHOD
    ----------------------------------------
    Work in integer minor units (cents), never floats:

    1. For each weight, compute ``total_cents * weight / sum_weights`` and keep
       the integer quotient and the fractional remainder.
    2. The quotients under-allocate by some whole number of cents, because each
       was floored.
    3. Hand those leftover cents out one at a time, to the lines with the
       largest remainders first.

    Each line's share is therefore within one cent of its exact proportional
    share, and the parts sum to ``total`` by construction rather than by luck.
    This is the method used for payroll, dividend distribution and seat
    apportionment, and it is what Square, TaxCloud and Drupal Commerce all use
    to apportion an order-level discount across line items.

    Ties are broken by ascending index, so the result is DETERMINISTIC. That
    matters: the same order must allocate identically on re-computation, or a
    brand statement would change between reads.

    EDGE CASES (all deliberate)
    ---------------------------
    - ``weights`` empty              -> ``[]``
    - ``total`` is 0                 -> all zeros
    - every weight is 0              -> split EQUALLY. A zero-weight basket
      still has to absorb the whole discount somewhere, and refusing would
      lose it. Proportionality is undefined, so equal is the honest fallback.
    - a single non-zero weight       -> that line takes the entire total

    Args:
        total: The amount to split. Must be non-negative.
        weights: Relative sizes, normally each line's subtotal. Must be
            non-negative.

    Returns:
        One Decimal per weight, each quantized to 2 places, summing exactly to
        ``quantize_money(total)``.

    Raises:
        ValueError: if ``total`` or any weight is negative.
    """
    total_dec = quantize_money(to_decimal(total, "total"))
    if total_dec < 0:
        raise ValueError(
            f"allocate_proportionally: total must be non-negative, got {total_dec}"
        )

    weight_decs = [to_decimal(w, "weight") for w in weights]
    for i, w in enumerate(weight_decs):
        if w < 0:
            raise ValueError(
                f"allocate_proportionally: weight[{i}] must be non-negative, got {w}"
            )

    n = len(weight_decs)
    if n == 0:
        return []

    # Integer cents throughout. Decimal is exact, but integers make the
    # conservation property trivially checkable.
    total_cents = int((total_dec * 100).to_integral_value(rounding=ROUND_HALF_UP))
    if total_cents == 0:
        return [Decimal("0.00")] * n

    weight_cents = [
        int((w * 100).to_integral_value(rounding=ROUND_HALF_UP)) for w in weight_decs
    ]
    sum_weights = sum(weight_cents)

    if sum_weights == 0:
        # Proportionality is undefined; split equally and give the remainder to
        # the earliest lines so the total is still conserved.
        base, leftover = divmod(total_cents, n)
        cents = [base + (1 if i < leftover else 0) for i in range(n)]
        return [(Decimal(c) / 100).quantize(TWOPLACES) for c in cents]

    quotients: List[int] = []
    remainders: List[tuple] = []  # (remainder, index)
    for i, w in enumerate(weight_cents):
        numerator = total_cents * w
        q, r = divmod(numerator, sum_weights)
        quotients.append(q)
        remainders.append((r, i))

    leftover = total_cents - sum(quotients)

    # Largest remainder first; ties resolved by ascending index for determinism.
    remainders.sort(key=lambda pair: (-pair[0], pair[1]))
    for k in range(leftover):
        quotients[remainders[k][1]] += 1

    allocation = [(Decimal(c) / 100).quantize(TWOPLACES) for c in quotients]

    # Conservation is the whole point of this function; assert it rather than
    # trusting the arithmetic above.
    if sum(allocation) != total_dec:
        raise AssertionError(
            f"allocate_proportionally broke conservation: "
            f"sum({allocation}) != {total_dec}"
        )
    return allocation
