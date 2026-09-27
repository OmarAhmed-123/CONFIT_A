"""Proportional allocation — conservation and fairness.

The single property that matters: THE PARTS MUST SUM TO THE WHOLE. Every other
assertion here supports that one. A discount that does not re-sum is money that
either vanishes from a brand statement or is invented on a customer refund, and
the discrepancy is silent — nothing throws, the ledger is just wrong.

The randomised cases at the bottom are the real proof. The hand-written ones
document the specific shapes that break naive implementations.
"""
from __future__ import annotations

import random
from decimal import Decimal

import pytest

from backend.app.core.money import allocate_proportionally, quantize_money


D = Decimal


# ── The classic failures of naive rounding ─────────────────────────────────

def test_ten_across_three_equal_lines_loses_no_cent():
    """10.00 / 3 = 3.333…  Round each and you get 9.99 or 10.01, never 10.00."""
    parts = allocate_proportionally(D("10.00"), [D("1"), D("1"), D("1")])
    assert sum(parts) == D("10.00")
    assert sorted(parts) == [D("3.33"), D("3.33"), D("3.34")]


def test_one_cent_across_three_lines_goes_somewhere():
    """A single indivisible cent must still be allocated, not dropped."""
    parts = allocate_proportionally(D("0.01"), [D("50"), D("30"), D("20")])
    assert sum(parts) == D("0.01")
    # It goes to the largest weight, which has the largest remainder.
    assert parts == [D("0.01"), D("0.00"), D("0.00")]


def test_allocation_is_proportional_not_equal():
    """An 80/20 basket must absorb the discount 80/20."""
    parts = allocate_proportionally(D("15.00"), [D("80.00"), D("20.00")])
    assert parts == [D("12.00"), D("3.00")]
    assert sum(parts) == D("15.00")


def test_worked_example_from_taxcloud_documentation():
    """Cross-check against a published, independent worked example.

    TaxCloud documents a 10.00 order discount over lines of 90.00 and 50.00
    splitting 64.3% / 35.7%.
    """
    parts = allocate_proportionally(D("10.00"), [D("90.00"), D("50.00")])
    assert sum(parts) == D("10.00")
    assert parts == [D("6.43"), D("3.57")]


# ── Edge cases ─────────────────────────────────────────────────────────────

def test_empty_weights_returns_empty():
    assert allocate_proportionally(D("10.00"), []) == []


def test_zero_total_allocates_zero_to_every_line():
    parts = allocate_proportionally(D("0.00"), [D("10"), D("20"), D("30")])
    assert parts == [D("0.00")] * 3
    assert sum(parts) == D("0.00")


def test_all_zero_weights_split_equally_rather_than_losing_the_money():
    """Proportionality is undefined here, but the total must survive."""
    parts = allocate_proportionally(D("10.00"), [D("0"), D("0"), D("0")])
    assert sum(parts) == D("10.00")
    assert sorted(parts) == [D("3.33"), D("3.33"), D("3.34")]


def test_single_nonzero_weight_absorbs_everything():
    parts = allocate_proportionally(D("7.77"), [D("0"), D("5.00"), D("0")])
    assert parts == [D("0.00"), D("7.77"), D("0.00")]


def test_single_line_gets_the_whole_discount():
    assert allocate_proportionally(D("42.42"), [D("99.99")]) == [D("42.42")]


def test_negative_total_is_rejected():
    """A discount is a positive magnitude; the sign lives at the call site."""
    with pytest.raises(ValueError, match="non-negative"):
        allocate_proportionally(D("-1.00"), [D("10")])


def test_negative_weight_is_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        allocate_proportionally(D("1.00"), [D("10"), D("-5")])


# ── Determinism ────────────────────────────────────────────────────────────

def test_identical_weights_allocate_deterministically():
    """Re-reading a brand statement must not change the numbers."""
    first = allocate_proportionally(D("10.00"), [D("1"), D("1"), D("1")])
    for _ in range(20):
        assert allocate_proportionally(D("10.00"), [D("1"), D("1"), D("1")]) == first
    # Ties break toward the earliest line.
    assert first == [D("3.34"), D("3.33"), D("3.33")]


# ── The property that actually matters, over random input ──────────────────

@pytest.mark.parametrize("seed", range(40))
def test_conservation_holds_for_random_baskets(seed):
    """Sum of parts == total, for arbitrary totals and line counts."""
    rng = random.Random(seed)
    n = rng.randint(1, 12)
    weights = [D(rng.randrange(0, 500_00)) / 100 for _ in range(n)]
    total = D(rng.randrange(0, 1_000_00)) / 100

    parts = allocate_proportionally(total, weights)

    assert len(parts) == n
    assert sum(parts) == quantize_money(total), (
        f"conservation broken: seed={seed} total={total} weights={weights}"
    )
    assert all(p >= 0 for p in parts), "no line may receive a negative share"


@pytest.mark.parametrize("seed", range(40))
def test_each_share_is_within_one_cent_of_its_exact_share(seed):
    """Fairness bound: largest-remainder guarantees error < 1 cent per line.

    Without this, conservation alone could be satisfied by dumping the entire
    remainder on one unlucky line.
    """
    rng = random.Random(1000 + seed)
    n = rng.randint(2, 10)
    weights = [D(rng.randrange(1, 500_00)) / 100 for _ in range(n)]
    total = D(rng.randrange(1, 1_000_00)) / 100

    parts = allocate_proportionally(total, weights)
    sum_w = sum(weights)

    for part, weight in zip(parts, weights):
        exact = total * weight / sum_w
        assert abs(part - exact) < D("0.01"), (
            f"line share {part} deviates from exact {exact} by a cent or more"
        )


def test_allocating_a_discount_never_exceeds_the_line_itself_when_capped():
    """Sanity check for the caller's contract.

    The function apportions whatever it is given. When the total equals the
    sum of weights (a 100% discount) each line's share equals that line — the
    property the order path relies on to never produce a negative net line.
    """
    weights = [D("19.99"), D("5.01"), D("100.00")]
    parts = allocate_proportionally(sum(weights), weights)
    assert parts == weights
