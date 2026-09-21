from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class GuidedRecommendationConstraints(BaseModel):
    """Structured constraints for the guided first-look contract.

    Palette values are normalized server-side against the catalog colour
    taxonomy. Fit only becomes authoritative when a concrete size profile is
    supplied or present on the authenticated profile; a vague fit preference is
    recorded as preference context but does not create a fake size score.
    """
    palette: Optional[str] = Field(default=None, max_length=40)
    avoid_palette: Optional[str] = Field(default=None, max_length=40)
    preferred_fit: Optional[str] = Field(default=None, max_length=30)
    size_tops: Optional[str] = Field(default=None, max_length=20)
    size_bottoms: Optional[str] = Field(default=None, max_length=20)
    size_shoes: Optional[str] = Field(default=None, max_length=20)


class StylistPromptRequest(BaseModel):
    session_id: Optional[int] = None
    prompt: str = Field(description="Natural language request or occasion text e.g. 'I need a smart casual outfit for an art gallery opening under $300'")
    occasion: Optional[str] = None
    budget_limit: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    voice_input_used: bool = False
    include_wardrobe_items: bool = True
    recommendation_constraints: Optional[GuidedRecommendationConstraints] = None


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
    budget_limit: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    within_budget: Optional[bool] = True
    budget_note: Optional[str] = None
    items: List[OutfitItemOut]
    created_at: datetime
    updated_at: Optional[datetime] = None
    composition_warnings: Optional[List[str]] = []
    # Sharing state is reported from the real token lifecycle (OUTFIT-01).
    is_shared: Optional[bool] = False
    share_url: Optional[str] = None
    share_expires_at: Optional[datetime] = None
    share_view_count: Optional[int] = 0

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
    """Canonical outfit-creation contract.

    The client may reference items EITHER by SKU (`product_sku_ids`) or by
    product (`product_ids`); at least one must be non-empty. The service layer
    resolves product ids -> a default in-stock SKU so both the Outfit Builder
    (SKU-based canvas) and the Stylist cards (product-based) share one contract.
    """
    title: str = Field(min_length=1, max_length=255)
    occasion: str = Field(default="Casual", max_length=100)
    product_sku_ids: Optional[List[int]] = None
    product_ids: Optional[List[int]] = None
    description: Optional[str] = Field(default=None, max_length=2000)


class OutfitUpdateInput(BaseModel):
    """Explicit, allow-listed update schema (no mass-assignment).

    Only client-editable fields are accepted. Protected fields (user_id,
    compatibility_score, is_saved, share_token, system metadata) cannot be
    set through this endpoint.
    """
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    occasion: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None, max_length=2000)


class OutfitItemsReplaceInput(BaseModel):
    """Full replacement of a saved look's item set (canvas edit / reorder).

    Deliberately a PUT-style whole-set contract rather than per-item patches:
    the composition policy validates a *set*, so partial mutations could never
    be checked coherently, and a whole-set swap is idempotent under retry.
    """
    product_sku_ids: Optional[List[int]] = Field(default=None, max_length=12)
    product_ids: Optional[List[int]] = Field(default=None, max_length=12)


class CompositionPreviewInput(BaseModel):
    """Dry-run input for the live canvas validity check."""
    product_sku_ids: Optional[List[int]] = Field(default=None, max_length=12)
    product_ids: Optional[List[int]] = Field(default=None, max_length=12)


class CompositionViolationOut(BaseModel):
    code: str
    message: str
    positions: List[str] = []


class CompositionVerdictOut(BaseModel):
    """Explainable validity verdict — the UI shows the reason, not a guess."""
    is_valid: bool
    violations: List[CompositionViolationOut] = []
    warnings: List[str] = []
    missing_positions: List[str] = []
    resolved_items: List[Dict[str, Any]] = []
    unresolved_ids: List[int] = []


class ShareRequestInput(BaseModel):
    """Options when minting a share link."""
    ttl_days: Optional[int] = Field(default=None, ge=1, le=365)
    rotate: bool = False


class ShareLinkOut(BaseModel):
    """Truthful share-link state. ``is_active`` is computed from revocation +
    expiry, never assumed from the mere existence of a token."""
    outfit_id: int
    share_token: Optional[str] = None
    share_url: Optional[str] = None
    expires_at: Optional[datetime] = None
    is_active: bool
    view_count: int = 0


class ShareRevokeOut(BaseModel):
    outfit_id: int
    revoked: bool
    was_active: bool
    is_active: bool


class PublicLookItemOut(BaseModel):
    """A single item on a publicly shared look — catalog facts only."""
    product_title: str
    brand_name: str
    category_name: str
    price: float
    image_url: str
    color_hex: str
    position: str


class PublicLookOut(BaseModel):
    """Public, read-only shared-look DTO (C8).

    Deliberately excludes every private field: no outfit id, no user_id, no
    owner identity, no profile data, no internal metadata.
    """
    title: str
    occasion: str
    description: Optional[str]
    total_price: float
    compatibility_score: int
    items: List[PublicLookItemOut]
    created_at: datetime


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
