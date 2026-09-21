"""Two findings from the §13 (inventory) and §12 (confidence) audit pass.

FINDING 1 — inventory was assumed, not checked.
    `SizeCandidate.in_stock` was computed as ``level is None or level > 0``, so a
    size absent from the stock map was reported to the user as **in stock**. The
    response asserted a fact the system had never established. Reachable
    whenever a product carries a size chart but no SKU rows: `sellable_sizes`
    is then empty, the chart is not restricted, and every charted size is
    reported available for a product that sells nothing.

FINDING 2 — the confidence number read as a probability.
    The engine emits an evidence tally in 0-100 and the API rendered it as
    "Size M at 66% confidence". Nothing in this system is calibrated against
    real fit outcomes, so a percentage implies a frequency we have never
    measured. The tally is retained for compatibility; the user-facing signal is
    now a deterministic high/medium/low band.
"""

from __future__ import annotations

import pytest

from backend.app.services.fit.ease import GarmentClass
from backend.app.services.fit.engine import FitEngine, FitDecision, FitRefusal, confidence_band
from backend.app.services.fit.size_charts import ChartContext, SizeChartResolver
from backend.app.services.fit.units import BodyMeasurements

CHART = (
    '{"unit":"cm","source":"test chart","updated_at":"2026-01-01","rows":['
    '{"size":"S","chest":[86,94]},{"size":"M","chest":[94,102]},{"size":"L","chest":[102,110]}]}'
)
BRAND_CHART = (
    '{"unit":"cm","published_by_brand":true,"updated_at":"2026-01-01","rows":['
    '{"size":"S","chest":[86,94],"waist":[72,80]},'
    '{"size":"M","chest":[94,102],"waist":[80,88]},'
    '{"size":"L","chest":[102,110],"waist":[88,96]}]}'
)

engine = FitEngine()


def _chart(raw=CHART, sellable=("S", "M", "L")):
    return SizeChartResolver().resolve(
        ChartContext(product_size_chart_json=raw, sellable_sizes=list(sellable))
    )


def _run(stock, body=None, raw=CHART, sellable=("S", "M", "L")):
    return engine.recommend(
        body=body or BodyMeasurements(height_cm=178, weight_kg=80, chest_cm=98),
        chart=_chart(raw, sellable),
        garment_class=GarmentClass("woven_top"),
        fit_preference="regular",
        material=None,
        stock_by_size=stock,
        demographic="men",
    )


# ── Finding 1: inventory ───────────────────────────────────────────────────

def test_a_size_absent_from_the_stock_map_is_unknown_not_available():
    """The core of the bug: missing != available."""
    result = _run({"S": 5, "L": 5})  # M's availability was never established
    table = {c.size: c for c in result.candidates}
    assert table["M"].in_stock is None, "an unchecked size was reported as stocked"
    assert table["M"].availability == "unknown"
    assert table["S"].in_stock is True
    assert not table["M"].is_sellable, "an unconfirmed size must not be sellable"


def test_an_unconfirmed_size_is_never_the_recommendation():
    """M fits best, but we cannot confirm it exists. Recommend a real size."""
    result = _run({"S": 5, "L": 5})
    assert isinstance(result, FitDecision)
    assert result.recommended_size != "M"
    assert result.recommended_size in {"S", "L"}


def test_product_with_a_chart_but_no_skus_refuses_instead_of_inventing_stock():
    """Previously returned M with in_stock=True for a product selling nothing."""
    result = _run({}, sellable=())
    assert not result.recommended
    assert isinstance(result, FitRefusal)
    assert result.reason_code == "INVENTORY_UNKNOWN"
    assert result.diagnostics.get("inventory_checked") is False
    # It should still be useful: say which size WOULD have fitted.
    assert result.diagnostics.get("best_fitting_size_if_available") == "M"


def test_explicitly_zero_stock_is_out_of_stock_not_unknown():
    """A checked-and-empty size is a different fact from an unchecked one."""
    result = _run({"S": 5, "M": 0, "L": 5})
    table = {c.size: c for c in result.candidates}
    assert table["M"].in_stock is False
    assert table["M"].availability == "out_of_stock"
    assert result.recommended_size != "M"


def test_all_sizes_zero_is_no_sellable_size_not_inventory_unknown():
    result = _run({"S": 0, "M": 0, "L": 0})
    assert isinstance(result, FitRefusal)
    assert result.reason_code == "NO_SELLABLE_SIZE"


def test_normal_case_still_recommends_the_best_fitting_available_size():
    """Guard against the fix being over-tightened into refusing everything."""
    result = _run({"S": 5, "M": 5, "L": 5})
    assert isinstance(result, FitDecision)
    assert result.recommended_size == "M"
    assert result.top.in_stock is True


# ── Finding 2: confidence is a band, not a probability ─────────────────────

def test_no_measured_section_is_always_low_confidence():
    band, why = confidence_band(
        measured_sections=0,
        estimated_sections=3,
        chart_is_brand_published=True,
        chart_is_product_specific=True,
        fit_score=95.0,
        is_ambiguous=False,
    )
    assert band == "low"
    assert "estimated" in why.lower()


def test_generic_standard_chart_caps_confidence_at_low():
    band, _ = confidence_band(
        measured_sections=3,
        estimated_sections=0,
        chart_is_brand_published=False,
        chart_is_product_specific=False,
        fit_score=99.0,
        is_ambiguous=False,
    )
    assert band == "low", "a generic chart cannot support high confidence"


def test_best_case_evidence_is_high_confidence():
    band, why = confidence_band(
        measured_sections=2,
        estimated_sections=0,
        chart_is_brand_published=True,
        chart_is_product_specific=True,
        fit_score=90.0,
        is_ambiguous=False,
    )
    assert band == "high"
    assert "brand" in why.lower()


def test_ambiguity_between_two_sizes_is_never_high():
    band, _ = confidence_band(
        measured_sections=3,
        estimated_sections=0,
        chart_is_brand_published=True,
        chart_is_product_specific=True,
        fit_score=95.0,
        is_ambiguous=True,
    )
    assert band == "medium"


def test_band_is_deterministic():
    kwargs = dict(
        measured_sections=2,
        estimated_sections=1,
        chart_is_brand_published=True,
        chart_is_product_specific=True,
        fit_score=88.0,
        is_ambiguous=False,
    )
    assert len({confidence_band(**kwargs)[0] for _ in range(50)}) == 1


def test_decision_exposes_a_band_and_never_calls_the_score_a_probability():
    result = _run({"S": 5, "M": 5, "L": 5}, raw=BRAND_CHART)
    assert isinstance(result, FitDecision)
    assert result.confidence_band in {"high", "medium", "low"}
    assert result.confidence_band_reason
    payload = result.as_dict()
    assert payload["confidence_band"] == result.confidence_band


@pytest.mark.parametrize("measured", [1, 2, 3])
def test_more_measured_sections_never_lowers_the_band(measured):
    """Monotonicity: better evidence must not produce a worse rating."""
    order = {"low": 0, "medium": 1, "high": 2}
    band, _ = confidence_band(
        measured_sections=measured,
        estimated_sections=0,
        chart_is_brand_published=True,
        chart_is_product_specific=True,
        fit_score=90.0,
        is_ambiguous=False,
    )
    baseline, _ = confidence_band(
        measured_sections=0,
        estimated_sections=3,
        chart_is_brand_published=True,
        chart_is_product_specific=True,
        fit_score=90.0,
        is_ambiguous=False,
    )
    assert order[band] >= order[baseline]
