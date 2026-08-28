from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class TryOnJobCreate(BaseModel):
    product_ids: List[int]
    user_image_url: Optional[str] = None
    user_image_base64: Optional[str] = None
    avatar_model_id: Optional[str] = "avatar_athletic_m"
    gender_mode: Optional[str] = "infer_from_image"
    output_aspect: Optional[str] = "9:16"
    background_mode: Optional[str] = "studio"
    consent_retain_photo: bool = False


class TryOnJobOut(BaseModel):
    id: int
    job_id: str
    status: str
    progress_pct: int
    current_stage: str
    model_used: str
    output_image_url: Optional[str] = None
    metrics: Dict[str, Any] = {}
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class GarmentAssetOut(BaseModel):
    id: int
    product_id: int
    slot_type: str
    flat_image_url: str
    segmented_garment_url: Optional[str] = None
    garment_mask_url: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApplyItemRequest(BaseModel):
    product_id: int
    slot: Optional[str] = None
    replace_if_occupied: bool = True


class RemoveItemRequest(BaseModel):
    product_id: Optional[int] = None
    slot: Optional[str] = None


class ReorderItemsRequest(BaseModel):
    slot_order: List[str]


class TryOnRequest(BaseModel):
    product_id: int
    user_image_url: Optional[str] = None
    user_image_base64: Optional[str] = None
    avatar_model_id: Optional[str] = "avatar_athletic_m"
    consent_retain_photo: bool = False
    custom_adjustments: Optional[Dict[str, Any]] = None


class TryOnResponse(BaseModel):
    session_id: int
    product_id: int
    product_title: str
    brand_name: str
    status: str
    original_item_image: str
    rendered_result_url: str
    fit_confidence_score: int
    body_fit_verdict: str
    recommended_size: str
    ai_disclosure: str
    traceability_hash: str
    expires_at: Optional[datetime] = None


class AppliedGarmentOut(BaseModel):
    product_id: int
    product_title: str
    brand_name: str
    category_name: str
    position: str  # "upper_outer", "upper_inner", "lower", "dress", "footwear", "accessory"
    image_url: str
    color_family: Optional[str] = None
    color_hex: Optional[str] = "#1B1F3B"
    material: Optional[str] = None
    price: float
    selected_size: Optional[str] = "M"
    layer_order: int = 1

    model_config = ConfigDict(from_attributes=True)


class MultiGarmentTryOnRequest(BaseModel):
    product_ids: Optional[List[int]] = []
    slot_mapping: Optional[Dict[str, int]] = {}
    user_image_url: Optional[str] = None
    user_image_base64: Optional[str] = None
    avatar_model_id: Optional[str] = "avatar_athletic_m"
    gender_mode: Optional[str] = "infer_from_image"
    pose_mode: Optional[str] = "standing_front"
    background_mode: Optional[str] = "luxury_studio"
    body_preservation_mode: str = "strict"
    face_preservation_mode: str = "strict"
    consent_retain_photo: bool = False


class MultiGarmentTryOnResponse(BaseModel):
    session_id: int
    status: str
    user_reference_image: str
    rendered_result_url: str
    before_after_split_url: Optional[str] = None
    applied_items: List[AppliedGarmentOut] = []
    total_price: float
    fit_confidence_score: int
    body_fit_verdict: str
    recommended_sizes: Dict[str, str] = {}
    ai_disclosure: str
    traceability_hash: str
    layering_order: List[str] = []
    dynamic_prompt_generated: Optional[str] = None
    expires_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AnimationKeyframeOut(BaseModel):
    step: int
    slot: str
    product_title: str
    brand_name: str
    image_url: str
    status: str

    model_config = ConfigDict(from_attributes=True)


class AnimationTryOnRequest(BaseModel):
    product_ids: Optional[List[int]] = []
    slot_mapping: Optional[Dict[str, int]] = {}
    user_image_url: Optional[str] = None
    avatar_model_id: Optional[str] = "avatar_athletic_m"
    gender_mode: Optional[str] = "infer_from_image"
    output_aspect: Optional[str] = "9:16"
    background_mode: Optional[str] = "studio"
    animation_style: Optional[str] = "premium_realistic"


class AnimationTryOnResponse(BaseModel):
    session_id: int
    status: str
    animation_style: str
    output_aspect: str
    rendered_animation_url: str
    keyframes_sequence: List[AnimationKeyframeOut] = []
    fit_confidence_score: int
    body_fit_verdict: str
    traceability_hash: str
    ai_disclosure: str
    dynamic_animation_prompt: str
    applied_items: List[AppliedGarmentOut] = []
    total_price: float

    model_config = ConfigDict(from_attributes=True)


class ImageValidationRequest(BaseModel):
    image_url: Optional[str] = None
    image_base64: Optional[str] = None


class ImageValidationResponse(BaseModel):
    is_valid: bool
    detected_gender: str
    body_framing: str
    resolution_status: str
    lighting_quality: str
    suggestions: List[str] = []


class NoPhotoFitRequest(BaseModel):
    product_id: int
    height_cm: float = Field(ge=100, le=250)
    weight_kg: float = Field(ge=30, le=250)
    body_shape: str = Field(description="Hourglass, Athletic, Rectangle, Pear, Inverted Triangle")
    chest_cm: Optional[float] = None
    waist_cm: Optional[float] = None
    hip_cm: Optional[float] = None
    preferred_fit: str = "regular"


class NoPhotoFitResponse(BaseModel):
    product_id: int
    recommended_size: str
    confidence_score: int
    fit_breakdown: Dict[str, str]
    size_comparison_table: List[Dict[str, Any]]
    brand_sizing_tendency: str
    return_risk_score: str


class VisualSearchRequest(BaseModel):
    image_url: Optional[str] = None
    image_base64: Optional[str] = None
    category_hint: Optional[str] = None
    max_price: Optional[float] = None
    in_stock_only: bool = True


class VisualSearchResultItem(BaseModel):
    product_id: int
    title: str
    brand_name: str
    price: float
    image_url: str
    similarity_score: int
    detected_color: str
    match_type: str


class VisualSearchResponse(BaseModel):
    query_id: int
    analysis_available: bool = False
    analysis_source: Optional[str] = None
    detected_category: Optional[str] = None
    detected_color: Optional[str] = None
    detected_pattern: Optional[str] = None
    detected_style: Optional[str] = None
    results_count: int
    matches: List[VisualSearchResultItem]


# Measurement Flow Schemas
class MeasurementSessionCreate(BaseModel):
    capture_mode: str = Field(default="client_side", description="'client_side', 'server_side', 'manual'")
    consent_granted: bool = True
    save_to_profile: bool = False


class MeasurementResultCreate(BaseModel):
    height_cm: float = Field(ge=100, le=250)
    shoulder_width_cm: Optional[float] = None
    chest_cm: Optional[float] = None
    waist_cm: Optional[float] = None
    hip_cm: Optional[float] = None
    inseam_cm: Optional[float] = None
    body_shape: Optional[str] = "Athletic"
    confidence_score: int = Field(default=95, ge=50, le=100)
    calibration_method: str = "on_device_height_calibrated"
    source: str = "camera_estimate"


class MeasurementResultOut(BaseModel):
    id: int
    session_id: int
    height_cm: float
    shoulder_width_cm: Optional[float]
    chest_cm: Optional[float]
    waist_cm: Optional[float]
    hip_cm: Optional[float]
    inseam_cm: Optional[float]
    body_shape: str
    confidence_score: int
    calibration_method: str
    source: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MeasurementSessionOut(BaseModel):
    id: int
    user_id: Optional[int]
    status: str
    capture_mode: str
    consent_granted: bool
    save_to_profile: bool
    results: List[MeasurementResultOut] = []
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
