from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class WardrobeItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    category: str  # Tops, Bottoms, Outerwear, Footwear, Accessories
    subcategory: Optional[str] = None
    color_name: str = Field(min_length=1, max_length=50)
    color_hex: str = "#1B1F3B"
    pattern: str = "Solid"
    brand_name: str = "Own Collection"
    image_url: str = Field(min_length=1, max_length=1000)
    occasions: List[str] = Field(default_factory=lambda: ["casual"])
    seasonality: str = "All-Season"
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
    seasonality: Optional[str] = None
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
    secondary_colors: List[str] = Field(default_factory=list)
    seasonality: str = "All-Season"
    processing_status: str = "ready"  # uploaded | processing | ready | failed
    processing_error: Optional[str] = None
    ai_confidence: Optional[float] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WardrobeUploadResultEntry(BaseModel):
    filename: str
    status: str  # created | failed | duplicate
    detail: Optional[str] = None
    item: Optional[WardrobeItemOut] = None


class WardrobeUploadSummary(BaseModel):
    total: int
    succeeded: int
    failed: int
    duplicates_skipped: int


class WardrobeUploadResponse(BaseModel):
    results: List[WardrobeUploadResultEntry]
    summary: WardrobeUploadSummary


class WardrobeAutoTagRequest(BaseModel):
    image_url: Optional[str] = None
    image_base64: Optional[str] = None


class WardrobeAutoTagResponse(BaseModel):
    analysis_available: bool = True
    detail: Optional[str] = None
    detected_title: Optional[str] = None
    detected_category: Optional[str] = None
    detected_subcategory: Optional[str] = None
    detected_color: Optional[str] = None
    detected_color_hex: Optional[str] = None
    detected_pattern: Optional[str] = None
    ai_tags: List[str] = Field(default_factory=list)
    suggested_occasions: List[str] = Field(default_factory=list)
    seasonality: Optional[str] = None
    confidence: Optional[float] = None


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
    pattern: Optional[str] = None
    strict_mode: bool = False


class WardrobeFirstOutfitItem(BaseModel):
    position: str
    source: str  # "owned" | "catalog"
    wardrobe_item_id: Optional[int] = None
    product_id: Optional[int] = None
    product_title: str
    brand_name: str
    color_family: Optional[str] = None
    dominant_hex: Optional[str] = None
    image_url: str
    price: float = 0.0


class WardrobeFirstOutfitOut(BaseModel):
    occasion: str
    owned_items: List[Dict[str, Any]]
    owned_count: int
    missing_positions: List[str]
    purchase_suggestions: List[Dict[str, Any]]
    compatibility_score: int
    is_complete_outfit: bool
    wardrobe_first: bool
    message: str


class DuplicateAlertResponse(BaseModel):
    has_duplicate_risk: bool
    similarity_score: int
    owned_item: Optional[WardrobeItemOut] = None
    alert_message: Optional[str] = None
    comparison_notes: Optional[str] = None
