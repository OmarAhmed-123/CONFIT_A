"""Group 1 profile / USP schemas.

Split DTOs implement spec §31: separate update contracts so a PATCH to one
concern (e.g. body attributes) cannot silently overwrite unrelated fields
with schema defaults. Every "update" schema uses Optional fields and the
controller passes `exclude_unset=True` — a caller who does not send a field
does not touch it.
"""
from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, Field, ConfigDict
from backend.app.schemas.money_types import OptionalNonNegativeMoney

# --- Canonical registries -----------------------------------------------------
# Group 1 §22: extensible server-side validation. Adding a value is a
# one-line change here; the DB stays JSON so no destructive schema change.
SUPPORTED_STYLE_ARCHETYPES = {
    "Smart Casual", "Quiet Luxury", "Modern Minimalist", "Streetwear Tailored",
    "Old Money", "Bohemian Refined", "Casual", "Formal", "Sporty",
    "Bohemian", "Classic", "Minimalist", "Luxury",
}
SUPPORTED_FASHION_AESTHETICS = {
    "Old Money", "Modern Tailored", "Relaxed Elegance", "Quiet Luxury",
    "Streetwear", "Minimalist", "Preppy", "Athleisure", "Coastal Grandmother",
    "Dark Academia", "Y2K", "Cottagecore",
}
SUPPORTED_FIT = {"slim", "regular", "oversized", "relaxed"}
SUPPORTED_BODY_SHAPES = {
    "Athletic", "Hourglass", "Rectangle", "Pear", "Inverted Triangle", "Apple", "Oval",
}
SUPPORTED_OCCASIONS = {"work", "casual", "party", "formal", "sports", "travel", "date_night"}


def _validate_subset(values: List[str], allowed: set, field: str) -> List[str]:
    unknown = [v for v in values if v not in allowed]
    if unknown:
        from backend.app.core.exceptions import ValidationDomainError
        raise ValidationDomainError(
            f"Unsupported values for {field}: {unknown}",
            field_errors={field: unknown},
        )
    return values


# --- Body attributes ---------------------------------------------------------
class BodyAttributesInput(BaseModel):
    """All fields OPTIONAL. If nothing is sent, no body row is created."""
    height_cm: Optional[float] = Field(default=None, ge=100, le=250)
    weight_kg: Optional[float] = Field(default=None, ge=30, le=250)
    body_shape: Optional[str] = None
    chest_cm: Optional[float] = Field(default=None, ge=50, le=200)
    waist_cm: Optional[float] = Field(default=None, ge=40, le=200)
    hip_cm: Optional[float] = Field(default=None, ge=50, le=200)
    inseam_cm: Optional[float] = Field(default=None, ge=40, le=140)

    def has_any_value(self) -> bool:
        return any(v is not None for v in self.model_dump().values())


class BodyAttributesOutput(BaseModel):
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    body_shape: Optional[str] = None
    chest_cm: Optional[float] = None
    waist_cm: Optional[float] = None
    hip_cm: Optional[float] = None
    inseam_cm: Optional[float] = None
    is_encrypted: bool = True


# --- Split preference DTOs (§31) ---------------------------------------------
class StylePreferencesInput(BaseModel):
    style_archetypes: Optional[List[str]] = None
    preferred_colors: Optional[List[str]] = None
    avoided_colors: Optional[List[str]] = None
    fashion_aesthetics: Optional[List[str]] = None


class BudgetPreferencesInput(BaseModel):
    budget_monthly_min: OptionalNonNegativeMoney = None
    budget_monthly_max: OptionalNonNegativeMoney = None
    budget_per_outfit_max: OptionalNonNegativeMoney = None


class BrandPreferencesInput(BaseModel):
    preferred_brands: Optional[List[str]] = None
    blacklisted_brands: Optional[List[str]] = None


class OccasionPreferencesInput(BaseModel):
    occasion_weights: Optional[Dict[str, float]] = None


class SizeFitPreferencesInput(BaseModel):
    size_tops: Optional[str] = None
    size_bottoms: Optional[str] = None
    size_shoes: Optional[str] = None
    fit_preference: Optional[str] = None


# --- Full onboarding wizard payload ------------------------------------------
class OnboardingQuizInput(BaseModel):
    """Full 5-step wizard payload. Every field is optional so a partial
    submission (e.g. user skipped the body step) never fabricates defaults —
    the repository writes only what is actually present."""
    style_archetypes: Optional[List[str]] = None
    preferred_colors: Optional[List[str]] = None
    avoided_colors: Optional[List[str]] = None
    fashion_aesthetics: Optional[List[str]] = None
    budget_monthly_min: OptionalNonNegativeMoney = None
    budget_monthly_max: OptionalNonNegativeMoney = None
    budget_per_outfit_max: OptionalNonNegativeMoney = None
    preferred_brands: Optional[List[str]] = None
    blacklisted_brands: Optional[List[str]] = None
    occasion_weights: Optional[Dict[str, float]] = None
    size_tops: Optional[str] = None
    size_bottoms: Optional[str] = None
    size_shoes: Optional[str] = None
    fit_preference: Optional[str] = None
    body_attributes: Optional[BodyAttributesInput] = None
    privacy_consent_tryon_storage: Optional[bool] = None
    privacy_consent_share_with_brands: Optional[bool] = None


# --- Consent -----------------------------------------------------------------
class ConsentState(BaseModel):
    """Server-truth consent state for the authenticated user.

    Backed by real columns on `user_style_profiles`. `policy_version` and
    `last_agreed_at` come from the profile row (or NULL when no profile
    exists yet), never from a hardcoded default.
    """
    user_id: int
    photo_storage: bool
    ai_personalization: bool
    marketing_analytics: bool
    share_with_brands: bool
    policy_version: int
    last_agreed_at: Optional[datetime] = None


class ConsentUpdate(BaseModel):
    photo_storage: Optional[bool] = None
    ai_personalization: Optional[bool] = None
    marketing_analytics: Optional[bool] = None
    share_with_brands: Optional[bool] = None


# --- USP response ------------------------------------------------------------
class USPResponse(BaseModel):
    id: int
    user_id: int
    style_archetypes: List[str]
    preferred_colors: List[str]
    avoided_colors: List[str]
    fashion_aesthetics: List[str]
    budget_monthly_min: Optional[float]
    budget_monthly_max: Optional[float]
    budget_per_outfit_max: Optional[float]
    preferred_brands: List[str]
    blacklisted_brands: List[str]
    occasion_weights: Dict[str, float]
    size_tops: Optional[str]
    size_bottoms: Optional[str]
    size_shoes: Optional[str]
    fit_preference: Optional[str]
    body_shape_tag: Optional[str]
    body_attributes: Optional[BodyAttributesOutput]
    onboarding_completed: bool
    privacy_consent_tryon_storage: bool
    privacy_consent_share_with_brands: bool
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Legacy alias — kept so old code paths (auth service, seed) still import
StyleQuizInput = OnboardingQuizInput
