from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class StylistPromptRequest(BaseModel):
    session_id: Optional[int] = None
    prompt: str = Field(description="Natural language request or occasion text e.g. 'I need a smart casual outfit for an art gallery opening under $300'")
    occasion: Optional[str] = None
    budget_limit: Optional[float] = None
    voice_input_used: bool = False
    include_wardrobe_items: bool = True


class OutfitItemOut(BaseModel):
    id: int
    product_id: int
    product_title: str
    brand_name: str
    category_name: str
    price: float
    image_url: str
    color_hex: str
    position: str  # "top", "bottom", "outerwear", "shoes", "footwear", "accessory", "dress"
    slot_type: Optional[str] = None
    color_family: Optional[str] = None
    material: Optional[str] = None
    role_in_outfit: Optional[str] = None
    sku_id: Optional[int] = None
    selected_size: Optional[str] = "M"

    model_config = ConfigDict(from_attributes=True)


class OutfitOut(BaseModel):
    id: int
    title: str
    description: Optional[str]
    occasion: str
    total_price: float
    compatibility_score: int
    color_palette: List[str]
    style_tags: List[str]
    is_saved: bool
    is_system_curated: bool
    is_complete: Optional[bool] = True
    completeness_status: Optional[str] = "complete_look"
    completeness_label: Optional[str] = "Complete Look"
    missing_slots: Optional[List[str]] = []
    color_harmony_score: Optional[int] = 95
    formality_score: Optional[int] = 90
    items: List[OutfitItemOut]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StylistMessageOut(BaseModel):
    id: int
    session_id: int
    sender: str
    content: str
    audio_url: Optional[str] = None
    intent_detected: Dict[str, Any]
    recommendations: List[OutfitOut]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StylistSessionOut(BaseModel):
    id: int
    user_id: int
    session_title: str
    messages: List[StylistMessageOut]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OutfitCreateInput(BaseModel):
    title: str
    occasion: str
    product_sku_ids: List[int]
    description: Optional[str] = None


class CompatibilityCheckRequest(BaseModel):
    product_ids: List[int]
    target_occasion: Optional[str] = "Casual"


class CompatibilityCheckResponse(BaseModel):
    compatibility_score: int  # 0-100
    color_harmony_type: str   # "Monochromatic", "Complementary", "Analogous", "Triadic", "Balanced Neutral"
    color_harmony_verdict: str
    aesthetic_consistency_verdict: str
    occasion_score: int
    budget_status: str
    suggestions: List[str]
