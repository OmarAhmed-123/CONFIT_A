"""The size-recommendation engine: deterministic, explainable, refusable.

Algorithm (garment-ease scoring, ranked)
----------------------------------------
For a product we resolve one size chart (``size_charts.py``) restricted to the
sizes actually in stock. For every candidate size and every body section the
chart and the user share:

  1. ``target_body_cm``  — the body girth that size is cut for. With a *body*
     chart this is the row's range directly; with a *garment* chart it is the
     garment girth minus the style's ideal ease (``ease.py``).
  2. ``deviation_cm``    — signed distance from the user's girth to that target
     band (0 inside the band, negative if the user is smaller, positive if
     larger).
  3. ``section_score``   — 100 inside the tolerance band, decaying with the
     deviation beyond it. Negative deviations (garment roomier than needed) are
     penalised more gently than positive ones (garment too small), and fabric
     stretch absorbs part of a positive deviation.
  4. ``overall_fit_score`` — the section scores combined with the garment
     class's section weights, renormalised over the sections we could actually
     evaluate, so a missing hip measurement does not silently count as a
     perfect hip.

Sizes are ranked by that score. The top size is the recommendation, and the
runner-up gap drives the confidence: two sizes scoring 91 and 90 is a genuine
toss-up and the response says so instead of projecting false precision.

Refusal
-------
``recommend`` returns a ``FitRefusal`` — never a size — when:
  * the product sells no size (no inventory to recommend from),
  * no size chart can be resolved,
  * the chart and the user share no comparable section,
  * or the only usable evidence is estimated and the top two sizes are
    statistically indistinguishable.

This is the audit's "امنع التوصية عند نقص البيانات" requirement expressed in
code, and it is covered by the acceptance dataset in
``backend/tests/fixtures/fit_acceptance_cases.json``.
"""

from __future__ import annotations

from dataclasses import replace as dc_replace

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.app.services.fit.anthropometry import (
    estimate_missing_girths,
    estimation_disclosure,
    residual_sd,
)
from backend.app.services.fit.ease import (
    EaseProfile,
    GarmentClass,
    ease_targets,
)
from backend.app.services.fit.size_charts import (
    DIMENSIONS,
    SizeChart,
    SizeRow,
    size_sort_key,
)
from backend.app.services.fit.units import BodyMeasurements

ENGINE_VERSION = "fit-engine/2.2.0"

# Body field name -> chart dimension name.
_BODY_TO_DIMENSION: Dict[str, str] = {
    "chest_cm": "chest",
    "waist_cm": "waist",
    "hip_cm": "hip",
    "shoulder_cm": "shoulder",
    "inseam_cm": "inseam",
    "neck_cm": "neck",
}
_DIMENSION_TO_BODY = {v: k for k, v in _BODY_TO_DIMENSION.items()}

# Score decay: how many cm beyond the tolerance band costs a full 100 points.
_DECAY_CM_TIGHT = 9.0    # garment too small — uncomfortable fast
_DECAY_CM_LOOSE = 14.0   # garment too roomy — more forgiving
# Score at exactly the edge of the tolerance band. Keeps the curve strictly
# decreasing inside the band so the best-centred size always wins outright.
_IN_BAND_FLOOR = 88.0

# Verdict bands on the signed deviation, in cm beyond tolerance.
_VERDICT_BANDS: Tuple[Tuple[float, str], ...] = (
    (0.0, "just right"),
    (2.5, "slightly snug" ),
    (6.0, "snug"),
    (math.inf, "too tight"),
)
_VERDICT_BANDS_LOOSE: Tuple[Tuple[float, str], ...] = (
    (0.0, "just right"),
    (3.0, "slightly relaxed"),
    (7.0, "relaxed"),
    (math.inf, "too loose"),
)

# Confidence model — additive evidence, capped. Every term is justified below
# and every deduction is reported in ``confidence_factors`` so the number can
# be audited rather than trusted.
#
# The terms are sized so that a REALISTIC best case (three measured sections,
# brand chart, known garment, well-centred size) lands near the high 80s rather
# than pinning the cap. A model that saturates is a model that cannot express
# the difference between good evidence and excellent evidence — the first draft
# scored "unknown garment type" and "known garment type" identically at 92
# because both were clipped, which made the number decorative.
_CONF_BASE = 22.0
_CONF_PER_MEASURED_SECTION = 12.0     # a real tape measurement of a scored section
_CONF_PER_ESTIMATED_SECTION = 2.5     # a modelled girth is weak evidence
_CONF_BRAND_CHART = 14.0              # the brand's own table beats a public standard
_CONF_DERIVED_CHART = 9.0             # product-specific, but derived from a stated source
_CONF_STANDARD_CHART = 4.0
_CONF_KNOWN_GARMENT_CLASS = 8.0
_CONF_FIT_QUALITY_SWING = 6.0         # how much the winning size's own score moves it
_CONF_MAX = 90.0                      # never claim near-certainty for a remote fit
_CONF_MIN = 5.0
_CONF_FLOOR_FOR_RECOMMENDATION = 35.0 # below this we refuse instead of guessing

# ---------------------------------------------------------------------------
# Confidence BAND — the honest, user-facing signal.
#
# The numeric score above is an internal evidence tally, NOT a probability. It
# is a sum of hand-chosen points; nothing in this system has been calibrated
# against real fit outcomes, so "66% confidence" would imply a frequency
# ("about 2 in 3 of these fit") that we have never measured. Presenting it that
# way is a fabricated statistic even though every term is individually
# defensible.
#
# So the score is reduced to three deterministic bands, defined purely by the
# EVIDENCE actually present, and those bands are what the user is shown. The
# thresholds below are documented product rules, not empirical findings.
_BAND_HIGH = "high"
_BAND_MEDIUM = "medium"
_BAND_LOW = "low"


def confidence_band(
    *,
    measured_sections: int,
    estimated_sections: int,
    chart_is_brand_published: bool,
    chart_is_product_specific: bool,
    fit_score: float,
    is_ambiguous: bool,
) -> Tuple[str, str]:
    """Classify recommendation strength from the evidence. Returns (band, why).

    Deterministic rules, in priority order. These are PRODUCT DECISIONS about
    what we are willing to stand behind - they are not derived from outcome
    data, because we have none.

    high   - at least two directly measured sections, a product-specific chart,
             a clearly best size, and a good fit at that size.
    low    - no directly measured section (everything modelled from height and
             weight), or only a generic standard chart, or the top two sizes
             are too close to separate.
    medium - everything else.
    """
    if measured_sections == 0:
        return _BAND_LOW, (
            "No body girth was measured directly - every section was estimated from "
            "your height and weight, which is a rough guide only."
        )
    if not chart_is_product_specific:
        return _BAND_LOW, (
            "This product has no size chart of its own, so a generic public standard "
            "was used and it may not match how this garment is actually cut."
        )
    if is_ambiguous:
        return _BAND_MEDIUM, (
            "Two sizes score almost the same for your measurements, so which one you "
            "prefer depends on how you like things to sit."
        )
    if measured_sections >= 2 and chart_is_brand_published and fit_score >= 80:
        return _BAND_HIGH, (
            f"{measured_sections} of your measurements were compared directly against "
            "the brand's own published chart and sit comfortably inside one size."
        )
    if measured_sections >= 2 and fit_score >= 80:
        return _BAND_MEDIUM, (
            f"{measured_sections} measurements sit comfortably inside one size, but the "
            "chart is derived from a public standard rather than published by the brand."
        )
    return _BAND_MEDIUM, (
        f"{measured_sections} measurement(s) were compared against this product's chart"
        + (f", with {estimated_sections} section(s) estimated" if estimated_sections else "")
        + "."
    )

# Fit-score floor for naming a size at all. This MUST agree with the lowest
# rating band the response labels as wearable (no_photo_fit_service defines
# <45 as "Does not fit"). It was previously 0, which is unreachable because the
# penalty curve is floored above zero: the engine would return
# `recommended: true` for a size it simultaneously described as "Does not fit"
# with a chest 36 cm outside the range. Confidence is a measure of how sure we
# are, not of whether the garment fits - a directly measured body that clearly
# fits nothing scores HIGH confidence in a bad fit, so the confidence floor
# above can never catch this case. It needs its own gate.
_MIN_FIT_SCORE_FOR_RECOMMENDATION = 45.0

# Margin (score points) below which two sizes are "too close to call".
_AMBIGUITY_MARGIN = 4.0


# ── result value objects ───────────────────────────────────────────────────
@dataclass(frozen=True)
class SectionFit:
    dimension: str
    body_cm: float
    body_is_estimated: bool
    target_min_cm: float
    target_max_cm: float
    deviation_cm: float          # signed: <0 body smaller than target band
    effective_deviation_cm: float  # after fabric stretch absorption
    score: float                 # 0..100
    weight: float
    verdict: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "section": self.dimension,
            "your_measurement_cm": self.body_cm,
            "measurement_is_estimated": self.body_is_estimated,
            "size_fits_bodies_cm": [self.target_min_cm, self.target_max_cm],
            "deviation_cm": self.deviation_cm,
            "score": round(self.score, 1),
            "weight": round(self.weight, 3),
            "verdict": self.verdict,
        }


@dataclass(frozen=True)
class SizeCandidate:
    size: str
    score: float
    sections: Tuple[SectionFit, ...]
    # Tri-state on purpose. ``True``/``False`` mean inventory was consulted and
    # gave an answer; ``None`` means this size was NOT present in the stock map
    # and its availability is genuinely unknown. The previous model was a plain
    # bool computed as ``level is None or level > 0``, which silently reported
    # "in stock" for a size nobody had checked — the response asserted a fact
    # the system did not have.
    in_stock: Optional[bool]
    stock_level: Optional[int] = None

    @property
    def evaluated_dimensions(self) -> Tuple[str, ...]:
        return tuple(s.dimension for s in self.sections)

    @property
    def is_sellable(self) -> bool:
        """Only a size confirmed available may be recommended."""
        return self.in_stock is True

    @property
    def availability(self) -> str:
        if self.in_stock is None:
            return "unknown"
        return "in_stock" if self.in_stock else "out_of_stock"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "size": self.size,
            "fit_score": round(self.score, 1),
            "in_stock": self.in_stock,
            "availability": self.availability,
            "stock_level": self.stock_level,
            "sections": [s.as_dict() for s in self.sections],
        }


@dataclass(frozen=True)
class FitRefusal:
    """An honest 'we cannot tell you' with a machine-readable reason."""

    reason_code: str
    message: str
    missing: Tuple[str, ...] = ()
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    recommended = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "recommended": False,
            "reason_code": self.reason_code,
            "message": self.message,
            "missing": list(self.missing),
            "diagnostics": self.diagnostics,
            "engine_version": ENGINE_VERSION,
        }


@dataclass(frozen=True)
class FitDecision:
    recommended_size: str
    alternative_size: Optional[str]
    # `confidence` is an internal evidence tally in 0-100, NOT a probability.
    # `confidence_band` ("high"/"medium"/"low") is the honest user-facing signal
    # -- see confidence_band() for why the number must not be shown as a percent.
    confidence: int
    confidence_band: str
    confidence_band_reason: str
    confidence_factors: Tuple[str, ...]
    is_ambiguous: bool
    candidates: Tuple[SizeCandidate, ...]
    garment_class: GarmentClass
    ease_profile_used: Dict[str, float]
    chart: SizeChart
    body_used: BodyMeasurements
    notes: Tuple[str, ...]
    demographic: str

    recommended = True

    @property
    def top(self) -> SizeCandidate:
        """The candidate actually RECOMMENDED — not merely the best scoring one.

        These differ whenever the best-scoring size is unavailable: candidates
        are ranked by fit, but the recommendation is the best *sellable* size.
        Returning ``candidates[0]`` here meant ``decision.top`` could describe a
        different (out-of-stock) size than ``recommended_size``, so callers
        reading ``top.in_stock`` could see ``False`` on a successful
        recommendation. Anchor it to the size we actually named.
        """
        for candidate in self.candidates:
            if candidate.size == self.recommended_size:
                return candidate
        return self.candidates[0]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "recommended": True,
            "recommended_size": self.recommended_size,
            "alternative_size": self.alternative_size,
            "confidence": self.confidence,
            "confidence_band": self.confidence_band,
            "confidence_band_reason": self.confidence_band_reason,
            "confidence_factors": list(self.confidence_factors),
            "is_ambiguous": self.is_ambiguous,
            "garment_class": self.garment_class.value,
            "engine_version": ENGINE_VERSION,
            "candidates": [c.as_dict() for c in self.candidates],
            "notes": list(self.notes),
        }


# ── scoring primitives (pure functions — unit-tested directly) ─────────────
def _target_band_for(
    row: SizeRow, dimension: str, chart_is_garment: bool, ease: EaseProfile
) -> Optional[Tuple[float, float]]:
    """The BODY girth band this size targets at ``dimension``."""
    band = row.ranges.get(dimension)
    if band is None:
        return None
    if not chart_is_garment:
        return band
    ideal = ease.ideal(dimension)
    return (round(band[0] - ideal, 1), round(band[1] - ideal, 1))


def _signed_deviation(value: float, band: Tuple[float, float]) -> float:
    if value < band[0]:
        return round(value - band[0], 2)   # negative: body smaller than target
    if value > band[1]:
        return round(value - band[1], 2)   # positive: body larger than target
    return 0.0


def section_score(deviation_cm: float, tolerance_cm: float, stretch_factor: float) -> Tuple[float, float]:
    """(score 0..100, effective deviation) for one section.

    The curve is *strictly* decreasing in |deviation|, with two regimes:

    * inside the tolerance band the fit is acceptable, so the penalty is mild
      (100 down to ``_IN_BAND_FLOOR``) — but it is NOT flat. A flat plateau
      would score several sizes identically and hand the decision to the
      tie-break rule instead of to the measurements, which is exactly how the
      first draft of this engine recommended S to a body that a chart placed
      squarely in L. Being 0 cm from the chart's centre must always beat being
      4 cm from it, even when both are "wearable".
    * beyond the band the score decays on a Gaussian, faster for a garment
      that is too small (``_DECAY_CM_TIGHT``) than for one that is too roomy.

    The two regimes join continuously at |deviation| == tolerance.

    Stretch absorbs part of a *positive* deviation only: elastane helps a
    garment that is slightly small; it does nothing for one that is too big.
    """
    effective = deviation_cm
    if deviation_cm > 0 and stretch_factor > 0:
        effective = round(deviation_cm * (1.0 - min(stretch_factor, 0.6)), 2)

    tolerance = max(tolerance_cm, 0.1)
    magnitude = abs(effective)

    if magnitude <= tolerance:
        ratio = magnitude / tolerance
        score = 100.0 - (100.0 - _IN_BAND_FLOOR) * ratio * ratio
        return round(score, 2), effective

    decay = _DECAY_CM_TIGHT if effective > 0 else _DECAY_CM_LOOSE
    ratio = (magnitude - tolerance) / decay
    score = _IN_BAND_FLOOR * math.exp(-1.35 * ratio * ratio) if ratio < 3 else 0.0
    return round(max(0.0, min(100.0, score)), 2), effective


def _verdict(deviation_cm: float, tolerance_cm: float) -> str:
    excess = abs(deviation_cm) - max(tolerance_cm, 0.0)
    if excess <= 0:
        return "just right"
    bands = _VERDICT_BANDS if deviation_cm > 0 else _VERDICT_BANDS_LOOSE
    for limit, label in bands:
        if excess <= limit:
            return label
    return bands[-1][1]


# ── the engine ─────────────────────────────────────────────────────────────
class FitEngine:
    """Pure domain service. No database, no I/O, no time, no randomness."""

    def _rank_candidates(
        self,
        body_used: BodyMeasurements,
        chart: SizeChart,
        scorable,
        chart_is_garment: bool,
        ease,
        stock: Dict[str, Optional[int]],
    ) -> List[SizeCandidate]:
        """Score every chart row against one body and rank them.

        Extracted so the SAME scoring can be replayed against perturbed bodies
        when probing whether an estimated girth could change the winner (see
        ``_estimate_robustness``). Duplicating the scoring for that check would
        guarantee the two copies drift apart.
        """
        candidates: List[SizeCandidate] = []
        for row in chart.rows:
            sections: List[SectionFit] = []
            for dimension in scorable:
                band = _target_band_for(row, dimension, chart_is_garment, ease)
                if band is None:
                    continue
                body_field = _DIMENSION_TO_BODY[dimension]
                value = getattr(body_used, body_field)
                deviation = _signed_deviation(value, band)
                score, effective = section_score(
                    deviation, ease.tolerance(dimension), ease.stretch_factor
                )
                sections.append(
                    SectionFit(
                        dimension=dimension,
                        body_cm=value,
                        body_is_estimated=body_field in body_used.estimated_fields,
                        target_min_cm=band[0],
                        target_max_cm=band[1],
                        deviation_cm=deviation,
                        effective_deviation_cm=effective,
                        score=score,
                        weight=ease.weight(dimension),
                        verdict=_verdict(effective, ease.tolerance(dimension)),
                    )
                )
            if not sections:
                continue

            # Renormalise weights over the sections we could evaluate: a chart
            # missing 'hip' must not award this size free points for it.
            total_weight = sum(s.weight for s in sections)
            if total_weight <= 0:
                continue
            overall = sum(s.score * s.weight for s in sections) / total_weight

            level = stock.get(row.size.strip().upper())
            candidates.append(
                SizeCandidate(
                    size=row.size,
                    score=round(overall, 2),
                    sections=tuple(sections),
                    # Absent from the stock map => unknown, NOT available.
                    in_stock=(None if level is None else level > 0),
                    stock_level=level,
                )
            )

        # Rank: score first, then the smaller size on a tie (less fabric
        # wasted and the cheaper return), so ordering is deterministic and
        # never depends on dict/DB/sort-stability accidents.
        candidates.sort(key=lambda c: (-c.score, size_sort_key(c.size)))
        return candidates

    def _estimate_robustness(
        self,
        body_used: BodyMeasurements,
        chart: SizeChart,
        scorable,
        chart_is_garment: bool,
        ease,
        stock: Dict[str, Optional[int]],
        demographic: str,
        winner: str,
    ) -> Tuple[bool, Tuple[str, ...]]:
        """Would the winning size still win across each estimate's error bar?

        An estimated girth is NOT a measurement; it is a point drawn from a
        distribution whose documented spread (``residual_sd``) is 5.5-7.5 cm,
        which is comparable to or wider than a whole size band. Scoring it as if
        it were exact silently converts our own uncertainty into a confident
        answer.

        Concretely, for a trouser chart in 5 cm waist steps, a user who measured
        only their hip got size 32 labelled "just right" on a waist WE invented;
        sliding that estimate within its own +/-7 cm error bar produced sizes
        30, 32 and 34. The engine reported one of the three and called it
        unambiguous.

        This replays the real scoring at the low and high end of each estimated
        field's interval (one field at a time, others held at their point
        value). If a different size wins anywhere in that range, the evidence
        does not single out one size and the caller must say so rather than
        pick.

        Deliberately deterministic and conservative -- it is an interval check,
        not a probability model, and produces no percentage.
        """
        if not body_used.estimated_fields:
            return True, ()

        unstable: List[str] = []
        for field in sorted(body_used.estimated_fields):
            centre = getattr(body_used, field, None)
            if centre is None:
                continue
            # Only fields the chart actually scores can change the outcome.
            if _BODY_TO_DIMENSION.get(field) not in set(scorable):
                continue
            sd = residual_sd(field, demographic)
            for probe in (centre - sd, centre + sd):
                if probe <= 0:
                    continue
                # NB: with_estimates() deliberately refuses to overwrite an
                # existing value (it must never clobber a real measurement), so
                # perturbing an already-filled estimate needs replace().
                probed = dc_replace(body_used, **{field: round(probe, 1)})
                ranked = self._rank_candidates(
                    probed, chart, scorable, chart_is_garment, ease, stock
                )
                sellable = [c for c in ranked if c.is_sellable]
                if sellable and sellable[0].size != winner:
                    unstable.append(field)
                    break
        return (not unstable), tuple(unstable)

    def recommend(
        self,
        *,
        body: BodyMeasurements,
        chart: SizeChart,
        garment_class: GarmentClass = GarmentClass.UNKNOWN,
        fit_preference: str = "regular",
        material: Optional[str] = None,
        stock_by_size: Optional[Dict[str, Optional[int]]] = None,
        demographic: str = "unisex",
        allow_estimates: bool = True,
    ) -> FitDecision | FitRefusal:
        notes: List[str] = []

        if not chart.rows:
            return FitRefusal(
                reason_code="NO_SIZE_CHART",
                message=(
                    "No size chart is available for this product, so any size we named "
                    "would be a guess. Ask the brand to publish its measurements, or "
                    "compare with a garment you already own."
                ),
                missing=("size_chart",),
                diagnostics={"chart_warnings": list(chart.parse_warnings)},
            )

        ease = ease_targets(garment_class, fit_preference, material=material)

        # Fill missing girths from height+weight, clearly flagged.
        body_used = body
        if allow_estimates:
            body_used = estimate_missing_girths(body, demographic=demographic)
        disclosure = estimation_disclosure(body_used, demographic)
        if disclosure:
            notes.append(disclosure)
        notes.extend(body_used.warnings)

        chart_is_garment = chart.provenance.measurement_type == "garment"
        if chart_is_garment:
            notes.append(
                "The brand publishes finished-garment measurements; the engine "
                "subtracted this style's ease allowance to compare them to your body."
            )

        # Which sections can we actually score? Intersection of (chart has it),
        # (we know the body value) and (this garment class cares about it).
        scorable: List[str] = []
        for dimension in DIMENSIONS:
            if ease.weight(dimension) <= 0:
                continue
            if not any(dimension in row.ranges for row in chart.rows):
                continue
            if getattr(body_used, _DIMENSION_TO_BODY[dimension], None) is None:
                continue
            scorable.append(dimension)

        if not scorable:
            wanted = [d for d in DIMENSIONS if ease.weight(d) > 0]
            have_chart = sorted({d for row in chart.rows for d in row.ranges})
            missing_body = [
                _DIMENSION_TO_BODY[d]
                for d in wanted
                if d in have_chart and getattr(body_used, _DIMENSION_TO_BODY[d], None) is None
            ]
            return FitRefusal(
                reason_code="NO_COMPARABLE_SECTION",
                message=(
                    "We could not compare a single body section with this product's size "
                    "chart, so there is nothing to base a size on. "
                    + (
                        "Add your " + ", ".join(m.replace("_cm", "") for m in missing_body) + "."
                        if missing_body
                        else "The chart does not list a measurement this garment is sized by."
                    )
                ),
                missing=tuple(missing_body) or ("comparable_section",),
                diagnostics={
                    "sections_this_garment_is_sized_by": wanted,
                    "sections_in_chart": have_chart,
                },
            )

        stock = {k.strip().upper(): v for k, v in (stock_by_size or {}).items()}

        candidates = self._rank_candidates(
            body_used, chart, scorable, chart_is_garment, ease, stock
        )

        if not candidates:
            return FitRefusal(
                reason_code="NO_SCOREABLE_SIZE",
                message="No size in this product's chart could be scored against your measurements.",
                missing=("scoreable_size",),
            )

        in_stock = [c for c in candidates if c.is_sellable]
        if not in_stock:
            # Distinguish "we checked and there is none" from "we could not
            # check". Both refuse, but they are different facts and the user
            # deserves the right one.
            any_known = any(c.in_stock is not None for c in candidates)
            if not any_known:
                return FitRefusal(
                    reason_code="INVENTORY_UNKNOWN",
                    message=(
                        "We could not confirm which sizes of this product are actually "
                        "available, so we will not recommend one. A size we cannot confirm "
                        "is in stock is not a recommendation."
                    ),
                    missing=("inventory",),
                    diagnostics={
                        "best_fitting_size_if_available": candidates[0].size,
                        "inventory_checked": False,
                    },
                )
            return FitRefusal(
                reason_code="NO_SELLABLE_SIZE",
                message=(
                    "Every size of this product is out of stock, so there is no size to "
                    "recommend right now."
                ),
                missing=("inventory",),
                diagnostics={"best_fitting_size_if_restocked": candidates[0].size},
            )

        best = in_stock[0]
        runner_up = in_stock[1] if len(in_stock) > 1 else None
        margin = (best.score - runner_up.score) if runner_up else None
        is_ambiguous = margin is not None and margin < _AMBIGUITY_MARGIN

        # An estimated girth whose error bar reaches into another size cannot
        # single out a size, however decisive the point score looks.
        estimate_robust, unstable_fields = self._estimate_robustness(
            body_used, chart, scorable, chart_is_garment, ease, stock,
            demographic, best.size,
        )
        if not estimate_robust:
            is_ambiguous = True

        if best.score < _MIN_FIT_SCORE_FOR_RECOMMENDATION:
            return FitRefusal(
                reason_code="NO_SIZE_FITS",
                message=(
                    "None of the sizes this product sells is close to your measurements. "
                    "Recommending the least-bad size would mean recommending a return."
                ),
                missing=("fitting_size",),
                diagnostics={
                    "closest_size": best.size,
                    "closest_size_score": best.score,
                    "sections": [s.as_dict() for s in best.sections],
                    "size_comparison_table": [c.as_dict() for c in in_stock],
                },
            )

        # ── No size may be named on estimated evidence alone ────────────────
        # The girth estimator's own published residual SD (5.5-7.5 cm, larger
        # for unknown sex) is WIDER than an EN 13402-3 size band (8 cm across
        # S/M/L). A size derived only from estimated girths therefore carries
        # an uncertainty of more than one full size: the number looks precise
        # but cannot discriminate between neighbouring sizes.
        #
        # Reporting it as a recommendation would be presenting a fabricated
        # input as a finding, which is exactly what this feature's audit
        # prohibits. Confidence alone cannot catch it -- the earlier defects
        # taught us that a scalar score is the wrong instrument for a
        # structural question. So this is an explicit evidence rule.
        if all(s.body_is_estimated for s in best.sections):
            needed = sorted(
                _DIMENSION_TO_BODY[s.dimension].replace("_cm", "") for s in best.sections
            )
            return FitRefusal(
                reason_code="INSUFFICIENT_EVIDENCE",
                message=(
                    "We can't name a size from height and weight alone. Estimating your "
                    + ", ".join(needed)
                    + " from height and weight is typically off by more than a whole "
                    "size, so any size we named would be a guess. Measure your "
                    + " or ".join(needed)
                    + " and we'll give you a real answer."
                ),
                missing=tuple(f"{n}_cm" for n in needed),
                diagnostics={
                    "best_guess_size": best.size,
                    "estimated_only": True,
                    "residual_sd_cm": {
                        _DIMENSION_TO_BODY[s.dimension]: residual_sd(
                            _DIMENSION_TO_BODY[s.dimension], demographic
                        )
                        for s in best.sections
                    },
                    "note": (
                        "Shown for diagnostics only. Deliberately NOT presented to the "
                        "shopper as a recommendation: the estimator's residual spread "
                        "exceeds one size band."
                    ),
                },
            )

        confidence, factors = self._confidence(
            best=best,
            runner_up=runner_up,
            chart=chart,
            garment_class=garment_class,
            body=body_used,
            demographic=demographic,
        )

        if confidence < _CONF_FLOOR_FOR_RECOMMENDATION:
            missing = [
                _DIMENSION_TO_BODY[s.dimension] for s in best.sections if s.body_is_estimated
            ]
            return FitRefusal(
                reason_code="INSUFFICIENT_EVIDENCE",
                message=(
                    "There is not enough solid evidence to name a size. "
                    + (
                        "Measure your "
                        + ", ".join(sorted(m.replace("_cm", "") for m in missing))
                        + " and try again — height and weight alone are too coarse for this garment."
                        if missing
                        else "Add your chest, waist and hip measurements and try again."
                    )
                ),
                missing=tuple(sorted(set(missing))) or ("measurements",),
                diagnostics={
                    "best_guess_size": best.size,
                    "best_guess_confidence": confidence,
                    "confidence_factors": list(factors),
                    "note": (
                        "A best guess is shown for diagnostics only and is deliberately "
                        "NOT presented to the shopper as a recommendation."
                    ),
                },
            )

        if not estimate_robust:
            pretty = ", ".join(f.replace("_cm", "") for f in unstable_fields)
            notes.append(
                f"Your {pretty} was estimated from your height and weight, not measured, "
                f"and that estimate is uncertain enough to reach into a neighbouring "
                f"size. {best.size} is our best reading of the evidence, but we cannot "
                f"narrow it to one size with confidence — measure your {pretty} for a "
                f"firm answer."
            )
        elif is_ambiguous and runner_up is not None:
            notes.append(
                f"Sizes {best.size} and {runner_up.size} score within "
                f"{margin:.1f} points of each other — you are between sizes. "
                f"Pick {best.size} for a closer fit and {runner_up.size} for more room."
            )

        out_of_stock_better = [
            c for c in candidates if not c.is_sellable and c.score > best.score + _AMBIGUITY_MARGIN
        ]
        if out_of_stock_better:
            notes.append(
                f"Size {out_of_stock_better[0].size} would fit you better but is out of stock."
            )

        measured_n = len([s for s in best.sections if not s.body_is_estimated])
        estimated_n = len([s for s in best.sections if s.body_is_estimated])
        band, band_reason = confidence_band(
            measured_sections=measured_n,
            estimated_sections=estimated_n,
            chart_is_brand_published=chart.provenance.is_authoritative,
            chart_is_product_specific=chart.provenance.is_product_specific,
            fit_score=best.score,
            is_ambiguous=is_ambiguous,
        )

        return FitDecision(
            recommended_size=best.size,
            alternative_size=(runner_up.size if runner_up and is_ambiguous else None),
            confidence=confidence,
            confidence_band=band,
            confidence_band_reason=band_reason,
            confidence_factors=tuple(factors),
            is_ambiguous=is_ambiguous,
            candidates=tuple(candidates),
            garment_class=garment_class,
            ease_profile_used=dict(ease.ideal_ease_cm),
            chart=chart,
            body_used=body_used,
            notes=tuple(notes),
            demographic=demographic,
        )

    # ── confidence ─────────────────────────────────────────────────────────
    def _confidence(
        self,
        *,
        best: SizeCandidate,
        runner_up: Optional[SizeCandidate],
        chart: SizeChart,
        garment_class: GarmentClass,
        body: BodyMeasurements,
        demographic: str,
    ) -> Tuple[int, List[str]]:
        """Confidence as an auditable sum of named evidence terms."""
        score = _CONF_BASE
        factors: List[str] = [f"base {_CONF_BASE:.0f}"]

        measured = [s for s in best.sections if not s.body_is_estimated]
        estimated = [s for s in best.sections if s.body_is_estimated]
        if measured:
            gain = _CONF_PER_MEASURED_SECTION * len(measured)
            score += gain
            factors.append(
                f"+{gain:.0f} for {len(measured)} measured section(s): "
                + ", ".join(s.dimension for s in measured)
            )
        if estimated:
            gain = _CONF_PER_ESTIMATED_SECTION * len(estimated)
            score += gain
            factors.append(
                f"+{gain:.0f} for {len(estimated)} estimated section(s) "
                f"(modelled from height/weight, ±"
                f"{max(residual_sd(_DIMENSION_TO_BODY[s.dimension], demographic) for s in estimated):.0f} cm)"
            )

        if chart.provenance.is_authoritative:
            score += _CONF_BRAND_CHART
            factors.append(f"+{_CONF_BRAND_CHART:.0f} brand-published size chart")
        elif chart.provenance.is_product_specific:
            # Authored for THIS product from a stated source. Better than the
            # generic fallback, worse than the brand's own measurements.
            score += _CONF_DERIVED_CHART
            factors.append(
                f"+{_CONF_DERIVED_CHART:.0f} product-specific size chart derived from "
                f"{chart.provenance.standard or 'a stated source'}, not published by the brand"
            )
        else:
            score += _CONF_STANDARD_CHART
            factors.append(
                f"+{_CONF_STANDARD_CHART:.0f} public standard chart "
                f"({chart.provenance.standard or 'generic'}), not the brand's own"
            )

        if garment_class is not GarmentClass.UNKNOWN:
            score += _CONF_KNOWN_GARMENT_CLASS
            factors.append(
                f"+{_CONF_KNOWN_GARMENT_CLASS:.0f} known garment type ({garment_class.value})"
            )
        else:
            factors.append("+0 garment type unknown — generic ease assumptions used")

        # How well the winning size actually fits, not just whether it won.
        quality = (best.score - 70.0) / 30.0
        adjust = round(_CONF_FIT_QUALITY_SWING * max(-1.0, min(1.0, quality)), 1)
        score += adjust
        factors.append(f"{adjust:+.1f} from the winning size's own fit score ({best.score:.0f}/100)")

        # A photo finish between two sizes is genuine uncertainty.
        if runner_up is not None:
            margin = best.score - runner_up.score
            if margin < _AMBIGUITY_MARGIN:
                penalty = round(12.0 * (1.0 - margin / _AMBIGUITY_MARGIN), 1)
                score -= penalty
                factors.append(
                    f"-{penalty:.1f} because size {runner_up.size} scores within "
                    f"{margin:.1f} points (between sizes)"
                )

        if chart.provenance.updated_at is None and chart.provenance.is_authoritative:
            score -= 3.0
            factors.append("-3 brand chart has no published update date")

        final = int(round(max(_CONF_MIN, min(_CONF_MAX, score))))
        factors.append(f"= {final} (capped at {_CONF_MAX:.0f}: a remote fit is never certain)")
        return final, factors
