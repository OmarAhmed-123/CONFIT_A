"""§15 — does the EVIDENCE justify naming ONE size?

The earlier passes established that the engine refuses when nothing is measured,
and that generic charts are gated by category. This file covers the remaining
semantic question: when the engine *does* name a size, is that single size
actually supported by the evidence, or is it an artefact of treating an
uncertain estimate as an exact number?

The defect these tests lock down: a user who measured only their hip received
trouser size 32 described as "just right", where the waist driving that decision
was invented by us with a ±7 cm error bar. Sliding that estimate inside its own
error bar produced sizes 30, 32 and 34 — yet the response said
``is_ambiguous: false``.
"""

from __future__ import annotations

import pytest

from backend.app.services.fit.anthropometry import estimate_missing_girths, residual_sd
from backend.app.services.fit.ease import GarmentClass
from backend.app.services.fit.engine import FitEngine
from backend.app.services.fit.size_charts import ChartContext, SizeChartResolver
from backend.app.services.fit.units import BodyMeasurements

engine = FitEngine()

TOP_CHART = (
    '{"unit":"cm","published_by_brand":true,"updated_at":"2026-01-01",'
    '"rows":[{"size":"S","chest":[86,94],"waist":[72,80]},'
    '{"size":"M","chest":[94,102],"waist":[80,88]},'
    '{"size":"L","chest":[102,110],"waist":[88,96]}]}'
)
TROUSER_CHART = (
    '{"unit":"cm","published_by_brand":true,"updated_at":"2026-01-01",'
    '"rows":[{"size":"30","waist":[76,81],"hip":[92,97]},'
    '{"size":"32","waist":[81,86],"hip":[97,102]},'
    '{"size":"34","waist":[86,91],"hip":[102,107]}]}'
)
# One dimension only, with heavily overlapping bands (Case B in the brief).
ONE_D_OVERLAP = (
    '{"unit":"cm","published_by_brand":true,"updated_at":"2026-01-01",'
    '"rows":[{"size":"M","chest":[94,104]},{"size":"L","chest":[98,108]}]}'
)
# Multidimensional overlap: legitimate, a second dimension separates them.
MULTI_D_OVERLAP = (
    '{"unit":"cm","published_by_brand":true,"updated_at":"2026-01-01",'
    '"rows":[{"size":"M","chest":[94,102],"waist":[78,86]},'
    '{"size":"L","chest":[98,106],"waist":[82,90]}]}'
)


def _chart(raw, sizes, category, demographic="men"):
    return SizeChartResolver().resolve(
        ChartContext(
            product_size_chart_json=raw,
            sellable_sizes=list(sizes),
            demographic=demographic,
            category_slug=category,
        )
    )


def _run(body, raw, sizes, category, garment, stock=None):
    stock = stock if stock is not None else {s: 5 for s in sizes}
    return engine.recommend(
        body=body,
        chart=_chart(raw, sizes, category),
        garment_class=GarmentClass(garment),
        fit_preference="regular",
        material=None,
        stock_by_size=stock,
        demographic="men",
    )


# ───────────────────── interval ambiguity (§4) ─────────────────────────────


class TestEstimateIntervalIsRespected:
    def test_uncertain_estimate_reaching_another_size_is_not_presented_as_certain(self):
        """THE defect: hip measured, waist estimated, trousers sized by waist."""
        body = estimate_missing_girths(
            BodyMeasurements(height_cm=178, weight_kg=78, hip_cm=99), demographic="men"
        )
        r = _run(body, TROUSER_CHART, ("30", "32", "34"), "bottoms", "trousers")
        assert r.recommended is True, "over-correcting into a refusal is not the fix"
        assert r.is_ambiguous is True, (
            "the estimate's error bar reaches another size; this is not a certain answer"
        )
        assert r.alternative_size is not None, "the other plausible size must be named"
        assert r.confidence_band != "high"
        assert any("estimated" in n and "neighbouring size" in n for n in r.notes), (
            "the user must be told WHY it is uncertain"
        )

    def test_the_winner_is_genuinely_unstable_across_the_error_bar(self):
        """Proves the test above is not tautological: the size really does change."""
        body = estimate_missing_girths(
            BodyMeasurements(height_cm=178, weight_kg=78, hip_cm=99), demographic="men"
        )
        sd = residual_sd("waist_cm", "men")
        winners = set()
        for probe in (body.waist_cm - sd, body.waist_cm, body.waist_cm + sd):
            perturbed = BodyMeasurements(
                height_cm=178, weight_kg=78, hip_cm=99, waist_cm=round(probe, 1)
            )
            res = _run(perturbed, TROUSER_CHART, ("30", "32", "34"), "bottoms", "trousers")
            if res.recommended:
                winners.add(res.recommended_size)
        assert len(winners) > 1, f"expected the estimate to swing the size, got {winners}"

    def test_measured_values_stay_decisive(self):
        """The check must not make confident cases timid."""
        body = BodyMeasurements(height_cm=178, weight_kg=78, hip_cm=99, waist_cm=83)
        r = _run(body, TROUSER_CHART, ("30", "32", "34"), "bottoms", "trousers")
        assert r.recommended is True
        assert r.is_ambiguous is False
        assert r.confidence_band == "high"

    def test_estimate_well_inside_one_size_remains_unambiguous(self):
        """An estimate whose whole interval sits in one size is fine to use."""
        body = BodyMeasurements(height_cm=178, weight_kg=78, chest_cm=98)
        body = estimate_missing_girths(body, demographic="men")
        r = _run(body, TOP_CHART, ("S", "M", "L"), "tops", "woven_top")
        assert r.recommended is True
        assert r.recommended_size == "M"

    @pytest.mark.parametrize("hip", [95, 99, 100, 103])
    def test_estimated_primary_dimension_never_claims_certainty(self, hip):
        body = estimate_missing_girths(
            BodyMeasurements(height_cm=178, weight_kg=78, hip_cm=hip), demographic="men"
        )
        r = _run(body, TROUSER_CHART, ("30", "32", "34"), "bottoms", "trousers")
        if r.recommended:
            assert not (r.is_ambiguous is False and r.confidence_band == "high")


# ───────────────────── evidence sufficiency (§5/§6) ────────────────────────


class TestEvidenceSufficiencyIsDimensionAware:
    def test_all_estimated_refuses(self):
        r = _run(
            estimate_missing_girths(
                BodyMeasurements(height_cm=178, weight_kg=78), demographic="men"
            ),
            TOP_CHART, ("S", "M", "L"), "tops", "woven_top",
        )
        assert r.recommended is False
        assert r.reason_code == "INSUFFICIENT_EVIDENCE"

    def test_a_measurement_irrelevant_to_the_chart_does_not_unlock_a_size(self):
        """Measuring chest tells you nothing about a waist/hip trouser chart."""
        body = estimate_missing_girths(
            BodyMeasurements(height_cm=178, weight_kg=78, chest_cm=98), demographic="men"
        )
        r = _run(body, TROUSER_CHART, ("30", "32", "34"), "bottoms", "trousers")
        assert r.recommended is False
        assert r.reason_code == "INSUFFICIENT_EVIDENCE"

    def test_the_relevant_measurement_does_unlock_a_size(self):
        body = estimate_missing_girths(
            BodyMeasurements(height_cm=178, weight_kg=78, waist_cm=83), demographic="men"
        )
        r = _run(body, TROUSER_CHART, ("30", "32", "34"), "bottoms", "trousers")
        assert r.recommended is True


# ───────────────────── overlap + ties (§7/§8/§9) ───────────────────────────


class TestOverlapAndTieBreaking:
    def test_ambiguous_one_dimensional_overlap_is_exposed_not_hidden(self):
        body = BodyMeasurements(height_cm=178, weight_kg=78, chest_cm=101)
        r = _run(body, ONE_D_OVERLAP, ("M", "L"), "tops", "woven_top")
        assert r.recommended is True
        assert r.is_ambiguous is True
        assert r.alternative_size == "L"
        scores = {c.size: c.score for c in r.candidates}
        assert scores["M"] == scores["L"], "this fixture is meant to be an exact tie"

    def test_multidimensional_overlap_is_legitimate_and_resolvable(self):
        """Case A: overlap is normal; a second dimension separates the sizes."""
        body = BodyMeasurements(height_cm=178, weight_kg=78, chest_cm=100, waist_cm=79)
        r = _run(body, MULTI_D_OVERLAP, ("M", "L"), "tops", "woven_top")
        assert r.recommended is True
        assert r.recommended_size == "M", "the waist should favour M"

    def test_exact_tie_breaks_to_the_smaller_size_deterministically(self):
        """Documented product rule, and stable across repeated runs."""
        body = BodyMeasurements(height_cm=178, weight_kg=78, chest_cm=101)
        picks = {
            _run(body, ONE_D_OVERLAP, ("M", "L"), "tops", "woven_top").recommended_size
            for _ in range(8)
        }
        assert picks == {"M"}, f"tie-break must be deterministic, saw {picks}"

    def test_tie_break_does_not_depend_on_chart_row_order(self):
        reversed_chart = (
            '{"unit":"cm","published_by_brand":true,"updated_at":"2026-01-01",'
            '"rows":[{"size":"L","chest":[98,108]},{"size":"M","chest":[94,104]}]}'
        )
        body = BodyMeasurements(height_cm=178, weight_kg=78, chest_cm=101)
        a = _run(body, ONE_D_OVERLAP, ("M", "L"), "tops", "woven_top")
        b = _run(body, reversed_chart, ("M", "L"), "tops", "woven_top")
        assert a.recommended_size == b.recommended_size == "M"


# ───────────────────── inventory interaction (§13) ─────────────────────────


class TestInventoryDoesNotDistortFit:
    def test_two_valid_sizes_one_in_stock_may_resolve_to_the_available_one(self):
        """Case A in the brief: permitted, because both genuinely fit."""
        body = BodyMeasurements(height_cm=178, weight_kg=78, chest_cm=101)
        r = _run(body, ONE_D_OVERLAP, ("M", "L"), "tops", "woven_top",
                 stock={"M": 0, "L": 4})
        assert r.recommended is True
        assert r.recommended_size == "L"
        assert r.top.in_stock is True
        # M scored identically but is out of stock, so availability -- not a
        # fit judgement -- decided between two genuinely valid sizes.
        by_size = {c.size: c for c in r.candidates}
        assert by_size["M"].score == by_size["L"].score
        assert by_size["M"].in_stock is False

    def test_inventory_never_promotes_a_size_that_does_not_fit(self):
        """Case B: M is in stock but wrong; L fits but is out. Must not push M."""
        body = BodyMeasurements(height_cm=170, weight_kg=52, chest_cm=130, waist_cm=120)
        r = _run(body, TOP_CHART, ("S", "M", "L"), "tops", "woven_top",
                 stock={"S": 0, "M": 9, "L": 0})
        assert r.recommended is False
        assert r.reason_code == "NO_SIZE_FITS"

    def test_unknown_inventory_stays_unknown(self):
        """Case C: nothing known about stock -> refuse, do not assume available."""
        body = BodyMeasurements(height_cm=178, weight_kg=78, chest_cm=98, waist_cm=84)
        r = _run(body, TOP_CHART, ("S", "M", "L"), "tops", "woven_top", stock={})
        assert r.recommended is False
        assert r.reason_code == "INVENTORY_UNKNOWN"
        assert r.diagnostics["inventory_checked"] is False


# ───────────────────── explanation honesty (§10) ───────────────────────────


class TestExplanationMatchesTheEvidence:
    def test_estimated_sections_are_flagged_as_estimated(self):
        body = estimate_missing_girths(
            BodyMeasurements(height_cm=178, weight_kg=78, chest_cm=98), demographic="men"
        )
        r = _run(body, TOP_CHART, ("S", "M", "L"), "tops", "woven_top")
        assert r.recommended is True
        by_dim = {s.dimension: s for s in r.top.sections}
        assert by_dim["chest"].body_is_estimated is False
        assert by_dim["waist"].body_is_estimated is True
        # The engine payload exposes the same distinction per section.
        sections = [s.as_dict() for s in r.top.sections]
        assert any(s.get("measurement_is_estimated") for s in sections), (
            "the payload must distinguish estimated from measured"
        )
        assert any(not s.get("measurement_is_estimated") for s in sections)

    def test_no_section_claims_a_measurement_the_user_never_gave(self):
        body = estimate_missing_girths(
            BodyMeasurements(height_cm=178, weight_kg=78, chest_cm=98), demographic="men"
        )
        r = _run(body, TOP_CHART, ("S", "M", "L"), "tops", "woven_top")
        for s in r.top.sections:
            if not s.body_is_estimated:
                assert s.dimension == "chest", (
                    f"{s.dimension} was never measured but is reported as measured"
                )
