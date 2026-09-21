"""Fit Finder application service — orchestration only, no fit maths here.

Architecture
------------
This is the *application* layer of the Fit Finder feature. It owns one job:
turn a request plus the database into the inputs the pure domain engine
(``backend/app/services/fit/``) needs, then turn the engine's decision into the
API contract. All sizing intelligence lives in the domain package, so it can be
unit-tested with no database and reused by any caller (API, batch re-scoring,
the PDP size hint) without duplication.

    controller  ->  NoPhotoFitService  ->  SizeChartResolver  ->  FitEngine
                          |                      |                    |
                    DB / inventory        chart provenance      pure scoring

What changed versus the pre-2026-09-21 implementation, and why
--------------------------------------------------------------
The audit "Fit Finder والقياسات والتوصية بالمقاس" recorded the feature as
"متحققة جزئيًا — المسارات موجودة، النتيجة الحسابية غير مثبتة". Concretely the
old service:

* mapped BMI alone to S/M/L/XL and **ignored** the chest/waist/hip the user
  had taken the trouble to measure;
* returned the same hard-coded size table (92-96 / 96-102 / …) for every
  product of every brand, ignoring ``products.size_chart_json``;
* recommended sizes the product does not sell and cannot ship;
* printed fixed strings — "Optimal contour (98% match)", "Ultra Low — < 3.2%
  estimated return probability", "uses modern European tailoring. True to
  standard international sizing." — that were unrelated to the inputs and to
  the brand. Those were the "ادعاءات" the audit warned about, and they are
  gone: nothing in this response is a constant pretending to be a measurement.

Every field returned below is now derived from the request, the product's own
chart, its live inventory and the documented ease model — or is explicitly
reported as unknown/refused.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from backend.app.core.exceptions import ResourceNotFoundError
from backend.app.repositories.catalog_repository import CatalogRepository
from backend.app.services.fit.ease import (
    GarmentClass,
    classify_garment,
)
from backend.app.services.fit.engine import (
    ENGINE_VERSION,
    FitDecision,
    FitEngine,
    FitRefusal,
    _MIN_FIT_SCORE_FOR_RECOMMENDATION,
)
from backend.app.services.fit.size_charts import (
    ChartContext,
    SizeChart,
    SizeChartResolver,
    normalise_size_label,
)
from backend.app.services.fit.units import BodyMeasurements, UnitSystem


class NoPhotoFitService:
    """Zero-photo size recommendation backed by real charts and real stock."""

    def __init__(
        self,
        db: Session,
        *,
        engine: Optional[FitEngine] = None,
        resolver: Optional[SizeChartResolver] = None,
    ):
        # Dependencies are injected (with sane defaults) so tests can substitute
        # a stub chart source without touching the database.
        self.db = db
        self.catalog_repo = CatalogRepository(db)
        self.engine = engine or FitEngine()
        self.resolver = resolver or SizeChartResolver()

    # ── public API ─────────────────────────────────────────────────────────
    def calculate_fit(
        self,
        product_id: int,
        *,
        units: str = "metric",
        height: Optional[float] = None,
        weight: Optional[float] = None,
        chest: Optional[float] = None,
        waist: Optional[float] = None,
        hip: Optional[float] = None,
        shoulder: Optional[float] = None,
        inseam: Optional[float] = None,
        neck: Optional[float] = None,
        body_shape: Optional[str] = None,
        preferred_fit: str = "regular",
        demographic: str = "unisex",
    ) -> Dict[str, Any]:
        product = self.catalog_repo.get_product_by_id(product_id)
        if not product:
            raise ResourceNotFoundError("Product", product_id)

        body = BodyMeasurements.from_payload(
            units=UnitSystem(units),
            height=height,
            weight=weight,
            chest=chest,
            waist=waist,
            hip=hip,
            shoulder=shoulder,
            inseam=inseam,
            neck=neck,
            body_shape=body_shape,
        )

        stock_by_size = self._stock_by_size(product)
        sellable = [s for s, level in stock_by_size.items() if level is None or level > 0]

        chart = self.resolver.resolve(
            ChartContext(
                product_size_chart_json=product.size_chart_json,
                # Restrict to sizes that EXIST for this product (sellable first,
                # falling back to the full size list so an out-of-stock product
                # gets the honest NO_SELLABLE_SIZE refusal rather than the
                # ambiguous NO_SIZE_CHART one).
                sellable_sizes=sellable or list(stock_by_size.keys()),
                demographic=demographic,
                brand_name=(product.brand.brand_name if product.brand else None),
                category_slug=(product.category.slug if product.category else None),
            )
        )

        garment_class = classify_garment(
            category_slug=(product.category.slug if product.category else None),
            category_name=(product.category.name if product.category else None),
            title=product.title,
            style_tags=self._json_list(product.style_tags),
        )

        decision = self.engine.recommend(
            body=body,
            chart=chart,
            garment_class=garment_class,
            fit_preference=preferred_fit,
            material=product.material,
            stock_by_size=stock_by_size,
            demographic=demographic,
        )

        if isinstance(decision, FitRefusal):
            return self._refusal_response(product, chart, garment_class, body, decision)
        return self._decision_response(product, decision)

    # ── response builders ──────────────────────────────────────────────────
    def _decision_response(self, product, decision: FitDecision) -> Dict[str, Any]:
        top = decision.top
        by_size = {c.size: c for c in decision.candidates}

        size_comparison_table = [
            {
                "size": c.size,
                # Per-section body ranges this size is cut for — from the real
                # chart, so two brands legitimately show different numbers.
                "ranges_cm": {
                    s.dimension: [s.target_min_cm, s.target_max_cm] for s in c.sections
                },
                "fit_score": round(c.score, 1),
                "fit_rating": self._rating_label(c.score),
                # Tri-state: None means inventory could not be confirmed for
                # this size. `availability` spells it out for clients that
                # would otherwise read a null as false.
                "in_stock": c.in_stock,
                "availability": c.availability,
                "stock_level": c.stock_level,
                "is_recommended": c.size == decision.recommended_size,
            }
            for c in decision.candidates
        ]

        fit_breakdown = {
            s.dimension: (
                f"your {s.body_cm:g} cm vs {s.target_min_cm:g}–{s.target_max_cm:g} cm for size "
                f"{top.size}: {s.verdict}"
                + (f" ({s.deviation_cm:+g} cm)" if s.deviation_cm else "")
                + (" — estimated, not measured" if s.body_is_estimated else "")
            )
            for s in top.sections
        }

        brand = product.brand
        return {
            "product_id": product.id,
            "recommended": True,
            "recommended_size": decision.recommended_size,
            "alternative_size": decision.alternative_size,
            "is_between_sizes": decision.is_ambiguous,
            # `confidence_band` is the honest headline signal. `confidence_score`
            # is retained for backwards compatibility but is an internal
            # evidence tally, not a probability — clients should show the band.
            "confidence_band": decision.confidence_band,
            "confidence_band_reason": decision.confidence_band_reason,
            "confidence_score": decision.confidence,
            "confidence_is_probability": False,
            "confidence_factors": list(decision.confidence_factors),
            "is_estimated": bool(decision.body_used.estimated_fields),
            "fit_verdict": self._rating_label(top.score),
            "confidence_disclosure": self._disclosure(decision),
            "fit_breakdown": fit_breakdown,
            "size_comparison_table": size_comparison_table,
            "measurements_used": {
                **decision.body_used.as_dict(),
                "estimated_fields": sorted(decision.body_used.estimated_fields),
                "sections_scored": list(top.evaluated_dimensions),
            },
            "size_chart_source": decision.chart.provenance.as_dict(),
            "garment": {
                "garment_class": decision.garment_class.value,
                "material": product.material,
                "ease_targets_cm": decision.ease_profile_used,
                "category": (product.category.name if product.category else None),
            },
            "brand_sizing_tendency": self._brand_tendency(brand, decision.chart),
            "return_risk": self._return_risk(decision, brand),
            "notes": list(decision.notes),
            "engine_version": ENGINE_VERSION,
            # Backwards compatibility: the previous contract exposed this as a
            # free-text field and the PDP still renders it.
            "return_risk_score": self._return_risk(decision, brand)["label"],
        }

    def _refusal_response(
        self,
        product,
        chart: SizeChart,
        garment_class: GarmentClass,
        body: BodyMeasurements,
        refusal: FitRefusal,
    ) -> Dict[str, Any]:
        """A refusal is a first-class successful response, not an error.

        The engine could not justify a size; saying so plainly (HTTP 200 with
        ``recommended: false``) is the honest outcome the audit asked for. It
        is NOT a 500, and it must never degrade into a guess.
        """
        return {
            "product_id": product.id,
            "recommended": False,
            "recommended_size": None,
            "alternative_size": None,
            "is_between_sizes": False,
            "confidence_score": 0,
            "confidence_factors": [],
            "is_estimated": bool(body.estimated_fields),
            "fit_verdict": "No recommendation",
            "confidence_disclosure": refusal.message,
            "reason_code": refusal.reason_code,
            "missing": list(refusal.missing),
            "diagnostics": refusal.diagnostics,
            "fit_breakdown": {},
            "size_comparison_table": [],
            "measurements_used": {
                **body.as_dict(),
                "estimated_fields": sorted(body.estimated_fields),
                "sections_scored": [],
            },
            "size_chart_source": chart.provenance.as_dict(),
            "garment": {
                "garment_class": garment_class.value,
                "material": product.material,
                "ease_targets_cm": {},
                "category": (product.category.name if product.category else None),
            },
            "brand_sizing_tendency": self._brand_tendency(product.brand, chart),
            "return_risk": {
                "label": "Unknown",
                "basis": "no recommendation was made, so no return risk is claimed",
            },
            "return_risk_score": "Unknown — no recommendation was made",
            "notes": list(chart.parse_warnings),
            "engine_version": ENGINE_VERSION,
        }

    # ── helpers ────────────────────────────────────────────────────────────
    @staticmethod
    def _json_list(raw: Any) -> List[str]:
        if not raw:
            return []
        try:
            value = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            return []
        return [str(v) for v in value] if isinstance(value, list) else []

    @staticmethod
    def _stock_by_size(product) -> Dict[str, Optional[int]]:
        """Live sellable quantity per size label (summed across colourways)."""
        stock: Dict[str, Optional[int]] = {}
        for sku in getattr(product, "skus", None) or []:
            label = normalise_size_label(sku.size)
            if not label:
                continue
            level = int(sku.stock_level or 0) if sku.is_in_stock else 0
            stock[label] = (stock.get(label) or 0) + level
        return stock

    # The "Does not fit" band and the engine's refusal floor are THE SAME
    # number by construction. They were previously two independent literals
    # that happened to agree; when they disagreed (refusal floor 0 vs label
    # threshold 45) production recommended a size it simultaneously described
    # as "Does not fit". Importing the constant makes that drift impossible.
    _DOES_NOT_FIT_BELOW = _MIN_FIT_SCORE_FOR_RECOMMENDATION

    @staticmethod
    def _rating_label(score: float) -> str:
        if score >= 92:
            return "Excellent fit"
        if score >= 80:
            return "Good fit"
        if score >= 65:
            return "Acceptable fit"
        if score >= NoPhotoFitService._DOES_NOT_FIT_BELOW:
            return "Poor fit"
        return "Does not fit"

    @staticmethod
    def _disclosure(decision: FitDecision) -> str:
        chart_src = decision.chart.provenance
        if chart_src.is_authoritative:
            chart_phrase = "the brand's published size chart" + (
                f" (updated {chart_src.updated_at})"
                if chart_src.updated_at
                else " (no update date published)"
            )
        elif chart_src.is_product_specific:
            chart_phrase = (
                f"this product's size chart, derived from {chart_src.standard or 'a stated source'} "
                f"rather than published by the brand"
            ) + (f" (reviewed {chart_src.updated_at})" if chart_src.updated_at else "")
        else:
            chart_phrase = (
                f"the public {chart_src.standard or 'standard'} size chart, "
                f"not the brand's own measurements"
            )
        measured = [s.dimension for s in decision.top.sections if not s.body_is_estimated]
        estimated = [s.dimension for s in decision.top.sections if s.body_is_estimated]
        evidence = (
            f"measured {', '.join(measured)}" if measured else "no measured body sections"
        )
        if estimated:
            evidence += f" plus estimated {', '.join(estimated)}"
        return (
            f"Size {decision.recommended_size} — {decision.confidence_band} confidence, from "
            f"{evidence}, compared against {chart_phrase}. "
            f"{decision.confidence_band_reason} "
            "This is a rule-based rating of how good the evidence is, not a statistical "
            "probability: we have not measured how often these recommendations turn out "
            "to be right."
        )

    @staticmethod
    def _brand_tendency(brand, chart: SizeChart) -> Dict[str, Any]:
        """Only claims we can actually support from stored data.

        The old copy asserted every brand "uses modern European tailoring. True
        to standard international sizing." for brands nobody had measured. We
        now report *what we know*: whether the brand published its own chart,
        and its recorded return-rate position versus the category benchmark —
        both real columns — and explicitly say when we have no sizing signal.
        """
        name = getattr(brand, "brand_name", None) or "This brand"
        if chart.provenance.is_authoritative:
            summary = f"{name} publishes its own size chart; sizing is matched against it directly."
        elif chart.provenance.is_product_specific:
            summary = (
                f"{name} has not published its own chart. This product carries a size chart "
                f"derived from {chart.provenance.standard or 'a stated public source'}, which is "
                f"specific to this garment but is not the brand's own measurement."
            )
        else:
            summary = (
                f"{name} has not published a size chart. Sizes below are matched against the "
                f"public {chart.provenance.standard or 'standard'} chart, which may differ from "
                "this brand's actual cut."
            )

        benchmark = getattr(brand, "return_rate_benchmark", None)
        current = getattr(brand, "current_return_rate", None)
        signal = None
        if isinstance(benchmark, int) and isinstance(current, int):
            if current < benchmark:
                signal = (
                    f"Recorded return rate {current}% is below the {benchmark}% category benchmark."
                )
            elif current > benchmark:
                signal = (
                    f"Recorded return rate {current}% is above the {benchmark}% category "
                    "benchmark — check the chart carefully."
                )
            else:
                signal = f"Recorded return rate matches the {benchmark}% category benchmark."

        return {
            "summary": summary,
            "has_published_chart": chart.provenance.is_authoritative,
            "chart_updated_at": chart.provenance.updated_at,
            "return_rate_signal": signal,
            "known_size_bias": None,
            "known_size_bias_note": (
                "CONFIT does not yet collect per-brand fit feedback, so no "
                "'runs small / runs large' claim is made."
            ),
        }

    @staticmethod
    def _return_risk(decision: FitDecision, brand) -> Dict[str, Any]:
        """Qualitative risk band derived from fit score, confidence and ambiguity.

        Deliberately NOT a fake percentage. The previous "< 3.2% estimated
        return probability" implied a calibrated model against observed returns;
        no such model or data exists here, and inventing the number was the
        clearest false claim in the old response.
        """
        score = decision.top.score
        confidence = decision.confidence
        if decision.is_ambiguous:
            label, basis = (
                "Elevated",
                "two sizes score almost identically, so a size-related return is more likely",
            )
        elif score >= 90 and confidence >= 75:
            label, basis = (
                "Low",
                "the recommended size sits inside the chart's range on every scored section, "
                "from measured inputs and the brand's own chart",
            )
        elif score >= 75 and confidence >= 60:
            label, basis = ("Moderate", "a good match, but part of the evidence is indirect")
        else:
            label, basis = (
                "Elevated",
                "the fit score or the evidence behind it is weak",
            )
        return {
            "label": label,
            "basis": basis,
            "fit_score": round(score, 1),
            "confidence": confidence,
            "note": (
                "Qualitative band, not a calibrated probability: CONFIT does not yet "
                "have observed return outcomes to calibrate one against."
            ),
        }

    # ── reuse by other features (PDP size hint) ────────────────────────────
    def quick_size_hint(
        self, product_id: int, body: BodyMeasurements, *, preferred_fit: str = "regular"
    ) -> Optional[str]:
        """The single size string for surfaces that only have room for one.

        Exposed so the product page never re-implements sizing (DRY). Returns
        ``None`` when the engine refuses — callers must render "no
        recommendation", never a fallback guess.
        """
        product = self.catalog_repo.get_product_by_id(product_id)
        if not product:
            return None
        stock = self._stock_by_size(product)
        chart = self.resolver.resolve(
            ChartContext(
                product_size_chart_json=product.size_chart_json,
                sellable_sizes=[s for s, lvl in stock.items() if lvl is None or lvl > 0],
                category_slug=(product.category.slug if product.category else None),
            )
        )
        decision = self.engine.recommend(
            body=body,
            chart=chart,
            garment_class=classify_garment(
                category_slug=(product.category.slug if product.category else None),
                category_name=(product.category.name if product.category else None),
                title=product.title,
                style_tags=self._json_list(product.style_tags),
            ),
            fit_preference=preferred_fit,
            material=product.material,
            stock_by_size=stock,
        )
        return decision.recommended_size if isinstance(decision, FitDecision) else None
