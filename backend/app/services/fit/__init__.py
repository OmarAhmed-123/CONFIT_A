"""CONFIT Fit Finder — the size-recommendation domain.

Why this package exists
-----------------------
The 2026-09-21 feature audit ("Fit Finder والقياسات والتوصية بالمقاس") found the
route and the UI present, but the *computation* unproven: the previous
implementation mapped BMI to a letter size, ignored the user's chest/waist/hip
even when supplied, ignored the product's own size chart, ignored which sizes
the product actually sells, and printed hard-coded strings such as
"Optimal contour (98% match)" and "< 3.2% estimated return probability"
regardless of the inputs. Those strings were not measurements of anything.

This package replaces that with a deterministic, inspectable engine built on
garment-ease theory (the standard approach in apparel fit research: compare
*garment* girth against *body* girth, score the deviation from the ease the
style intends, aggregate the per-section scores into one ranked result and
report the sections that drove the decision).

Layering (each module is pure and independently testable)
---------------------------------------------------------
``units``        value objects + conversion/validation at the boundary (cm/kg
                 canonical; in/lb accepted and converted once, never twice).
``anthropometry``population-level estimation of missing girths from height and
                 weight, explicitly labelled as estimates with uncertainty.
``size_charts``  resolution of the authoritative body-measurement chart for a
                 product: brand-published chart first, standards-based fallback
                 (EN 13402-3 letter-code girth ranges) second, and an explicit
                 "no chart" result third — which the engine refuses to guess past.
``ease``         style/category ease targets and fit-preference shifts.
``engine``       the scoring algorithm: per-section fit deviation -> weighted
                 overall fit score -> ranked candidate sizes -> confidence ->
                 explanation. Returns a refusal object instead of a size when
                 the evidence is insufficient.

Design rules honoured here
--------------------------
* DRY: one conversion table (``units``), one chart resolver, one ease table,
  one scoring function. The API layer, the tests and any future batch job all
  call the same code path.
* Single responsibility / strategy pattern: chart *sources* are pluggable
  (``ChartSource``), so adding a brand-specific importer never touches the
  scoring maths.
* Determinism: no randomness, no wall-clock, no network. Identical inputs give
  identical outputs, which is what makes the acceptance dataset meaningful.
* Honesty: every number the API returns is derived from the inputs. Anything
  the engine does not know is reported as unknown, and low evidence produces a
  refusal, never a confident-looking guess.
"""

from backend.app.services.fit.units import (  # noqa: F401
    BodyMeasurements,
    MeasurementValidationError,
    UnitSystem,
    cm_from,
    kg_from,
)
from backend.app.services.fit.size_charts import (  # noqa: F401
    ChartProvenance,
    SizeChart,
    SizeChartResolver,
    SizeRow,
)
from backend.app.services.fit.ease import GarmentClass, classify_garment, ease_targets
from backend.app.services.fit.engine import (  # noqa: F401
    FitDecision,
    FitEngine,
    FitRefusal,
    SizeCandidate,
)

__all__ = [
    "BodyMeasurements",
    "MeasurementValidationError",
    "UnitSystem",
    "cm_from",
    "kg_from",
    "ChartProvenance",
    "SizeChart",
    "SizeChartResolver",
    "SizeRow",
    "GarmentClass",
    "classify_garment",
    "ease_targets",
    "FitDecision",
    "FitEngine",
    "FitRefusal",
    "SizeCandidate",
]
