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

from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Union, Optional

# Set high precision for intermediate calculations, final quantized to 2 decimals
getcontext().prec = 28

MoneyInput = Union[Decimal, int, float, str, None]

TWOPLACES = Decimal("0.01")


def to_decimal(value: MoneyInput) -> Decimal:
    """Convert any money input to Decimal safely, without float binary errors.
    
    - None → Decimal("0.00")
    - Decimal → quantized to 2 decimals
    - int → Decimal(int)
    - float → Decimal(str(float)) to avoid binary representation error (e.g., 0.1)
    - str → Decimal(str)
    
    All results quantized to 2 decimals with ROUND_HALF_UP.
    """
    if value is None:
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return quantize_money(value)
    if isinstance(value, int):
        return Decimal(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    if isinstance(value, float):
        # Convert via str to avoid binary float error: Decimal(0.1) != Decimal("0.1")
        return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    if isinstance(value, str):
        try:
            return Decimal(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        except Exception:
            return Decimal("0.00")
    # Fallback
    try:
        return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


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
    dec_b = to_decimal(b)
    return quantize_money(dec_a * dec_b)


def money_percent(base: MoneyInput, percent: MoneyInput) -> Decimal:
    """Calculate percent of base: base * (percent / 100) with exact arithmetic."""
    dec_base = to_decimal(base)
    dec_percent = to_decimal(percent)
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
