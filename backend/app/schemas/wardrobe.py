from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class WardrobeItemCreate(BaseModel):
    title: str
    category: str  # Tops, Bottoms, Outerwear, Footwear, Accessories
    subcategory: Optional[str] = None
    color_name: str
    color_hex: str = "#1B1F3B"
    pattern: str = "Solid"
    brand_name: str = "Own Collection"
    image_url: str
    occasions: List[str] = Field(default_factory=lambda: ["casual"])
    wear_frequency: str = "regular"  # "favorite", "regular", "rarely_worn", "seasonal"
    purchase_price: Optional[float] = None
    is_favorite: bool = False


class WardrobeItemUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    color_name: Optional[str] = None
    color_hex: Optional[str] = None
    pattern: Optional[str] = None
    occasions: Optional[List[str]] = None
    wear_frequency: Optional[str] = None
    is_favorite: Optional[bool] = None
    wear_count: Optional[int] = None


class WardrobeItemOut(BaseModel):
    id: int
    user_id: int
    title: str
    category: str
    subcategory: Optional[str]
    color_name: str
    color_hex: str
    pattern: str
    brand_name: str
    image_url: str
    ai_tags: List[str]
    occasions: List[str]
    wear_frequency: str
    wear_count: int
    is_favorite: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WardrobeAutoTagRequest(BaseModel):
    image_url: Optional[str] = None
    image_base64: Optional[str] = None


class WardrobeAutoTagResponse(BaseModel):
    detected_title: str
    detected_category: str
    detected_subcategory: str
    detected_color: str
    detected_color_hex: str
    detected_pattern: str
    ai_tags: List[str]
    suggested_occasions: List[str]
    confidence: float


class GapAnalysisOut(BaseModel):
    id: int
    missing_category: str
    missing_subcategory: str
    suggested_colors: List[str]
    rationale: str
    unlocks_outfit_count: int
    recommended_products: List[Dict[str, Any]]


class DuplicateCheckRequest(BaseModel):
    product_id: int
    product_title: str
    category: str
    color_family: str
    strict_mode: bool = False


class DuplicateAlertResponse(BaseModel):
    has_duplicate_risk: bool
    similarity_score: int
    owned_item: Optional[WardrobeItemOut] = None
    alert_message: Optional[str] = None
    comparison_notes: Optional[str] = None
