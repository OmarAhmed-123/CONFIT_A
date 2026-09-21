"""Coarse girth estimation from height and weight — a PRODUCT HEURISTIC.

Honesty about what this is
--------------------------
This module is **not** a validated anthropometric model, and an earlier version
of this docstring wrongly implied it was. It claimed the coefficients were
"fitted to the published population girth/BMI relationships". They were not
fitted to any dataset by us; they are hand-chosen coefficients that reproduce
plausible population averages. That claim was corrected after audit.

What is actually supportable, and what is not:

* **Waist — directionally supported.** A published NHANES regression predicts
  waist circumference from BMI for adults:
  ``WC = 22.61 + 2.52*BMI + 0.158*AGE`` (men, white non-Hispanic), from
  Bozeman et al., *Predicting waist circumference from body mass index*, BMC
  Medical Research Methodology 2012;12:115, https://doi.org/10.1186/1471-2288-12-115.
  Our waist BMI slope (2.55) is close to the published 2.52, so the *shape* of
  the relationship is externally supported. Our intercept is ~10 cm lower
  because we carry no age term and target a younger apparel-shopping cohort —
  that offset is a **product choice, not a published finding.**

* **Chest, shoulder, neck — NOT externally validated.** NHANES does not measure
  chest circumference at all (its circumference measures are waist, arm, and in
  some cycles head/sagittal diameter). No equivalent public regression backs
  these coefficients. They are plausibility-tuned heuristics. Do not describe
  them as scientific.

* **Hip — partially supported** in direction only (hip girth rises with BMI and
  with stature, cf. Heymsfield et al. on circumference/height allometry), but
  the specific coefficients here are again ours, not a published fit.

Why the estimates still exist
-----------------------------
They are useful as *context* (e.g. widening a confidence interval, ordering
candidates), not as a basis for naming a size. The residual spread below
(±5.5–7.5 cm, wider when sex is unknown) is **larger than one EN 13402-3 size
band (8 cm)**, so an estimate cannot discriminate between neighbouring sizes.

``engine.py`` therefore REFUSES to name a size when every comparable section is
estimated (`INSUFFICIENT_EVIDENCE`). That refusal is the honest consequence of
the numbers in this file. Do not weaken it to raise the recommendation rate.

Hard rules
----------
1. An estimate is never presented as a measurement: every estimated field is
   listed in ``BodyMeasurements.estimated_fields``, surfaced in the API
   response, and reduces confidence.
2. Estimation requires BOTH height and weight. From height alone nothing is
   invented.
3. Outside the fitted BMI support the estimator returns the body unchanged
   rather than extrapolating.

Model form
----------
    girth_cm = a + b * BMI + c * (height_cm - 170)

Sex matters; when unknown, unisex coefficients (midway between the male and
female values) are used and the residual spread is widened accordingly.
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


# Coefficients by demographic. See the module docstring for exactly which of
# these are externally supported (waist: direction supported by the NHANES
# regression in Bozeman 2012) and which are unvalidated product heuristics
# (chest, shoulder, neck — NHANES does not even measure chest circumference).
# "unisex" is used when sex is unknown and carries a deliberately larger
# residual SD.
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
