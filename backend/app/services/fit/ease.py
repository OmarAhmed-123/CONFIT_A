"""Garment ease model — how much room a style is supposed to leave.

Why ease, and not "BMI -> letter"
---------------------------------
Apparel fit is governed by *ease*: the difference between a garment's girth and
the wearer's body girth at the same section. A blazer that measures the same as
your chest does not fit; it needs roughly 10–14 cm of wearing + design ease. A
knit t-shirt needs far less (and can even be worn with negative ease). This is
the standard formulation in the fit-recommendation literature — compare actual
ease against the *ideal ease* for the style, score the deviation per section,
then aggregate. That is what this module parameterises and what
``engine.py`` scores.

Two chart conventions are supported, because real catalogues mix them:

* ``measurement_type == "body"`` (the common case, and what EN 13402 charts
  are): the chart already states the *body* girth the size is cut for, so the
  ideal ease is zero-by-construction — the target is simply "your girth inside
  the row's range", and the ease table is used only to decide how a deviation
  should be *interpreted* (tight vs. relaxed) and how much slack the style
  tolerates.
* ``measurement_type == "garment"``: the chart states finished-garment girths,
  so the engine subtracts the style's ideal ease to recover the body girth the
  size targets before scoring.

Everything here is data, not behaviour, so it is reviewable by a merchandiser
without reading Python. Values are in centimetres of total girth (not radius).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple


class GarmentClass(str, Enum):
    """Fit-relevant garment families. Chosen by category/style, not by name."""

    TAILORED_OUTER = "tailored_outer"   # blazers, suit jackets, coats
    CASUAL_OUTER = "casual_outer"       # bombers, parkas, overshirts
    WOVEN_TOP = "woven_top"             # shirts, blouses
    KNIT_TOP = "knit_top"               # t-shirts, jersey, sweaters
    DRESS = "dress"
    TROUSERS = "trousers"               # trousers, chinos, jeans
    SKIRT = "skirt"
    ACTIVEWEAR = "activewear"           # stretch-dominated
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EaseProfile:
    """Ideal ease (cm) per section plus how forgiving the style is.

    ``tolerance`` is the half-width (cm) of the "just right" band around the
    ideal ease. Inside it, fit is scored as perfect; outside it the deviation
    is penalised, and ``stretch_factor`` (0..1, share of girth recoverable by
    fabric stretch) reduces the penalty for being *under* the target.
    """

    ideal_ease_cm: Dict[str, float]
    tolerance_cm: Dict[str, float]
    stretch_factor: float = 0.0
    # Relative importance of each section for THIS garment class. Trousers are
    # decided at the waist/hip; a blazer at the chest and shoulder.
    weights: Dict[str, float] = None  # type: ignore[assignment]

    def ideal(self, dimension: str) -> float:
        return self.ideal_ease_cm.get(dimension, 0.0)

    def tolerance(self, dimension: str) -> float:
        return self.tolerance_cm.get(dimension, 3.0)

    def weight(self, dimension: str) -> float:
        return (self.weights or {}).get(dimension, 0.0)


# Ideal ease values below are conventional apparel-industry wearing+design ease
# ranges expressed as midpoints; tolerances are the usable band around them.
_PROFILES: Dict[GarmentClass, EaseProfile] = {
    GarmentClass.TAILORED_OUTER: EaseProfile(
        ideal_ease_cm={"chest": 12.0, "waist": 12.0, "hip": 8.0, "shoulder": 1.5, "neck": 2.0},
        tolerance_cm={"chest": 3.0, "waist": 4.0, "hip": 4.0, "shoulder": 1.0, "neck": 1.0},
        stretch_factor=0.0,
        weights={"chest": 0.45, "shoulder": 0.25, "waist": 0.20, "hip": 0.10},
    ),
    GarmentClass.CASUAL_OUTER: EaseProfile(
        ideal_ease_cm={"chest": 16.0, "waist": 16.0, "hip": 12.0, "shoulder": 3.0},
        tolerance_cm={"chest": 5.0, "waist": 6.0, "hip": 6.0, "shoulder": 2.0},
        stretch_factor=0.05,
        weights={"chest": 0.55, "shoulder": 0.20, "waist": 0.15, "hip": 0.10},
    ),
    GarmentClass.WOVEN_TOP: EaseProfile(
        ideal_ease_cm={"chest": 10.0, "waist": 10.0, "hip": 8.0, "shoulder": 1.0, "neck": 1.5},
        tolerance_cm={"chest": 3.5, "waist": 5.0, "hip": 5.0, "shoulder": 1.0, "neck": 0.8},
        stretch_factor=0.02,
        weights={"chest": 0.50, "shoulder": 0.20, "waist": 0.20, "hip": 0.10},
    ),
    GarmentClass.KNIT_TOP: EaseProfile(
        ideal_ease_cm={"chest": 6.0, "waist": 6.0, "hip": 6.0, "shoulder": 1.0},
        tolerance_cm={"chest": 5.0, "waist": 6.0, "hip": 6.0, "shoulder": 1.5},
        stretch_factor=0.25,
        weights={"chest": 0.65, "shoulder": 0.15, "waist": 0.12, "hip": 0.08},
    ),
    GarmentClass.DRESS: EaseProfile(
        ideal_ease_cm={"chest": 8.0, "waist": 6.0, "hip": 8.0, "shoulder": 1.0},
        tolerance_cm={"chest": 3.5, "waist": 3.5, "hip": 3.5, "shoulder": 1.0},
        stretch_factor=0.10,
        weights={"chest": 0.34, "waist": 0.33, "hip": 0.28, "shoulder": 0.05},
    ),
    GarmentClass.TROUSERS: EaseProfile(
        ideal_ease_cm={"waist": 3.0, "hip": 6.0, "inseam": 0.0},
        tolerance_cm={"waist": 2.5, "hip": 4.0, "inseam": 2.5},
        stretch_factor=0.08,
        weights={"waist": 0.55, "hip": 0.35, "inseam": 0.10},
    ),
    GarmentClass.SKIRT: EaseProfile(
        ideal_ease_cm={"waist": 2.5, "hip": 6.0},
        tolerance_cm={"waist": 2.5, "hip": 4.0},
        stretch_factor=0.08,
        weights={"waist": 0.55, "hip": 0.45},
    ),
    GarmentClass.ACTIVEWEAR: EaseProfile(
        ideal_ease_cm={"chest": 2.0, "waist": 1.0, "hip": 2.0},
        tolerance_cm={"chest": 5.0, "waist": 5.0, "hip": 5.0},
        stretch_factor=0.45,
        weights={"chest": 0.40, "waist": 0.30, "hip": 0.30},
    ),
    # UNKNOWN deliberately carries generous tolerance and no strong opinion:
    # when we cannot tell what the garment is, the engine must be less certain,
    # not more. Confidence is reduced for this class in engine.py.
    GarmentClass.UNKNOWN: EaseProfile(
        ideal_ease_cm={"chest": 9.0, "waist": 8.0, "hip": 8.0, "shoulder": 1.5},
        tolerance_cm={"chest": 5.0, "waist": 6.0, "hip": 6.0, "shoulder": 2.0},
        stretch_factor=0.10,
        weights={"chest": 0.45, "waist": 0.25, "hip": 0.20, "shoulder": 0.10},
    ),
}

# Fit preference shifts the ideal ease. Slim = less room, relaxed/oversized =
# more. Applied as a per-section delta in cm (girth), scaled by section.
_FIT_PREFERENCE_DELTA_CM: Dict[str, float] = {
    "slim": -4.0,
    "tailored": -4.0,
    "regular": 0.0,
    "standard": 0.0,
    "relaxed": +4.0,
    "loose": +6.0,
    "oversized": +8.0,
}

VALID_FIT_PREFERENCES: Tuple[str, ...] = tuple(sorted(_FIT_PREFERENCE_DELTA_CM))

# Category slug / style tag -> garment class. Matched on substrings so a
# catalogue that says "outerwear/blazers" or "mens-tailoring" still resolves.
_CATEGORY_KEYWORDS: Tuple[Tuple[GarmentClass, Tuple[str, ...]], ...] = (
    (GarmentClass.TAILORED_OUTER, ("blazer", "suit", "tailor", "tuxedo", "sport-coat", "sportcoat", "overcoat", "trench")),
    (GarmentClass.CASUAL_OUTER, ("outerwear", "jacket", "coat", "parka", "bomber", "puffer", "overshirt", "gilet", "vest")),
    (GarmentClass.KNIT_TOP, ("t-shirt", "tshirt", "tee", "knit", "jersey", "sweater", "jumper", "hoodie", "sweatshirt", "cardigan", "polo")),
    (GarmentClass.WOVEN_TOP, ("shirt", "blouse", "top", "tunic")),
    (GarmentClass.DRESS, ("dress", "gown", "jumpsuit", "abaya", "kaftan", "caftan")),
    (GarmentClass.TROUSERS, ("trouser", "pant", "jean", "denim", "chino", "short", "cargo", "legging", "bottom")),
    (GarmentClass.SKIRT, ("skirt",)),
    (GarmentClass.ACTIVEWEAR, ("active", "sport", "gym", "training", "performance", "yoga", "run")),
)

_STRETCH_MATERIALS: Tuple[Tuple[str, float], ...] = (
    ("elastane", 0.20), ("spandex", 0.20), ("lycra", 0.20),
    ("jersey", 0.12), ("rib", 0.10), ("stretch", 0.10), ("knit", 0.08),
)


def classify_garment(
    *,
    category_slug: Optional[str] = None,
    category_name: Optional[str] = None,
    title: Optional[str] = None,
    style_tags: Optional[list] = None,
) -> GarmentClass:
    """Best-effort garment class. Returns UNKNOWN rather than guessing wrong.

    Signals are checked most-specific first (tailoring beats generic outerwear)
    and across every text field the catalogue offers, because real data puts
    the useful word in a different column for every brand.
    """
    haystack = " ".join(
        str(part).lower()
        for part in (category_slug, category_name, title, *(style_tags or []))
        if part
    )
    if not haystack.strip():
        return GarmentClass.UNKNOWN
    for garment_class, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return garment_class
    return GarmentClass.UNKNOWN


def stretch_bonus_from_material(material: Optional[str]) -> float:
    """Extra stretch share implied by the material string (0 when unknown)."""
    if not material:
        return 0.0
    text = str(material).lower()
    return max((bonus for token, bonus in _STRETCH_MATERIALS if token in text), default=0.0)


def ease_targets(
    garment_class: GarmentClass,
    fit_preference: str = "regular",
    *,
    material: Optional[str] = None,
) -> EaseProfile:
    """Ease profile for a garment class, shifted by the user's fit preference.

    Unknown preferences fall back to 'regular' — the caller validates the
    vocabulary at the API boundary (``VALID_FIT_PREFERENCES``), so reaching
    here with junk means a programming error, not a user error, and silently
    inventing a shift would be worse than neutral behaviour.
    """
    base = _PROFILES.get(garment_class, _PROFILES[GarmentClass.UNKNOWN])
    delta = _FIT_PREFERENCE_DELTA_CM.get(str(fit_preference or "regular").lower(), 0.0)

    # Length sections (inseam) are not affected by a fit preference.
    shifted = {
        dim: (value + delta if dim != "inseam" else value)
        for dim, value in base.ideal_ease_cm.items()
    }
    stretch = min(0.6, base.stretch_factor + stretch_bonus_from_material(material))
    return EaseProfile(
        ideal_ease_cm=shifted,
        tolerance_cm=dict(base.tolerance_cm),
        stretch_factor=round(stretch, 3),
        weights=dict(base.weights or {}),
    )
