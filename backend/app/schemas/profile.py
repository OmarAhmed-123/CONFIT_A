from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class BodyAttributesInput(BaseModel):
    height_cm: Optional[float] = Field(default=None, ge=100, le=250)
    weight_kg: Optional[float] = Field(default=None, ge=30, le=250)
    body_shape: Optional[str] = Field(default=None, description="Hourglass, Athletic, Rectangle, Pear, Inverted Triangle")
    chest_cm: Optional[float] = None
    waist_cm: Optional[float] = None
    hip_cm: Optional[float] = None
    inseam_cm: Optional[float] = None


class BodyAttributesOutput(BaseModel):
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    body_shape: Optional[str] = None
    chest_cm: Optional[float] = None
    waist_cm: Optional[float] = None
    hip_cm: Optional[float] = None
    inseam_cm: Optional[float] = None
    is_encrypted: bool = True


class StyleQuizInput(BaseModel):
    style_archetypes: List[str] = Field(default_factory=list, description="e.g. ['streetwear', 'quiet_luxury', 'minimalist']")
    preferred_colors: List[str] = Field(default_factory=list, description="e.g. ['Navy', 'Beige', 'Black', 'Emerald']")
    avoided_colors: List[str] = Field(default_factory=list)
    fashion_aesthetics: List[str] = Field(default_factory=list)
    budget_monthly_min: float = 100.0
    budget_monthly_max: float = 1000.0
    budget_per_outfit_max: float = 350.0
    preferred_brands: List[str] = Field(default_factory=list)
    occasion_weights: Dict[str, float] = Field(default_factory=lambda: {"work": 0.35, "casual": 0.35, "party": 0.2, "sports": 0.1})
    size_tops: str = "M"
    size_bottoms: str = "32"
    size_shoes: str = "42"
    fit_preference: str = "regular"  # "slim", "regular", "oversized"
    body_attributes: Optional[BodyAttributesInput] = None
    privacy_consent_tryon_storage: bool = False
    privacy_consent_share_with_brands: bool = False


class USPResponse(BaseModel):
    id: int
    user_id: int
    style_archetypes: List[str]
    preferred_colors: List[str]
    avoided_colors: List[str]
    fashion_aesthetics: List[str]
    budget_monthly_min: float
    budget_monthly_max: float
    budget_per_outfit_max: float
    preferred_brands: List[str]
    blacklisted_brands: List[str]
    occasion_weights: Dict[str, float]
    size_tops: str
    size_bottoms: str
    size_shoes: str
    fit_preference: str
    body_shape_tag: Optional[str]
    body_attributes: Optional[BodyAttributesOutput]
    onboarding_completed: bool
    privacy_consent_tryon_storage: bool
    privacy_consent_share_with_brands: bool
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
