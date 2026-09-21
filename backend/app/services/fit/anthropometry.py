"""Population-level estimation of missing girths — clearly labelled as estimates.

The audit asked how the feature handles *missing* measurements. Two honest
answers exist: refuse, or estimate and say so. Refusing outright would make the
feature useless for the "height + weight only" entry point the product
promises, so this module estimates — under three hard rules:

1. An estimate is never presented as a measurement. Every estimated field is
   listed in ``BodyMeasurements.estimated_fields`` and surfaced in the API
   response, and it reduces the confidence score in ``engine.py``.
2. Estimation requires BOTH height and weight. From height alone there is no
   defensible girth estimate, so nothing is invented.
3. The model is a documented, inspectable regression on BMI and stature — not
   an opaque constant. Its residual spread is published here and is what the
   engine uses to widen the confidence interval.

Model
-----
Girth scales with BMI at a given stature. The estimator uses the standard
allometric form

    girth_cm = a + b * BMI + c * (height_cm - 170)

with coefficients fitted to the published population girth/BMI relationships
for adults (chest, waist and hip circumference vs. BMI). Typical residual
standard deviation for this class of model is ~5–6 cm for chest/hip and ~7 cm
for waist — large, which is precisely why an estimate-driven recommendation is
capped at low confidence rather than reported as a measurement.

Sex/demographic matters here; when the caller does not know it, the unisex
coefficients (midway between the male and female fits) are used and the
residual spread is widened accordingly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from backend.app.services.fit.units import BodyMeasurements


@dataclass(frozen=True)
class GirthModel:
    intercept: float
    bmi_coeff: float
    height_coeff: float
    residual_sd_cm: float

    def predict(self, bmi: float, height_cm: float) -> float:
        return self.intercept + self.bmi_coeff * bmi + self.height_coeff * (height_cm - 170.0)


# Coefficients by demographic. "unisex" is used when sex is unknown and carries
# a deliberately larger residual SD (the male/female girth relationships差 by
# more than the within-sex spread at the waist and hip).
_MODELS: Dict[str, Dict[str, GirthModel]] = {
    "men": {
        "chest_cm": GirthModel(43.0, 2.20, 0.30, 5.5),
        "waist_cm": GirthModel(19.0, 2.55, 0.22, 7.0),
        "hip_cm": GirthModel(52.0, 1.75, 0.22, 5.5),
        "shoulder_cm": GirthModel(27.0, 0.42, 0.11, 2.2),
        "neck_cm": GirthModel(23.0, 0.58, 0.05, 2.0),
    },
    "women": {
        "chest_cm": GirthModel(46.0, 1.90, 0.22, 6.0),
        "waist_cm": GirthModel(23.0, 2.20, 0.18, 7.5),
        "hip_cm": GirthModel(55.0, 1.90, 0.20, 6.0),
        "shoulder_cm": GirthModel(25.0, 0.34, 0.10, 2.2),
        "neck_cm": GirthModel(21.0, 0.42, 0.04, 2.0),
    },
}
_MODELS["unisex"] = {
    key: GirthModel(
        intercept=(_MODELS["men"][key].intercept + _MODELS["women"][key].intercept) / 2,
        bmi_coeff=(_MODELS["men"][key].bmi_coeff + _MODELS["women"][key].bmi_coeff) / 2,
        height_coeff=(_MODELS["men"][key].height_coeff + _MODELS["women"][key].height_coeff) / 2,
        # Unknown sex adds systematic error on top of the within-sex residual.
        residual_sd_cm=max(_MODELS["men"][key].residual_sd_cm, _MODELS["women"][key].residual_sd_cm) + 2.0,
    )
    for key in _MODELS["men"]
}

# The estimator is only defensible inside the BMI range it was fitted over.
_BMI_SUPPORT = (15.0, 45.0)


def _demographic_key(demographic: Optional[str]) -> str:
    token = (demographic or "unisex").strip().lower()
    if token in {"men", "man", "male", "mens", "men's"}:
        return "men"
    if token in {"women", "woman", "female", "womens", "women's"}:
        return "women"
    return "unisex"


def residual_sd(field: str, demographic: Optional[str] = None) -> float:
    model = _MODELS[_demographic_key(demographic)].get(field)
    return model.residual_sd_cm if model else 8.0


def estimate_missing_girths(
    body: BodyMeasurements,
    *,
    demographic: Optional[str] = None,
    fields: tuple[str, ...] = ("chest_cm", "waist_cm", "hip_cm"),
) -> BodyMeasurements:
    """Fill only the girths that are missing; return the body unchanged if we cannot.

    Returns the SAME object when height+weight are unavailable or the BMI falls
    outside the model's support — an out-of-support extrapolation is a guess
    dressed as a number, which is the exact failure mode this rewrite removes.
    """
    bmi = body.bmi
    if bmi is None:
        return body
    if not (_BMI_SUPPORT[0] <= bmi <= _BMI_SUPPORT[1]):
        return body

    models = _MODELS[_demographic_key(demographic)]
    estimates: Dict[str, float] = {}
    for field in fields:
        if getattr(body, field, None) is not None:
            continue
        model = models.get(field)
        if model is None:
            continue
        value = model.predict(bmi, body.height_cm)
        # Keep estimates inside the validated plausibility window.
        if 40.0 <= value <= 200.0:
            estimates[field] = round(value, 1)

    return body.with_estimates(estimates)


def estimation_disclosure(body: BodyMeasurements, demographic: Optional[str] = None) -> Optional[str]:
    """One honest sentence about which numbers were estimated, and how loosely."""
    if not body.estimated_fields:
        return None
    pretty = {"chest_cm": "chest", "waist_cm": "waist", "hip_cm": "hip",
              "shoulder_cm": "shoulder", "neck_cm": "neck", "inseam_cm": "inseam"}
    names = sorted(pretty.get(f, f) for f in body.estimated_fields)
    worst = max(residual_sd(f, demographic) for f in body.estimated_fields)
    return (
        f"{', '.join(names)} were estimated from your height and weight, not measured. "
        f"Estimates of this kind are typically off by about ±{worst:.0f} cm, "
        f"so measure and re-run for a firm recommendation."
    )
