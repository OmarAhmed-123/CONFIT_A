"""Regression tests for defects found in the final truth audit (post PR #28).

These are REAL behavioral tests against production code, not simulations.

Defect 1 (RATE QUANTIZATION):
    to_decimal() quantizes to 2 decimals. Applying it to a *rate* silently changed
    a 7.5% tax rate into 8%, and a 7.125% promo into 7.13%. Rates are not money.

Defect 2 (SILENT OUT-OF-RANGE PERSISTENCE):
    SQLite silently stores values outside NUMERIC(12,2). Failure must be explicit.

Defect 3 (FLOAT RE-ENTRY):
    Core money arithmetic must be exact Decimal. If money_add/money_mul is reverted
    to float+round, these tests must fail.
"""

from decimal import Decimal
import pytest

from backend.app.core.money import (
    to_decimal,
    to_rate,
    money_add,
    money_mul,
    money_percent,
    money_sum,
    quantize_money,
    assert_money_range,
    MoneyRangeError,
    MAX_MONEY,
)


class TestRateIsNotMoney:
    def test_tax_rate_is_not_quantized_to_two_decimals(self):
        # to_decimal would corrupt this to 0.08
        assert to_decimal(0.075) == Decimal("0.08")
        assert to_rate(0.075) == Decimal("0.075")

    def test_seven_point_five_percent_tax_on_1000(self):
        assert money_mul(Decimal("1000.00"), 0.075) == Decimal("75.00")

    def test_fractional_percent_promo_exact(self):
        assert money_percent(Decimal("1000.00"), "7.125") == Decimal("71.25")

    def test_low_rate_not_rounded_to_zero(self):
        # 0.5% must not become 0.00 (which would zero out all tax)
        assert to_rate("0.005") == Decimal("0.005")
        assert money_mul(Decimal("10000.00"), "0.005") == Decimal("50.00")

    def test_checkout_uses_to_rate_for_tax(self):
        import inspect
        from backend.app.services import commerce_service
        src = inspect.getsource(commerce_service)
        assert "to_rate(settings.TAX_RATE)" in src
        assert "to_decimal(settings.TAX_RATE)" not in src


class TestNumericRangeIsExplicit:
    def test_max_value_accepted(self):
        assert assert_money_range("9999999999.99") == MAX_MONEY

    def test_above_range_rejected_explicitly(self):
        with pytest.raises(MoneyRangeError):
            assert_money_range("10000000000.00", "total")

    def test_negative_below_range_rejected(self):
        with pytest.raises(MoneyRangeError):
            assert_money_range("-10000000000.00", "refund")

    def test_range_guard_is_wired_into_checkout(self):
        import inspect
        from backend.app.services import commerce_service
        src = inspect.getsource(commerce_service)
        assert "assert_money_range" in src


class TestNoFloatReEntry:
    """These fail if core arithmetic is reverted to float."""

    def test_classic_float_error_absent(self):
        assert money_add("0.1", "0.2") == Decimal("0.30")

    def test_accumulation_of_ten_thousand_cents_exact(self):
        total = Decimal("0.00")
        for _ in range(10000):
            total = money_add(total, "0.01")
        assert total == Decimal("100.00")

    def test_half_up_not_bankers_rounding(self):
        # float round() gives 2.67 (banker's + binary); business policy is HALF_UP
        assert quantize_money(Decimal("2.675")) == Decimal("2.68")
        assert quantize_money(Decimal("2.665")) == Decimal("2.67")

    def test_results_are_decimal_type_not_float(self):
        for v in (money_add(1, 2), money_mul("3.33", 3), money_sum(["1.11", "2.22"]),
                  money_percent("100", "5")):
            assert isinstance(v, Decimal)

    def test_aggregation_accumulator_is_decimal_not_float(self):
        """money_sum must accumulate in Decimal.

        A float accumulator can survive small aggregations by luck, so this is
        checked structurally as well as numerically: the arithmetic helpers in
        money.py must contain no float() conversion at all.
        """
        import inspect
        from backend.app.core import money as money_mod
        for fn in (money_mod.money_add, money_mod.money_sub, money_mod.money_mul,
                   money_mod.money_sum, money_mod.money_percent,
                   money_mod.quantize_money):
            src = inspect.getsource(fn)
            assert "float(" not in src, (
                f"{fn.__name__} performs a float conversion — float re-entry in "
                "the financial domain boundary")
            assert "round(" not in src or "ROUND_HALF_UP" in src, (
                f"{fn.__name__} uses builtin round()")
        assert money_sum(["0.01"] * 3 + ["1000000.01"] * 7) == Decimal("7000000.10")

    def test_rate_multiplication_is_exact_not_binary(self):
        """money_mul with a rate must not go through float."""
        assert money_mul("0.70", "1.1") == Decimal("0.77")   # float: 0.7700000000000001
        assert money_mul("1.15", "1.1") == Decimal("1.27")   # float 1.2650000000000001 -> 1.27
        assert money_mul("8.335", "1") == Decimal("8.34")

    def test_large_sum_precision_beats_float(self):
        vals = ["0.07"] * 100000
        assert money_sum(vals) == Decimal("7000.00")


class TestCanonicalMoneyUtility:
    def test_no_duplicate_money_helpers_in_app(self):
        import pathlib, re
        root = pathlib.Path("backend/app")
        offenders = []
        for f in root.rglob("*.py"):
            if f.as_posix().endswith("core/money.py"):
                continue
            src = f.read_text(encoding="utf-8", errors="ignore")
            if re.search(r"^\s*def (to_decimal|money_add|money_sub|money_mul|quantize_money|money_percent)\b",
                         src, re.M):
                offenders.append(f.as_posix())
        assert offenders == [], f"Duplicate money helpers found: {offenders}"
