"""Semantic-closure tests: estimated measurements (§4) and generic-fallback
eligibility (§9).

These cover two questions the earlier passes answered only technically:

1. Does the engine ever name a size that rests entirely on girths it invented
   from height and weight? (It must not — the estimator's own residual spread
   is wider than a size band.)
2. Is the generic EN 13402-3 chart ever applied to a product it cannot
   semantically describe, such as footwear or a handbag? (It must not — that is
   a category error, not a low-confidence answer.)

Each test asserts WHICH measurements were used and WHY, not merely that the
call succeeded.
"""

from __future__ import annotations

import pytest

from backend.app.services.fit.anthropometry import (
    _BMI_SUPPORT,
    estimate_missing_girths,
    residual_sd,
)
from backend.app.services.fit.ease import GarmentClass
from backend.app.services.fit.engine import FitEngine
from backend.app.services.fit.size_charts import (
    ChartContext,
    SizeChartResolver,
    en13402_eligibility,
)
from backend.app.services.fit.units import BodyMeasurements

BRAND_CHART = (
    '{"unit":"cm","published_by_brand":true,"updated_at":"2026-01-01",'
    '"rows":[{"size":"S","chest":[86,94],"waist":[72,80]},'
    '{"size":"M","chest":[94,102],"waist":[80,88]},'
    '{"size":"L","chest":[102,110],"waist":[88,96]}]}'
)
STOCK = {"S": 5, "M": 5, "L": 5}
engine = FitEngine()


def _chart(raw=BRAND_CHART, category="tops", sizes=("S", "M", "L")):
    return SizeChartResolver().resolve(
        ChartContext(
            product_size_chart_json=raw,
            sellable_sizes=list(sizes),
            demographic="men",
            category_slug=category,
        )
    )


def _run(body, chart=None, stock=None, garment="woven_top"):
    return engine.recommend(
        body=body,
        chart=chart if chart is not None else _chart(),
        garment_class=GarmentClass(garment),
        fit_preference="regular",
        material=None,
        stock_by_size=stock if stock is not None else STOCK,
        demographic="men",
    )


# ───────────────────────── §4 estimated measurements ──────────────────────


class TestEstimationIsNeverTheSoleBasisForASize:
    def test_height_and_weight_only_refuses(self):
        r = _run(BodyMeasurements(height_cm=178, weight_kg=78))
        assert r.recommended is False
        assert r.reason_code == "INSUFFICIENT_EVIDENCE"
        # It must tell the user what to measure, not just fail.
        assert set(r.missing) >= {"chest_cm"}
        assert "height and weight alone" in r.message

    @pytest.mark.parametrize("h,w", [(160, 50), (170, 70), (185, 95), (195, 120)])
    def test_no_body_gets_a_size_from_height_and_weight_alone(self, h, w):
        r = _run(BodyMeasurements(height_cm=h, weight_kg=w))
        assert r.recommended is False, f"named a size for h{h}/w{w} with zero measured girths"

    def test_one_real_measurement_unlocks_a_recommendation(self):
        """Refusal must be proportionate: measuring chest is enough for a top."""
        r = _run(BodyMeasurements(height_cm=178, weight_kg=78, chest_cm=98))
        assert r.recommended is True
        assert r.recommended_size == "M"
        # Still not high confidence — the waist was estimated.
        assert r.confidence_band in {"medium", "low"}

    def test_two_real_measurements_raise_confidence(self):
        r = _run(BodyMeasurements(height_cm=178, weight_kg=78, chest_cm=98, waist_cm=84))
        assert r.recommended is True
        assert r.confidence_band == "high"

    def test_the_refusal_is_justified_by_the_estimators_own_numbers(self):
        """The reason we refuse: residual SD exceeds one 8 cm size band."""
        r = _run(BodyMeasurements(height_cm=178, weight_kg=78))
        sds = r.diagnostics["residual_sd_cm"]
        assert sds, "refusal must expose the uncertainty that caused it"
        # EN 13402-3 men's chest bands are 8 cm wide.
        assert max(sds.values()) * 2 > 8.0, (
            "if the estimator were this precise the refusal would be unnecessary"
        )

    def test_estimated_fields_are_always_labelled(self):
        b = estimate_missing_girths(
            BodyMeasurements(height_cm=178, weight_kg=78, chest_cm=98), demographic="men"
        )
        assert "chest_cm" not in b.estimated_fields, "a measured value was marked estimated"
        assert "waist_cm" in b.estimated_fields
        assert b.chest_cm == 98, "a measured value must never be overwritten"

    def test_estimation_needs_both_height_and_weight(self):
        """Height alone must invent nothing."""
        b = BodyMeasurements(height_cm=178)
        out = estimate_missing_girths(b, demographic="men")
        assert out.estimated_fields == frozenset() or not out.estimated_fields
        assert out.chest_cm is None

    @pytest.mark.parametrize("bmi_target", [10.0, 60.0])
    def test_out_of_support_bmi_estimates_nothing(self, bmi_target):
        h = 1.75
        w = bmi_target * h * h
        out = estimate_missing_girths(
            BodyMeasurements(height_cm=175, weight_kg=w), demographic="men"
        )
        assert not out.estimated_fields, (
            f"extrapolated outside the model support {_BMI_SUPPORT}"
        )
        assert out.chest_cm is None

    def test_unknown_sex_widens_uncertainty(self):
        assert residual_sd("chest_cm", None) > residual_sd("chest_cm", "men")

    def test_conflicting_measurements_do_not_silently_resolve(self):
        """Waist far larger than chest is unusual but real; it must not crash
        nor be quietly 'corrected' into a comfortable answer."""
        r = _run(BodyMeasurements(height_cm=178, weight_kg=78, chest_cm=90, waist_cm=130))
        if r.recommended:
            assert r.confidence_band != "high"
        else:
            assert r.reason_code in {"NO_SIZE_FITS", "INSUFFICIENT_EVIDENCE"}


# ─────────────────── §9 generic fallback eligibility ──────────────────────


class TestGenericFallbackEligibility:
    @pytest.mark.parametrize("slug", ["tops", "bottoms", "outerwear", "dresses"])
    def test_garment_categories_may_use_the_standard(self, slug):
        ok, reason = en13402_eligibility(slug)
        assert ok is True and reason

    @pytest.mark.parametrize("slug", ["footwear", "shoes", "accessories", "bags", "jewellery"])
    def test_non_garment_categories_may_not(self, slug):
        ok, reason = en13402_eligibility(slug)
        assert ok is False
        assert reason

    def test_unknown_category_is_ineligible_not_assumed_clothing(self):
        assert en13402_eligibility("mystery-box")[0] is False
        assert en13402_eligibility(None)[0] is False

    def test_footwear_sold_in_letter_sizes_is_refused(self):
        """The real hole: numeric shoe sizes failed only because '42' is not a
        letter code. A sandal sold S/M/L used to get CHEST bands."""
        chart = _chart(raw=None, category="footwear")
        assert chart.provenance.source == "none"
        assert any("not applicable" in w for w in chart.parse_warnings)

    def test_accessory_sold_in_letter_sizes_is_refused(self):
        chart = _chart(raw=None, category="accessories")
        assert chart.provenance.source == "none"

    def test_numeric_shoe_sizes_still_refused(self):
        chart = _chart(raw=None, category="footwear", sizes=("40", "41", "42"))
        assert chart.provenance.source == "none"

    def test_eligible_category_without_product_chart_uses_the_standard(self):
        chart = _chart(raw=None, category="tops")
        assert chart.provenance.source == "standard_en13402"
        assert chart.provenance.as_dict()["is_brand_published"] is False

    def test_the_engine_refuses_end_to_end_for_an_ineligible_category(self):
        chart = _chart(raw=None, category="footwear")
        r = _run(
            BodyMeasurements(height_cm=178, weight_kg=78, chest_cm=98, waist_cm=84),
            chart=chart,
        )
        assert r.recommended is False
        assert r.reason_code == "NO_SIZE_CHART"

    # ── precedence (§10) ──
    def test_product_chart_wins_over_the_generic_standard(self):
        chart = _chart(raw=BRAND_CHART, category="tops")
        assert chart.provenance.source == "brand_published"

    def test_product_chart_is_used_even_for_an_ineligible_category(self):
        """Eligibility gates the GENERIC chart only. A real chart attached to a
        footwear product is authoritative for that product."""
        shoe_chart = (
            '{"unit":"cm","published_by_brand":true,"updated_at":"2026-01-01",'
            '"rows":[{"size":"S","chest":[86,94]},{"size":"M","chest":[94,102]}]}'
        )
        chart = _chart(raw=shoe_chart, category="footwear", sizes=("S", "M"))
        assert chart.provenance.source == "brand_published"

    def test_derived_chart_is_never_marked_brand_published(self):
        derived = (
            '{"unit":"cm","source":"EN 13402-3 (derived)","updated_at":"2026-01-01",'
            '"rows":[{"size":"S","chest":[86,94]},{"size":"M","chest":[94,102]}]}'
        )
        chart = _chart(raw=derived, category="tops", sizes=("S", "M"))
        assert chart.provenance.as_dict()["is_brand_published"] is False
        assert chart.provenance.is_authoritative is False
