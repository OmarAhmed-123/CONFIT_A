"""Units, bounds and the canonical body-measurement value object.

Audit finding this closes
-------------------------
"لم يتحقق الفحص من حدود القيم، الوحدات، التحويل بين cm/in، أو التعامل مع قياسات
ناقصة" — value bounds, units, cm/in conversion and missing measurements were
never verified. Previously the *frontend* converted inches to centimetres and
the backend simply trusted whatever number arrived; a client that forgot to
convert (or converted twice) produced a silently wrong recommendation with no
way to tell from the response.

The fix: the wire contract carries the unit system explicitly, conversion
happens exactly once, here, and every value is bounds-checked against
anthropometric plausibility *after* conversion. Out-of-range input is a 422
with the offending field — never a recommendation computed from nonsense.

Canonical internal units are centimetres and kilograms. Nothing downstream of
this module ever sees inches or pounds.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Dict, Optional

CM_PER_IN = 2.54
KG_PER_LB = 0.45359237


class UnitSystem(str, Enum):
    METRIC = "metric"      # cm / kg
    IMPERIAL = "imperial"  # in / lb


class MeasurementValidationError(ValueError):
    """Raised with a per-field map so the API can answer 422 precisely."""

    def __init__(self, field_errors: Dict[str, str]):
        self.field_errors = dict(field_errors)
        super().__init__("; ".join(f"{k}: {v}" for k, v in sorted(field_errors.items())))


def cm_from(value: Optional[float], units: UnitSystem) -> Optional[float]:
    """Length -> centimetres, rounded to 0.1 cm (below tape-measure precision)."""
    if value is None:
        return None
    cm = float(value) * (CM_PER_IN if units is UnitSystem.IMPERIAL else 1.0)
    return round(cm, 1)


def kg_from(value: Optional[float], units: UnitSystem) -> Optional[float]:
    """Mass -> kilograms, rounded to 0.1 kg."""
    if value is None:
        return None
    kg = float(value) * (KG_PER_LB if units is UnitSystem.IMPERIAL else 1.0)
    return round(kg, 1)


def in_from_cm(value_cm: Optional[float]) -> Optional[float]:
    if value_cm is None:
        return None
    return round(value_cm / CM_PER_IN, 1)


# Plausibility bounds in canonical units. These are deliberately wide (they
# must not exclude real bodies) but tight enough to catch unit mistakes: a
# height of 70 (inches entered as cm) and a chest of 250 both fail here.
BOUNDS_CM: Dict[str, tuple[float, float]] = {
    "height_cm": (100.0, 250.0),
    "chest_cm": (50.0, 200.0),
    "waist_cm": (40.0, 200.0),
    "hip_cm": (50.0, 200.0),
    "shoulder_cm": (25.0, 70.0),
    "inseam_cm": (50.0, 110.0),
    "neck_cm": (25.0, 70.0),
}
BOUNDS_WEIGHT_KG = (30.0, 300.0)

# Internal consistency rules. A body whose stated waist exceeds its stated
# chest by more than this is not impossible, but a waist *larger than the hip
# by 40 cm* is almost always a data-entry error; we surface it as a warning
# (recorded in the response) rather than rejecting a real body.
IMPLAUSIBLE_RATIOS: Dict[str, tuple[str, str, float, str]] = {
    "waist_vs_chest": ("waist_cm", "chest_cm", 1.6, "waist is more than 60% larger than chest"),
    "waist_vs_hip": ("waist_cm", "hip_cm", 1.6, "waist is more than 60% larger than hip"),
    "chest_vs_waist": ("chest_cm", "waist_cm", 2.2, "chest is more than 2.2x the waist"),
}


@dataclass(frozen=True)
class BodyMeasurements:
    """Validated body measurements in canonical units.

    Only ``height_cm`` is required — it is the one dimension every flow has and
    the anchor for population-based estimation. Every girth is optional and
    ``None`` means *unknown*, never zero and never a default body.
    """

    height_cm: float
    weight_kg: Optional[float] = None
    chest_cm: Optional[float] = None
    waist_cm: Optional[float] = None
    hip_cm: Optional[float] = None
    shoulder_cm: Optional[float] = None
    inseam_cm: Optional[float] = None
    neck_cm: Optional[float] = None
    body_shape: Optional[str] = None
    # Fields that were estimated rather than supplied by the user.
    estimated_fields: frozenset[str] = frozenset()
    warnings: tuple[str, ...] = ()

    # ── construction ────────────────────────────────────────────────────────
    @classmethod
    def from_payload(
        cls,
        *,
        units: UnitSystem | str = UnitSystem.METRIC,
        height: Optional[float],
        weight: Optional[float] = None,
        chest: Optional[float] = None,
        waist: Optional[float] = None,
        hip: Optional[float] = None,
        shoulder: Optional[float] = None,
        inseam: Optional[float] = None,
        neck: Optional[float] = None,
        body_shape: Optional[str] = None,
    ) -> "BodyMeasurements":
        """Convert once, validate once. Raises MeasurementValidationError."""
        unit_system = UnitSystem(units) if not isinstance(units, UnitSystem) else units
        errors: Dict[str, str] = {}

        if height is None:
            raise MeasurementValidationError({"height": "height is required"})

        values = {
            "height_cm": cm_from(height, unit_system),
            "chest_cm": cm_from(chest, unit_system),
            "waist_cm": cm_from(waist, unit_system),
            "hip_cm": cm_from(hip, unit_system),
            "shoulder_cm": cm_from(shoulder, unit_system),
            "inseam_cm": cm_from(inseam, unit_system),
            "neck_cm": cm_from(neck, unit_system),
        }
        weight_kg = kg_from(weight, unit_system)

        for field, value in values.items():
            if value is None:
                continue
            lo, hi = BOUNDS_CM[field]
            if not (lo <= value <= hi):
                unit_label = "cm" if unit_system is UnitSystem.METRIC else "in"
                shown = value if unit_system is UnitSystem.METRIC else in_from_cm(value)
                lo_s = lo if unit_system is UnitSystem.METRIC else in_from_cm(lo)
                hi_s = hi if unit_system is UnitSystem.METRIC else in_from_cm(hi)
                errors[field] = (
                    f"{shown} {unit_label} is outside the plausible range "
                    f"{lo_s}–{hi_s} {unit_label}"
                )

        if weight_kg is not None:
            lo, hi = BOUNDS_WEIGHT_KG
            if not (lo <= weight_kg <= hi):
                errors["weight_kg"] = (
                    f"{weight_kg} kg is outside the plausible range {lo}–{hi} kg"
                )

        if errors:
            raise MeasurementValidationError(errors)

        warnings: list[str] = []
        for _rule, (a, b, ratio, message) in IMPLAUSIBLE_RATIOS.items():
            va, vb = values[a], values[b]
            if va is not None and vb is not None and vb > 0 and va / vb > ratio:
                warnings.append(
                    f"Unusual proportions: {message} "
                    f"({a}={va} cm, {b}={vb} cm). Double-check how you measured."
                )

        return cls(
            height_cm=values["height_cm"],  # type: ignore[arg-type]
            weight_kg=weight_kg,
            chest_cm=values["chest_cm"],
            waist_cm=values["waist_cm"],
            hip_cm=values["hip_cm"],
            shoulder_cm=values["shoulder_cm"],
            inseam_cm=values["inseam_cm"],
            neck_cm=values["neck_cm"],
            body_shape=(body_shape or None),
            warnings=tuple(warnings),
        )

    # ── derived ─────────────────────────────────────────────────────────────
    @property
    def bmi(self) -> Optional[float]:
        if self.weight_kg is None or not self.height_cm:
            return None
        return round(self.weight_kg / ((self.height_cm / 100.0) ** 2), 2)

    def measured_girths(self) -> Dict[str, float]:
        """Girths the USER supplied (estimates excluded) — the evidence base."""
        out: Dict[str, float] = {}
        for field in ("chest_cm", "waist_cm", "hip_cm", "shoulder_cm", "neck_cm", "inseam_cm"):
            value = getattr(self, field)
            if value is not None and field not in self.estimated_fields:
                out[field] = value
        return out

    def known_girths(self) -> Dict[str, float]:
        """All girths present, measured or estimated."""
        return {
            field: getattr(self, field)
            for field in ("chest_cm", "waist_cm", "hip_cm", "shoulder_cm", "neck_cm", "inseam_cm")
            if getattr(self, field) is not None
        }

    def with_estimates(self, estimates: Dict[str, float]) -> "BodyMeasurements":
        """Return a copy carrying population estimates, flagged as estimated."""
        if not estimates:
            return self
        applied = {k: round(v, 1) for k, v in estimates.items() if getattr(self, k) is None}
        if not applied:
            return self
        return replace(
            self,
            **applied,
            estimated_fields=frozenset(self.estimated_fields | set(applied)),
        )

    def as_dict(self) -> Dict[str, Optional[float]]:
        return {
            "height_cm": self.height_cm,
            "weight_kg": self.weight_kg,
            "chest_cm": self.chest_cm,
            "waist_cm": self.waist_cm,
            "hip_cm": self.hip_cm,
            "shoulder_cm": self.shoulder_cm,
            "inseam_cm": self.inseam_cm,
            "neck_cm": self.neck_cm,
            "bmi": self.bmi,
        }
