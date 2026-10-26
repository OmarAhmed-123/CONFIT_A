"""Data contract for the wardrobe outfit recommendation (IBM stylist tutorial
alignment). Everything the model emits is re-validated against these models
AND against the caller's real wardrobe before it reaches the client."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

TimeOfDay = Literal["morning", "afternoon", "evening", "night"]
Season = Literal["spring", "summer", "autumn", "winter"]
ItemRole = Literal["top", "bottom", "dress", "footwear", "outerwear", "accessory"]


class OutfitRecommendationRequest(BaseModel):
    occasion: str = Field("Smart Casual", min_length=2, max_length=60)
    time_of_day: Optional[TimeOfDay] = None
    season: Optional[Season] = None
    location: Optional[str] = Field(None, max_length=120)
    activity: Optional[str] = Field(None, max_length=160)
    dress_code: Optional[str] = Field(None, max_length=80)
    style_preferences: List[str] = Field(default_factory=list, max_length=8)
    color_preferences: List[str] = Field(default_factory=list, max_length=8)
    comfort_needs: Optional[str] = Field(None, max_length=200)
    exclusions: Optional[str] = Field(None, max_length=200)
    excluded_item_ids: List[int] = Field(default_factory=list, max_length=50)
    # "Another outfit" — ids from the previous answer so the model varies.
    previous_item_ids: List[int] = Field(default_factory=list, max_length=20)
    # UI locale. Only the free-text prose (summary, reasons, notes) follows it;
    # JSON keys, category names and ids stay English so validation is unchanged.
    language: Literal["en", "ar"] = "en"

    @field_validator("style_preferences", "color_preferences")
    @classmethod
    def _clean_lists(cls, v: List[str]) -> List[str]:
        out = []
        for s in v:
            s = str(s).strip()[:40]
            if s and s not in out:
                out.append(s)
        return out

    @field_validator("occasion", "location", "activity", "dress_code", "comfort_needs", "exclusions")
    @classmethod
    def _strip(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = " ".join(str(v).split())
        return v or None


class RecommendedItem(BaseModel):
    wardrobe_item_id: int
    role: ItemRole
    category: str
    title: str
    subcategory: Optional[str] = None
    color_name: str
    color_hex: str
    image_url: str
    reason: str = Field(min_length=1, max_length=400)
    analysis_source: Optional[str] = None
    ai_confidence: Optional[float] = None


class OutfitRecommendation(BaseModel):
    outfit_id: str
    occasion: str
    title: str
    summary: str
    items: List[RecommendedItem]
    styling_notes: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    missing_categories: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    is_complete: bool
    # Honesty block (FR-18). `source` is one of:
    #   "watsonx"                 – a language model produced the selection + reasons
    #   "deterministic_fallback"  – rule-based scorer; `ai_generated` is False
    source: Literal["watsonx", "deterministic_fallback"]
    ai_generated: bool
    model_id: Optional[str] = None
    prompt_version: Optional[str] = None
    fallback_reason: Optional[str] = None
    latency_seconds: Optional[float] = None
    # Items the model referenced that did NOT exist in the wardrobe (dropped).
    rejected_references: List[int] = Field(default_factory=list)
    context: dict = Field(default_factory=dict)


class StylistStatus(BaseModel):
    """What /wardrobe/stylist/status reports so the UI can set expectations."""
    watsonx_configured: bool
    watsonx_url: Optional[str] = None
    vision_model_id: Optional[str] = None
    reasoning_model_id: Optional[str] = None
    vision_provider_mode: str
    stylist_provider_mode: str
    legacy_vision_configured: bool
    ready_items: int
    categories_present: List[str]
    prompt_version: str
