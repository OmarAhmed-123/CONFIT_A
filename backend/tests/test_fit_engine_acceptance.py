"""Acceptance + property tests for the Fit Finder size engine.

The 2026-09-21 audit's core finding was that the recommendation *computation*
was unproven ("النتيجة الحسابية غير مثبتة") and that no acceptance data existed
across bodies, sizes and brands. This file is the answer to both:

* ``fixtures/fit_acceptance_cases.json`` drives table-based acceptance over
  anonymous synthetic bodies against five deliberately different brand charts,
  each case asserting an acceptable *range* of sizes rather than one label.
* The property tests below pin invariants that must hold for ALL inputs, which
  is what stops a future refactor from re-introducing a BMI lookup table that
  happens to pass the table cases.

Nothing here touches the database or the network: the engine is a pure domain
service, so these assertions are about the maths, not about a fixture DB.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import pytest

from backend.app.services.fit.ease import GarmentClass
from backend.app.services.fit.engine import FitDecision, FitEngine, FitRefusal, section_score
from backend.app.services.fit.size_charts import (
    ChartContext,
    SizeChartResolver,
    parse_size_chart_json,
    size_sort_key,
)
from backend.app.services.fit.units import (
    BodyMeasurements,
    MeasurementValidationError,
    UnitSystem,
)

FIXTURE = Path(__file__).parent / "fixtures" / "fit_acceptance_cases.json"
DATA = json.loads(FIXTURE.read_text())
CASES = {case["id"]: case for case in DATA["cases"]}
CHARTS = DATA["charts"]

engine = FitEngine()


def _run(case: Dict) -> FitDecision | FitRefusal:
    body_spec = dict(case["body"])
    body = BodyMeasurements.from_payload(
        units=UnitSystem(body_spec.pop("units", "metric")),
        height=body_spec.pop("height"),
        weight=body_spec.pop("weight", None),
        chest=body_spec.pop("chest", None),
        waist=body_spec.pop("waist", None),
        hip=body_spec.pop("hip", None),
        shoulder=body_spec.pop("shoulder", None),
        inseam=body_spec.pop("inseam", None),
        neck=body_spec.pop("neck", None),
    )
    assert not body_spec, f"unconsumed body fields in case {case['id']}: {body_spec}"

    stock = {k: v for k, v in (case.get("stock") or {}).items()}
    chart = SizeChartResolver().resolve(
        ChartContext(
            product_size_chart_json=CHARTS[case["chart"]],
            sellable_sizes=list(stock.keys()),
            demographic=case.get("demographic", "unisex"),
        )
    )
    return engine.recommend(
        body=body,
        chart=chart,
        garment_class=GarmentClass(case.get("garment_class", "unknown")),
        fit_preference=case.get("fit_preference", "regular"),
        material=case.get("material"),
        stock_by_size=stock,
        demographic=case.get("demographic", "unisex"),
    )


@pytest.mark.parametrize("case_id", sorted(CASES), ids=sorted(CASES))
def test_acceptance_case(case_id: str):
    case = CASES[case_id]
    expect = case["expect"]
    result = _run(case)
    why = f"{case_id}: {case['why']}"

    if "recommended" in expect:
        assert result.recommended is expect["recommended"], (
            f"{why}\nGot: {result.as_dict()}"
        )

    if not result.recommended:
        assert isinstance(result, FitRefusal)
        if "reason_code" in expect:
            assert result.reason_code == expect["reason_code"], why
        if "reason_code_in" in expect:
            assert result.reason_code in expect["reason_code_in"], why
        # A refusal must always explain itself in words a shopper can act on.
        assert len(result.message) > 30, why
        return

    assert isinstance(result, FitDecision)

    if "size_in" in expect:
        assert result.recommended_size in expect["size_in"], (
            f"{why}\nExpected one of {expect['size_in']}, got {result.recommended_size}"
        )
    if "size_not_in" in expect:
        assert result.recommended_size not in expect["size_not_in"], why
    if "confidence_min" in expect:
        assert result.confidence >= expect["confidence_min"], why
    if "confidence_max" in expect:
        assert result.confidence <= expect["confidence_max"], why
    if expect.get("estimated_fields_nonempty"):
        assert result.body_used.estimated_fields, why
    if "is_ambiguous" in expect:
        assert result.is_ambiguous is expect["is_ambiguous"], (
            f"{why}\ncandidates={[(c.size, c.score) for c in result.candidates]}"
        )
    if expect.get("alternative_required"):
        assert result.alternative_size, why
    if "chart_source" in expect:
        assert result.chart.provenance.source == expect["chart_source"], why
    if expect.get("chart_not_authoritative"):
        assert not result.chart.provenance.is_authoritative, why
    if expect.get("chart_warning_required"):
        assert result.chart.parse_warnings, why

    # Cross-case relational expectations.
    for key, comparator in (
        ("larger_than_case", lambda a, b: a > b),
        ("not_larger_than_case", lambda a, b: a <= b),
        ("not_smaller_than_case", lambda a, b: a >= b),
        ("same_size_as_case", lambda a, b: a == b),
    ):
        other_id = expect.get(key)
        if other_id:
            other = _run(CASES[other_id])
            assert isinstance(other, FitDecision), f"{why} (comparison case failed)"
            assert comparator(
                size_sort_key(result.recommended_size), size_sort_key(other.recommended_size)
            ), (
                f"{why}\n{case_id}={result.recommended_size} vs "
                f"{other_id}={other.recommended_size}"
            )

    for key, comparator in (
        ("more_confident_than_case", lambda a, b: a > b),
        ("less_confident_than_case", lambda a, b: a < b),
    ):
        other_id = expect.get(key)
        if other_id:
            other = _run(CASES[other_id])
            other_conf = other.confidence if isinstance(other, FitDecision) else 0
            assert comparator(result.confidence, other_conf), (
                f"{why}\n{case_id} confidence={result.confidence} vs "
                f"{other_id}={other_conf}"
            )


# ── invariants that must hold for every recommendation ─────────────────────
def _decisions():
    for case_id, case in sorted(CASES.items()):
        result = _run(case)
        if isinstance(result, FitDecision):
            yield case_id, case, result


def test_recommended_size_is_always_in_stock():
    for case_id, case, decision in _decisions():
        stock = case.get("stock") or {}
        level = stock.get(decision.recommended_size)
        assert level is None or level > 0, (
            f"{case_id}: recommended {decision.recommended_size} with stock {level}"
        )


def test_recommended_size_exists_in_the_resolved_chart():
    for case_id, _case, decision in _decisions():
        chart_sizes = {row.size for row in decision.chart.rows}
        assert decision.recommended_size in chart_sizes, case_id


def test_every_reported_section_traces_to_a_real_user_or_estimated_value():
    """No section may be reported without the number it was computed from."""
    for case_id, _case, decision in _decisions():
        for section in decision.top.sections:
            assert section.body_cm is not None, case_id
            assert section.target_min_cm <= section.target_max_cm, case_id
            # Deviation must be consistent with the band it claims.
            if section.deviation_cm == 0:
                assert section.target_min_cm <= section.body_cm <= section.target_max_cm, case_id
            elif section.deviation_cm > 0:
                assert section.body_cm > section.target_max_cm, case_id
            else:
                assert section.body_cm < section.target_min_cm, case_id


def test_confidence_is_bounded_and_explained():
    for case_id, _case, decision in _decisions():
        assert 5 <= decision.confidence <= 92, case_id
        assert decision.confidence_factors, case_id
        # The factor list must end with the final value, so the arithmetic is
        # auditable rather than asserted.
        assert str(decision.confidence) in decision.confidence_factors[-1], case_id


def test_estimated_inputs_never_reach_measured_grade_confidence():
    """The single most important honesty property of the feature.

    The property is about the sections the decision was actually SCORED on: a
    girth that was estimated but never used (because the chart does not list
    that section) is irrelevant to how much the answer can be trusted.
    """
    for case_id, _case, decision in _decisions():
        scored = decision.top.sections
        if scored and all(s.body_is_estimated for s in scored):
            assert decision.confidence <= 60, (
                f"{case_id}: fully estimated evidence scored {decision.confidence}%"
            )
        elif any(s.body_is_estimated for s in scored):
            assert decision.confidence <= 80, (
                f"{case_id}: partly estimated evidence scored {decision.confidence}%"
            )


def test_estimated_sections_are_always_labelled_in_the_output():
    for case_id, _case, decision in _decisions():
        for section in decision.top.sections:
            field = f"{section.dimension}_cm"
            expected = field in decision.body_used.estimated_fields
            assert section.body_is_estimated is expected, case_id


def test_engine_is_deterministic():
    for case_id, case, _decision in _decisions():
        first = _run(case).as_dict()
        second = _run(case).as_dict()
        assert first == second, case_id


def test_no_hardcoded_marketing_strings_in_any_response():
    """Regression guard for the exact fabricated claims the audit flagged."""
    banned = [
        "Optimal contour (98% match)",
        "Relaxed drape, comfortable movement (95% match)",
        "< 3.2% estimated return probability",
        "True to standard international sizing",
        "modern European tailoring",
    ]
    for case_id, case, decision in _decisions():
        blob = json.dumps(decision.as_dict())
        for phrase in banned:
            assert phrase not in blob, f"{case_id} still emits fabricated claim: {phrase}"


# ── section scoring maths ──────────────────────────────────────────────────
def test_section_score_is_perfect_at_centre_and_strictly_decays():
    assert section_score(0.0, 3.0, 0.0)[0] == 100.0
    edge = section_score(3.0, 3.0, 0.0)[0]
    inside = section_score(1.5, 3.0, 0.0)[0]
    mid = section_score(6.0, 3.0, 0.0)[0]
    far = section_score(12.0, 3.0, 0.0)[0]
    # Inside the band the fit is good but NOT indistinguishable — a flat
    # plateau would let the tie-break, not the measurements, pick the size.
    assert 100.0 > inside > edge >= 85.0
    assert edge > mid > far
    assert far >= 0.0


def test_being_too_small_is_penalised_harder_than_being_too_roomy():
    tight = section_score(+8.0, 3.0, 0.0)[0]
    loose = section_score(-8.0, 3.0, 0.0)[0]
    assert tight < loose


def test_stretch_only_helps_when_the_garment_is_too_small():
    no_stretch = section_score(+6.0, 3.0, 0.0)[0]
    stretchy = section_score(+6.0, 3.0, 0.4)[0]
    assert stretchy > no_stretch
    assert section_score(-6.0, 3.0, 0.4)[0] == section_score(-6.0, 3.0, 0.0)[0]


def test_score_is_monotonic_in_deviation():
    previous = 101.0
    for deviation in [0, 1, 2, 3, 4, 6, 8, 10, 14, 20]:
        score = section_score(float(deviation), 3.0, 0.0)[0]
        assert score <= previous
        previous = score


# ── units and validation ───────────────────────────────────────────────────
def test_imperial_and_metric_bodies_are_identical_after_conversion():
    metric = BodyMeasurements.from_payload(
        units=UnitSystem.METRIC, height=178, weight=78, chest=102
    )
    imperial = BodyMeasurements.from_payload(
        units=UnitSystem.IMPERIAL, height=70.1, weight=172, chest=40.2
    )
    assert abs(metric.height_cm - imperial.height_cm) <= 0.3
    assert abs(metric.chest_cm - imperial.chest_cm) <= 0.3
    assert abs(metric.weight_kg - imperial.weight_kg) <= 0.5


def test_height_in_inches_sent_as_metric_is_rejected_not_silently_used():
    """The classic unit bug: 70 (inches) arriving as centimetres."""
    with pytest.raises(MeasurementValidationError) as exc:
        BodyMeasurements.from_payload(units=UnitSystem.METRIC, height=70, weight=78)
    assert "height_cm" in exc.value.field_errors


@pytest.mark.parametrize(
    "field,value",
    [("chest", 500), ("waist", 5), ("hip", 400), ("shoulder", 200), ("inseam", 5)],
)
def test_out_of_range_girths_are_rejected(field, value):
    with pytest.raises(MeasurementValidationError):
        BodyMeasurements.from_payload(
            units=UnitSystem.METRIC, height=178, weight=78, **{field: value}
        )


def test_implausible_proportions_produce_a_warning_not_a_silent_pass():
    body = BodyMeasurements.from_payload(
        units=UnitSystem.METRIC, height=178, weight=78, chest=90, waist=150
    )
    assert body.warnings


def test_missing_girths_are_none_never_zero_or_a_default_body():
    body = BodyMeasurements.from_payload(units=UnitSystem.METRIC, height=178, weight=78)
    assert body.chest_cm is None and body.waist_cm is None and body.hip_cm is None
    assert body.measured_girths() == {}


# ── chart parsing ──────────────────────────────────────────────────────────
def test_inch_chart_is_converted_once():
    chart = parse_size_chart_json(CHARTS["echo_inches"])
    row = next(r for r in chart.rows if r.size == "M")
    assert 96 <= row.ranges["chest"][0] <= 97   # 38 in
    assert 101 <= row.ranges["chest"][1] <= 102  # 40 in


def test_malformed_chart_yields_no_rows_and_a_recorded_reason():
    chart = parse_size_chart_json(CHARTS["malformed"])
    assert not chart.rows
    assert chart.parse_warnings
    assert chart.provenance.source == "none"


def test_empty_chart_is_not_authoritative():
    chart = parse_size_chart_json(CHARTS["empty"])
    assert not chart.rows
    assert not chart.provenance.is_authoritative


def test_standards_fallback_is_labelled_as_not_the_brands_own():
    chart = SizeChartResolver().resolve(
        ChartContext(product_size_chart_json="{}", sellable_sizes=["S", "M", "L"])
    )
    assert chart.rows
    assert chart.provenance.source == "standard_en13402"
    assert not chart.provenance.is_authoritative
    assert chart.provenance.standard == "EN 13402-3"


def test_standards_fallback_refuses_unmappable_numeric_sizes():
    chart = SizeChartResolver().resolve(
        ChartContext(product_size_chart_json="{}", sellable_sizes=["30", "32", "34"])
    )
    assert not chart.rows


def test_brand_chart_wins_over_the_standard():
    chart = SizeChartResolver().resolve(
        ChartContext(
            product_size_chart_json=CHARTS["borea_small"], sellable_sizes=["S", "M", "L"]
        )
    )
    assert chart.provenance.is_authoritative
    assert chart.rows[0].ranges["chest"] == (82.0, 88.0)


def test_chart_is_restricted_to_sellable_sizes():
    chart = SizeChartResolver().resolve(
        ChartContext(product_size_chart_json=CHARTS["atlas_generous"], sellable_sizes=["M"])
    )
    assert [r.size for r in chart.rows] == ["M"]


def test_size_ordering_covers_letters_and_numbers():
    letters = sorted(["XL", "S", "M", "L", "XS"], key=size_sort_key)
    assert letters == ["XS", "S", "M", "L", "XL"]
    numbers = sorted(["36", "30", "34", "32"], key=size_sort_key)
    assert numbers == ["30", "32", "34", "36"]
