"""Growth percentages must never be invented from an empty baseline.

MEASURED DEFECT (2026-10-20)
----------------------------
``_calculate_growth_rates`` mapped ``prev_val == 0`` to ``100.0`` whenever the
current value was positive. A brand in its first month — or one returning after
a month with no orders — was shown a green **"+100%"** on gross sales, net
sales, order count, units sold and AOV. Five success claims, all derived from a
denominator that does not exist.

Percentage growth from zero is undefined: ``(C - 0) / 0`` is not 100, it is
unbounded. The only honest representation is "no comparable baseline", and the
number must be ABSENT rather than large.

WHAT THESE TESTS PIN
--------------------
The full contract, including the cases the old code got right, so a future
"simplification" cannot quietly restore the old branch:

  P > 0            -> real percentage (increase, decrease, and flat)
  P == 0, C > 0    -> None,  basis "no_prior_baseline"
  P == 0, C == 0   -> None,  basis "no_activity"
  P or C missing   -> None,  basis "not_comparable"

``None`` means "not calculable". It never means zero, and no caller may render
it as a number.
"""
from __future__ import annotations

import pytest

from backend.app.services.business_intelligence_service import (
    BusinessIntelligenceService as BIS,
)

METRICS = ("gross_sales", "net_sales", "orders_count", "units_sold", "average_order_value")


def kpis(**over):
    base = {
        "gross_sales": 0.0,
        "net_sales": 0.0,
        "orders_count": 0,
        "units_sold": 0,
        "average_order_value": 0.0,
        "currency": "USD",
    }
    base.update(over)
    return base


# --------------------------------------------------------------------------
# The defect
# --------------------------------------------------------------------------
def test_zero_baseline_is_not_a_hundred_percent():
    """The exact regression: 0 -> positive must not claim +100%."""
    current = kpis(gross_sales=600.0, orders_count=1, units_sold=2, average_order_value=600.0)
    previous = kpis()

    growth = BIS._calculate_growth_rates(current, previous)

    assert growth["gross_sales_change_pct"] is None, "a change from zero has no percentage"
    assert growth["orders_count_change_pct"] is None
    assert growth["units_sold_change_pct"] is None
    assert 100.0 not in growth.values(), f"no metric may claim +100% from an empty baseline: {growth}"


def test_zero_baseline_basis_says_why():
    current = kpis(gross_sales=600.0)
    previous = kpis()

    basis = BIS._growth_basis(current, previous)

    assert basis["gross_sales"] == "no_prior_baseline"


def test_no_activity_in_either_period_is_distinct_from_no_baseline():
    """0 -> 0 is 'nothing happened', not 'undefined growth'."""
    basis = BIS._growth_basis(kpis(), kpis())
    growth = BIS._calculate_growth_rates(kpis(), kpis())

    assert basis["gross_sales"] == "no_activity"
    assert growth["gross_sales_change_pct"] is None


def test_missing_period_is_not_comparable():
    basis = BIS._growth_basis(kpis(gross_sales=10.0), {"gross_sales": None})
    growth = BIS._calculate_growth_rates(kpis(gross_sales=10.0), {"gross_sales": None})

    assert basis["gross_sales"] == "not_comparable"
    assert growth["gross_sales_change_pct"] is None


# --------------------------------------------------------------------------
# The behaviour that was already correct — must not regress
# --------------------------------------------------------------------------
def test_positive_baseline_increase():
    growth = BIS._calculate_growth_rates(kpis(gross_sales=600.0), kpis(gross_sales=300.0))
    assert growth["gross_sales_change_pct"] == 100.0


def test_positive_baseline_decrease():
    growth = BIS._calculate_growth_rates(kpis(gross_sales=150.0), kpis(gross_sales=300.0))
    assert growth["gross_sales_change_pct"] == -50.0


def test_positive_baseline_flat():
    growth = BIS._calculate_growth_rates(kpis(gross_sales=300.0), kpis(gross_sales=300.0))
    assert growth["gross_sales_change_pct"] == 0.0


def test_rounding_is_stable():
    growth = BIS._calculate_growth_rates(kpis(gross_sales=1000.0), kpis(gross_sales=3.0))
    assert growth["gross_sales_change_pct"] == round(((1000.0 - 3.0) / 3.0) * 100.0, 1)


def test_every_metric_is_reported():
    """No metric may silently disappear from the response contract."""
    growth = BIS._calculate_growth_rates(kpis(gross_sales=1.0), kpis(gross_sales=2.0))
    for metric in METRICS:
        assert f"{metric}_change_pct" in growth


def test_growth_map_stays_purely_numeric():
    """The CSV export and the chart layer iterate this map.

    An earlier draft of the fix nested a ``basis`` dict inside it, which would
    have put a mapping where both consumers expect a number (or None).
    """
    growth = BIS._calculate_growth_rates(kpis(gross_sales=5.0), kpis(gross_sales=1.0))
    assert "basis" not in growth
    for value in growth.values():
        assert value is None or isinstance(value, (int, float))
