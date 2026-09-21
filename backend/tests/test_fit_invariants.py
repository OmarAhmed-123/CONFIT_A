"""§21 required invariants for the Fit Finder, asserted through the REAL paths.

These are not unit tests of helpers. Each one encodes a rule that must hold for
every response the product can emit, and each corresponds to a defect that was
actually shipped at some point in this feature's history:

* "Does not fit" once coexisted with ``recommended: true`` (two independent
  thresholds that disagreed).
* Unknown inventory was once reported as in stock.
* A standards-derived chart was once labelled "Brand-published".
* A deterministic rule score was once rendered as "66% confidence".

Property-style checks sweep a grid of bodies/charts/stock so a future change
that breaks an invariant for some input is caught even if the hand-written
example still passes.
"""

from __future__ import annotations

import itertools

import pytest

from backend.app.services.fit.ease import GarmentClass
from backend.app.services.fit.engine import (
    _MIN_FIT_SCORE_FOR_RECOMMENDATION,
    FitDecision,
    FitEngine,
    FitRefusal,
)
from backend.app.services.fit.size_charts import ChartContext, SizeChartResolver
from backend.app.services.fit.units import BodyMeasurements
from backend.app.services.no_photo_fit_service import NoPhotoFitService

engine = FitEngine()

DERIVED_CHART = (
    '{"unit":"cm","source":"EN 13402-3 (derived)","updated_at":"2026-01-01",'
    '"notes":["Demo catalogue: standards-derived, not published by the brand."],'
    '"rows":[{"size":"S","chest":[86,94],"waist":[72,80]},'
    '{"size":"M","chest":[94,102],"waist":[80,88]},'
    '{"size":"L","chest":[102,110],"waist":[88,96]}]}'
)
BRAND_CHART = (
    '{"unit":"cm","published_by_brand":true,"updated_at":"2026-01-01",'
    '"rows":[{"size":"S","chest":[86,94],"waist":[72,80]},'
    '{"size":"M","chest":[94,102],"waist":[80,88]},'
    '{"size":"L","chest":[102,110],"waist":[88,96]}]}'
)

# A deliberately wide sweep: tiny, normal, huge and boundary-exact bodies.
BODIES = [
    BodyMeasurements(height_cm=178, weight_kg=78, chest_cm=98, waist_cm=84),
    BodyMeasurements(height_cm=160, weight_kg=50, chest_cm=86, waist_cm=72),
    BodyMeasurements(height_cm=195, weight_kg=120, chest_cm=130, waist_cm=124),
    BodyMeasurements(height_cm=170, weight_kg=52, chest_cm=130, waist_cm=120),
    BodyMeasurements(height_cm=175, weight_kg=70, chest_cm=94, waist_cm=80),
    BodyMeasurements(height_cm=182, weight_kg=95, chest_cm=110, waist_cm=96),
    BodyMeasurements(height_cm=165, weight_kg=60),  # girths estimated only
]
STOCKS = [
    {"S": 5, "M": 5, "L": 5},
    {"S": 0, "M": 0, "L": 0},
    {"S": 5, "L": 5},          # M unknown
    {},                        # nothing known
    {"S": 0, "M": 3, "L": 0},
]
CHARTS = [DERIVED_CHART, BRAND_CHART, "{}"]
PREFS = ["slim", "regular", "relaxed"]


def _resolve(raw, stock):
    sellable = [s for s, v in stock.items() if v is None or v > 0]
    return SizeChartResolver().resolve(
        ChartContext(
            product_size_chart_json=raw,
            sellable_sizes=sellable or list(stock.keys()),
            demographic="men",
        )
    )


def _run(body, raw, stock, pref="regular"):
    return engine.recommend(
        body=body,
        chart=_resolve(raw, stock),
        garment_class=GarmentClass("woven_top"),
        fit_preference=pref,
        material=None,
        stock_by_size=stock,
        demographic="men",
    )


ALL_CASES = list(itertools.product(BODIES, CHARTS, STOCKS, PREFS))


@pytest.mark.parametrize("body,raw,stock,pref", ALL_CASES)
def test_invariants_hold_for_every_combination(body, raw, stock, pref):
    """One sweep, all §21 invariants. 315 combinations."""
    result = _run(body, raw, stock, pref)

    if not result.recommended:
        assert isinstance(result, FitRefusal)
        assert result.reason_code, "a refusal must say why"
        assert result.message, "a refusal must be explainable to the user"
        return

    assert isinstance(result, FitDecision)
    top = result.top

    # INVARIANT 1 — fit classification consistency.
    # A size the product describes as "Does not fit" must never be recommended.
    rating = NoPhotoFitService._rating_label(top.score)
    assert rating != "Does not fit", (
        f"recommended a size rated 'Does not fit' (score={top.score})"
    )
    assert top.score >= _MIN_FIT_SCORE_FOR_RECOMMENDATION

    # INVARIANT 2 — inventory honesty.
    # The recommended size must be CONFIRMED available, never unknown.
    assert top.in_stock is True, f"recommended a size with availability={top.availability}"
    assert top.is_sellable

    # INVARIANT 3 — provenance honesty.
    prov = result.chart.provenance
    if prov.source != "brand_published":
        assert prov.is_brand_published is False if hasattr(prov, "is_brand_published") else True
        assert prov.as_dict()["is_brand_published"] is False, (
            f"non-brand chart ({prov.source}) claimed brand publication"
        )

    # INVARIANT 4 — confidence honesty: a band, and never a probability.
    assert result.confidence_band in {"high", "medium", "low"}
    assert result.confidence_band_reason
    payload = result.as_dict()
    assert "probability" not in str(payload.get("confidence_band", "")).lower()

    # INVARIANT 5 — a generic fallback chart can never be high confidence.
    if not prov.is_product_specific:
        assert result.confidence_band == "low", (
            "generic standard chart must not support better than low confidence"
        )


@pytest.mark.parametrize("body,raw,stock,pref", ALL_CASES)
def test_no_candidate_is_ever_reported_as_confirmed_without_evidence(body, raw, stock, pref):
    """INVARIANT 3b — unknown availability must never render as confirmed."""
    result = _run(body, raw, stock, pref)
    if not result.recommended:
        return
    for c in result.candidates:
        level = stock.get(c.size)
        if level is None:
            assert c.in_stock is None, f"{c.size}: unchecked size reported as {c.in_stock}"
            assert c.availability == "unknown"
        else:
            assert c.in_stock is (level > 0)
            assert c.availability == ("in_stock" if level > 0 else "out_of_stock")


def test_rating_label_threshold_is_bound_to_the_engine_refusal_floor():
    """The two thresholds must be ONE number, not two that happen to agree.

    When they diverged (refusal at 0, label at 45) production recommended a
    garment it simultaneously described as "Does not fit".
    """
    assert NoPhotoFitService._DOES_NOT_FIT_BELOW is _MIN_FIT_SCORE_FOR_RECOMMENDATION
    eps = 0.01
    assert NoPhotoFitService._rating_label(_MIN_FIT_SCORE_FOR_RECOMMENDATION) != "Does not fit"
    assert NoPhotoFitService._rating_label(_MIN_FIT_SCORE_FOR_RECOMMENDATION - eps) == "Does not fit"


def test_missing_critical_measurements_refuse_rather_than_fabricate():
    """INVARIANT 7 — no girth measured at all, for a garment sized by girth."""
    body = BodyMeasurements(height_cm=175, weight_kg=70)
    result = _run(body, BRAND_CHART, {"S": 5, "M": 5, "L": 5})
    if result.recommended:
        # Permitted only if it is openly flagged as estimated AND low confidence.
        assert result.body_used.estimated_fields, "estimated girths not disclosed"
        assert result.confidence_band == "low"
    else:
        assert result.reason_code in {"INSUFFICIENT_EVIDENCE", "NO_COMPARABLE_SECTION"}


def test_no_compatible_available_size_produces_an_explicit_refusal():
    """INVARIANT 1b — a body nothing fits must get a refusal, not the least-bad size."""
    body = BodyMeasurements(height_cm=170, weight_kg=52, chest_cm=130, waist_cm=120)
    result = _run(body, BRAND_CHART, {"S": 5, "M": 5, "L": 5})
    assert not result.recommended
    assert result.reason_code == "NO_SIZE_FITS"
