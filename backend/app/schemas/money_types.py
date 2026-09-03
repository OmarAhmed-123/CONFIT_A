"""Pydantic boundary types for monetary API inputs.

These are thin adapters: every rule is delegated to the canonical domain
validator ``backend.app.core.money.validate_money`` so the API boundary and
the domain layer can never disagree (no second implementation of money
rules). A rejected value surfaces as a normal pydantic validation error
(HTTP 422) *before* any service/repository code runs.

    PositiveMoney      prices, bids, budgets, BNPL amounts  (> 0)
    NonNegativeMoney   optional preference budgets, purchase prices (>= 0)
    SignedMoney        deltas that may legitimately be negative

All three reject NaN, ±Infinity, unparseable text, booleans, values outside
NUMERIC(12,2) (|x| > 9,999,999,999.99) and sub-cent precision (0.005).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Optional

from pydantic import BeforeValidator

from backend.app.core.money import MoneyRangeError, MoneyValueError, validate_money


def _money_validator(*, allow_negative: bool, allow_zero: bool):
    def _validate(value):
        if value is None:
            return None
        try:
            return validate_money(
                value,
                "amount",
                allow_negative=allow_negative,
                allow_zero=allow_zero,
                exact_scale=True,
            )
        except (MoneyValueError, MoneyRangeError) as exc:
            # pydantic converts ValueError into a field validation error
            raise ValueError(str(exc)) from exc

    return _validate


PositiveMoney = Annotated[Decimal, BeforeValidator(_money_validator(allow_negative=False, allow_zero=False))]
NonNegativeMoney = Annotated[Decimal, BeforeValidator(_money_validator(allow_negative=False, allow_zero=True))]
SignedMoney = Annotated[Decimal, BeforeValidator(_money_validator(allow_negative=True, allow_zero=True))]

OptionalPositiveMoney = Optional[PositiveMoney]
OptionalNonNegativeMoney = Optional[NonNegativeMoney]
